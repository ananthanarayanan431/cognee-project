"""Recall — retrieve this user's typed ArgumentRecord/PersonalFact nodes from
Cognee's graph for the opponent and progress views, ranked by relevance.

cognee 0.1.40's graph store and per-class vector collections are GLOBAL across
every user (there is no dataset-scoped graph query the way
`cognee.search(..., datasets=[...])` scopes prose CHUNKS search). So isolation
here is enforced by filtering on each node's own `user_id` property after
loading it — never by trusting the vector search's result order, which only
supplies a relevance ranking over an already-owned candidate set (same
graph+vector join shape as ContextFirewall's recall.py).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from debatemind.cognee._base import SEARCH_TIMEOUT, elapsed_ms, filter_out_patterns, preview

logger = logging.getLogger(__name__)

# Fetched from the GLOBAL per-class vector collection, then filtered down to
# this user's owned nodes — a generous limit so this user's own records are
# likely present in the ranked set even when many other users share the same
# collection. This is a ranking aid only; ownership filtering (below) is what
# actually enforces isolation.
_VECTOR_TOP_K = 100


def _node_props(entry: Any) -> tuple[str, dict]:
    """Normalize a get_graph_data() node entry to (id, properties)."""
    if isinstance(entry, tuple):
        nid, props = entry[0], entry[1]
    else:
        props, nid = entry, entry.get("id")
    return str(nid), dict(props or {})


async def owned_nodes(node_type: str, user_id: str) -> dict[str, dict]:
    """All graph nodes of `node_type` owned by `user_id`, keyed by node id."""
    from cognee.infrastructure.databases.graph import get_graph_engine

    try:
        engine = await get_graph_engine()
        nodes, _edges = await engine.get_graph_data()
    except Exception:
        logger.exception("get_graph_data failed while loading %s for user %s", node_type, user_id)
        return {}

    owned: dict[str, dict] = {}
    for entry in nodes:
        nid, props = _node_props(entry)
        if props.get("type") == node_type and props.get("user_id") == user_id:
            owned[nid] = props
    return owned


async def _vector_rank(collection: str, query: str, limit: int) -> list[str]:
    """Node ids from `collection`, ordered by relevance to `query` (best effort)."""
    from cognee.infrastructure.databases.vector import get_vector_engine

    engine = get_vector_engine()  # sync factory -> handle
    try:
        results = await engine.search(collection_name=collection, query_text=query, limit=limit)
    except Exception:
        logger.warning("vector search failed for collection %s", collection, exc_info=True)
        return []
    return [str(r.id) for r in results]


async def _rank_and_build(
    owned: dict[str, dict],
    *,
    collection: str,
    query: str,
    top_k: int,
    to_record: Callable[[str, dict], dict],
) -> list[dict]:
    if not owned:
        return []

    try:
        ranked_ids = await asyncio.wait_for(
            _vector_rank(collection, query, _VECTOR_TOP_K), timeout=SEARCH_TIMEOUT
        )
    except asyncio.TimeoutError:
        ranked_ids = []

    ordered: list[dict] = []
    seen: set[str] = set()
    for nid in ranked_ids:
        if nid in owned and nid not in seen:
            ordered.append(to_record(nid, owned[nid]))
            seen.add(nid)
    if not ordered:
        # Vector search's global top_k didn't surface any of this user's ids
        # (crowded out by other users' records) — fall back to the owned set
        # unranked rather than returning nothing.
        ordered = [to_record(nid, props) for nid, props in owned.items()]
    return ordered[:top_k]


def _argument_record(node_id: str, props: dict) -> dict:
    return {
        "node_id": node_id,
        "text": props.get("summary", ""),
        "pattern_type": props.get("pattern_type"),
        "fallacy": props.get("fallacy"),
        "outcome": props.get("outcome"),
        "session_id": props.get("session_id"),
    }


def _fact_record(node_id: str, props: dict) -> dict:
    return {"node_id": node_id, "text": props.get("fact_text", "")}


async def recall_weaknesses(user_id: str, exclude_patterns: set[str] | None = None) -> list[dict]:
    t0 = time.monotonic()
    owned = await owned_nodes("ArgumentRecord", user_id)
    items = await _rank_and_build(
        owned,
        collection="ArgumentRecord_summary",
        query="fallacy weak evidence poor argument outcome lost",
        top_k=10,
        to_record=_argument_record,
    )
    items = filter_out_patterns(items, exclude_patterns)
    logger.info(
        "cognee.recall_weaknesses ok",
        extra={
            "event": "cognee.recall_weaknesses.ok",
            "user_id": user_id,
            "owned": len(owned),
            "results": len(items),
            "excluded_patterns": sorted(exclude_patterns) if exclude_patterns else [],
            "elapsed_ms": elapsed_ms(t0),
        },
    )
    logger.debug(
        "cognee.recall_weaknesses ok preview",
        extra={"results_preview": [preview(it["text"], 120) for it in items[:3]]},
    )
    return items


async def recall_topic_weaknesses(
    user_id: str, topic: str, exclude_patterns: set[str] | None = None
) -> list[dict]:
    t0 = time.monotonic()
    owned = await owned_nodes("ArgumentRecord", user_id)
    normalized_topic = topic.strip().lower()
    topic_owned = {
        nid: props
        for nid, props in owned.items()
        if (props.get("topic_name") or "").strip().lower() == normalized_topic
    }
    items = await _rank_and_build(
        topic_owned,
        collection="ArgumentRecord_summary",
        query=f"topic {topic} weak poor outcome lost needs improvement",
        top_k=5,
        to_record=_argument_record,
    )
    items = filter_out_patterns(items, exclude_patterns)
    logger.info(
        "cognee.recall_topic_weaknesses ok",
        extra={
            "event": "cognee.recall_topic_weaknesses.ok",
            "user_id": user_id,
            "topic": topic,
            "owned": len(topic_owned),
            "results": len(items),
            "elapsed_ms": elapsed_ms(t0),
        },
    )
    return items


async def recall_user_facts(user_id: str, topic: str = "") -> list[dict]:
    t0 = time.monotonic()
    owned = await owned_nodes("PersonalFact", user_id)
    query = (
        f"personal facts about the user relevant to {topic}: "
        "preferences, background, interests, dislikes, occupation"
        if topic
        else "personal facts about the user: preferences, background, interests, dislikes"
    )
    items = await _rank_and_build(
        owned, collection="PersonalFact_fact_text", query=query, top_k=5, to_record=_fact_record
    )
    logger.info(
        "cognee.recall_user_facts ok",
        extra={
            "event": "cognee.recall_user_facts.ok",
            "user_id": user_id,
            "topic": topic,
            "owned": len(owned),
            "results": len(items),
            "elapsed_ms": elapsed_ms(t0),
        },
    )
    return items
