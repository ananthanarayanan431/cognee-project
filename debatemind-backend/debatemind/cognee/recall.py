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
from collections import Counter
from typing import Any, Callable

from debatemind.cognee._base import (
    SEARCH_TIMEOUT,
    classify_entity,
    elapsed_ms,
    filter_out_patterns,
    preview,
)

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


def _edge_parts(entry: Any) -> tuple[str, str]:
    """Normalize a get_graph_data() edge entry to (source_id, target_id).

    Matches graph_view.py's (src, tgt, label) convention; we only need the
    endpoints here to walk one hop out from an owned record.
    """
    if isinstance(entry, tuple):
        src = str(entry[0]) if len(entry) > 0 else ""
        tgt = str(entry[1]) if len(entry) > 1 else ""
        return src, tgt
    if isinstance(entry, dict):
        return str(entry.get("source", "")), str(entry.get("target", ""))
    return "", ""


async def _load_graph() -> tuple[dict[str, dict], list[tuple[str, str]]]:
    """The whole graph once: ({node_id: props}, [(src, tgt), ...]).

    A single get_graph_data() call feeds both ownership filtering and the
    one-hop neighbour walk, so a recall never loads the graph twice. Returns
    empty structures (never raises) so a storage hiccup degrades recall to
    "no memory" instead of aborting the debate turn.
    """
    from cognee.infrastructure.databases.graph import get_graph_engine

    try:
        engine = await get_graph_engine()
        raw_nodes, raw_edges = await engine.get_graph_data()
    except Exception:
        logger.exception("get_graph_data failed")
        return {}, []

    nodes_by_id: dict[str, dict] = {}
    for entry in raw_nodes:
        nid, props = _node_props(entry)
        nodes_by_id[nid] = props
    edges = [_edge_parts(e) for e in raw_edges]
    return nodes_by_id, edges


def _owned(nodes_by_id: dict[str, dict], node_type: str, user_id: str) -> dict[str, dict]:
    return {
        nid: props
        for nid, props in nodes_by_id.items()
        if props.get("type") == node_type and props.get("user_id") == user_id
    }


async def owned_nodes(node_type: str, user_id: str) -> dict[str, dict]:
    """All graph nodes of `node_type` owned by `user_id`, keyed by node id."""
    nodes_by_id, _edges = await _load_graph()
    return _owned(nodes_by_id, node_type, user_id)


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


# --------------------------------------------------------------------------
# Cognitive profile — the graph-aware layer. recall_weaknesses() above returns
# the prose summaries; this aggregates the *typed* signal across all of a
# user's records. Two sources, same user_id ownership filter as the rest of
# this module:
#
#   Layer 1 (structured fields on the owned ArgumentRecord: fallacy, outcome,
#     topic_name) — always available. This is what powers recurring_fallacies
#     and weak_domains today.
#
#   Layer 2 (ontology entities cognify() extracted — CognitiveBias,
#     ReasoningApproach, EvidenceType) reached by a one-hop walk out of the
#     record. NOTE: in the pinned cognee, add_data_points()'s typed nodes and
#     cognify()'s prose-derived Entity graph are SEPARATE subgraphs — a typed
#     ArgumentRecord's only edges are its typed Topic/UserProfile links, so
#     this walk currently surfaces nothing extra. The code is kept because it
#     is isolation-safe and lights up for free if the two graphs are ever
#     bridged (e.g. a memify pass linking records to their extracted entities);
#     until then biases/reasoning/evidence_types come back empty by design.

_WEAK_EVIDENCE = {"Weak", "Absent"}


def _neighbour_ids(edges: list[tuple[str, str]], owned_ids: set[str]) -> dict[str, set[str]]:
    """One-hop undirected adjacency, restricted to owned records as endpoints."""
    adj: dict[str, set[str]] = {nid: set() for nid in owned_ids}
    for src, tgt in edges:
        if src in owned_ids and tgt:
            adj[src].add(tgt)
        if tgt in owned_ids and src:
            adj[tgt].add(src)
    return adj


async def recall_cognitive_profile(user_id: str, topic: str = "") -> dict:
    """Aggregate typed cognitive signal across this user's ArgumentRecords.

    Weighted toward Lost outcomes (a weakness that cost a debate matters more
    than one that didn't). Returns raw counts-derived lists; mastered-pattern
    exclusion is applied by the caller via filter_profile_patterns() so the
    result stays cacheable and mastery takes effect on the very next turn
    (mirrors how recall_weaknesses() is cached raw in opponent.py).
    """
    t0 = time.monotonic()
    nodes_by_id, edges = await _load_graph()
    owned = _owned(nodes_by_id, "ArgumentRecord", user_id)
    if topic:
        normalized_topic = topic.strip().lower()
        owned = {
            nid: props
            for nid, props in owned.items()
            if (props.get("topic_name") or "").strip().lower() == normalized_topic
        }

    fallacies: Counter = Counter()
    reasoning: Counter = Counter()
    biases: Counter = Counter()
    evidence_types: Counter = Counter()
    weak_domains: Counter = Counter()

    adj = _neighbour_ids(edges, set(owned))
    for nid, props in owned.items():
        lost = props.get("outcome") == "Lost"
        weight = 2 if lost else 1

        # Layer 1 — structured fields already on the owned record (reliable).
        hit = classify_entity(props.get("fallacy"))
        if hit and hit[0] == "fallacy":
            fallacies[hit[1]] += weight
        if lost:
            domain = (props.get("topic_name") or "").strip()
            if domain:
                weak_domains[domain] += 1

        # Layer 2 — cognify's ontology neighbours (best-effort, graph-derived).
        for neighbour_id in adj.get(nid, ()):
            neighbour = nodes_by_id.get(neighbour_id) or {}
            hit = classify_entity(neighbour.get("name") or neighbour.get("summary"))
            if not hit:
                continue
            category, canonical = hit
            if category == "fallacy":
                fallacies[canonical] += weight
            elif category == "reasoning":
                reasoning[canonical] += weight
            elif category == "bias":
                biases[canonical] += weight
            elif category == "evidence_type":
                evidence_types[canonical] += weight

    profile = {
        "record_count": len(owned),
        "recurring_fallacies": [name for name, _ in fallacies.most_common(4)],
        "cognitive_biases": [name for name, _ in biases.most_common(3)],
        "reasoning_approaches": [name for name, _ in reasoning.most_common(3)],
        "evidence_types": [name for name, _ in evidence_types.most_common(3)],
        "weak_domains": [name for name, _ in weak_domains.most_common(3)],
    }
    logger.info(
        "cognee.recall_cognitive_profile ok",
        extra={
            "event": "cognee.recall_cognitive_profile.ok",
            "user_id": user_id,
            "topic": topic,
            "owned": len(owned),
            "fallacies": profile["recurring_fallacies"],
            "biases": profile["cognitive_biases"],
            "reasoning": profile["reasoning_approaches"],
            "elapsed_ms": elapsed_ms(t0),
        },
    )
    return profile


def filter_profile_patterns(profile: dict, exclude_patterns: set[str] | None) -> dict:
    """Drop mastered patterns from a profile's recurring_fallacies list.

    Only fallacies are pattern-typed (StrawMan, AdHominem…); biases, reasoning,
    and domains are never mastered away, so they pass through untouched. Returns
    a shallow copy — the cached raw profile is never mutated.
    """
    if not exclude_patterns:
        return profile
    return {
        **profile,
        "recurring_fallacies": [
            f for f in profile.get("recurring_fallacies", []) if f not in exclude_patterns
        ],
    }


def cognitive_profile_text(profile: dict) -> str:
    """One compact line of the profile for a system prompt, or "" if empty.

    Returning "" lets the consumer omit the whole prompt block for a user with
    no recorded history, rather than injecting an empty scaffold.
    """
    if not profile or not profile.get("record_count"):
        return ""
    parts: list[str] = []
    if profile.get("recurring_fallacies"):
        parts.append("recurring fallacies: " + ", ".join(profile["recurring_fallacies"]))
    if profile.get("cognitive_biases"):
        parts.append("cognitive biases: " + ", ".join(profile["cognitive_biases"]))
    if profile.get("reasoning_approaches"):
        parts.append("leans on reasoning: " + ", ".join(profile["reasoning_approaches"]))
    if profile.get("evidence_types"):
        parts.append("typical evidence: " + ", ".join(profile["evidence_types"]))
    if profile.get("weak_domains"):
        parts.append("weakest on topics: " + ", ".join(profile["weak_domains"]))
    return "; ".join(parts)
