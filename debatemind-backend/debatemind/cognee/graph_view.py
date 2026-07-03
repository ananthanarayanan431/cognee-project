"""Read-only view over Cognee's raw graph, scoped to one user, for the
knowledge-graph explorer panel (GET /api/users/me/knowledge-graph).

Distinct from debatemind/services/graph_svc.py, which derives a small,
mastery-colored fingerprint/brain graph from Postgres and powers the existing
gameplay UI (FingerprintGraph.tsx / BrainGraph.tsx) — this module instead
renders Cognee's actual entity graph: the typed nodes debatemind/cognee/schema.py
declares, plus whatever the cognify() LLM pass linked them to.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_LABEL_FIELDS = ("summary", "name", "fact_text", "claim_text", "user_id")
_TYPED_TYPES = {"UserProfile", "Topic", "ArgumentRecord", "SessionSummary", "PersonalFact"}
# Node types cognee's prose pipeline (add() -> cognify()) writes. Historically
# these carried NO user_id property, so the ownership filter below matched none
# of them and the panel rendered empty even after many sessions. They are
# rendered as themselves (not folded to a generic "Node") so the explorer can
# color the LLM-derived entity web distinctly from the typed anchors.
_COGNIFY_TYPES = {"Entity", "EntityType", "DocumentChunk", "TextDocument", "TextSummary"}
_RENDERED_TYPES = _TYPED_TYPES | _COGNIFY_TYPES


def _node_props(entry: Any) -> tuple[str, dict]:
    if isinstance(entry, tuple):
        nid, props = entry[0], entry[1]
    else:
        props, nid = entry, entry.get("id")
    return str(nid), dict(props or {})


def _edge_parts(entry: Any) -> tuple[str, str, str]:
    if isinstance(entry, tuple):
        src = str(entry[0]) if len(entry) > 0 else ""
        tgt = str(entry[1]) if len(entry) > 1 else ""
        label = str(entry[2]) if len(entry) > 2 else ""
        return src, tgt, label
    if isinstance(entry, dict):
        return (
            str(entry.get("source", "")),
            str(entry.get("target", "")),
            str(entry.get("label", "")),
        )
    return "", "", ""


def _truncate(text: str) -> str:
    text = text.strip()
    return text if len(text) <= 60 else text[:57] + "…"


def _chunk_label(text: str) -> str:
    """A readable label for a prose DocumentChunk/TextSummary.

    The prose fingerprint.py writes starts with a "User:/Session:" header a
    human never wants to see — surface the Topic line instead, falling back to
    the first line that isn't part of that machine header."""
    topic = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Topic:"):
            topic = stripped[len("Topic:") :].strip()
            break
        if stripped and not stripped.startswith(("User:", "Session:")):
            topic = topic or stripped
    return _truncate(topic) if topic else "Debate excerpt"


def _label(node_type: str, props: dict) -> str:
    if node_type in {"DocumentChunk", "TextSummary"}:
        text = props.get("text")
        if text:
            return _chunk_label(str(text))
    if node_type == "TextDocument":
        return "Debate transcript"
    for field in _LABEL_FIELDS:
        val = props.get(field)
        if val:
            return _truncate(str(val))
    return node_type


def _safe_props(props: dict) -> dict:
    return {k: v for k, v in props.items() if k != "embedding"}


def _owns(props: dict, user_id: str, marker: str) -> bool:
    """Whether this node anchors the given user.

    Two independent anchors, because cognee stores the same user's data in two
    disconnected subgraphs (see debatemind/cognee/schema.py):
      1. typed add_data_points() nodes carry an explicit `user_id` property;
      2. cognify's prose nodes (DocumentChunk) carry no property at all — the
         user id lives only inside the chunk text as a "User: {uid}" line
         (fingerprint.py writes every record with that header).
    Seeding off only (1) is what left the panel empty for users whose sessions
    produced prose but no typed nodes.
    """
    if props.get("user_id") == user_id:
        return True
    if props.get("type") == "DocumentChunk" and marker in str(props.get("text", "")):
        return True
    return False


async def user_graph_view(user_id: str, limit: int = 400) -> dict:
    """{nodes, edges} for this user: their owned nodes (typed nodes by `user_id`
    property, plus cognify DocumentChunks whose text bears the "User: {uid}"
    marker), plus any node one edge hop away from one of them — which pulls in
    the cognify-derived entity web (entities, types, transcripts) that carries
    no ownership property of its own but is linked to the owned chunks."""
    from cognee.infrastructure.databases.graph import get_graph_engine

    try:
        engine = await get_graph_engine()
        raw_nodes, raw_edges = await engine.get_graph_data()
    except Exception:
        logger.exception("get_graph_data failed for user %s", user_id)
        return {"nodes": [], "edges": [], "error": "graph unavailable"}

    all_nodes: dict[str, dict] = {}
    for entry in raw_nodes:
        nid, props = _node_props(entry)
        all_nodes[nid] = props

    marker = f"User: {user_id}"
    owned_ids = {nid for nid, props in all_nodes.items() if _owns(props, user_id, marker)}

    # Expand only outward from owned seeds (never from the neighbours), so shared
    # cognify hubs — a common EntityType, an entity named "none" — can be shown
    # but can't bridge back into another user's chunks. Keeps isolation intact.
    edges = [_edge_parts(e) for e in raw_edges]
    adjacent_ids: set[str] = set()
    for src, tgt, _lbl in edges:
        if src in owned_ids:
            adjacent_ids.add(tgt)
        if tgt in owned_ids:
            adjacent_ids.add(src)

    included_ids = (owned_ids | adjacent_ids) & set(all_nodes.keys())

    nodes_out = []
    for nid in list(included_ids)[:limit]:
        props = all_nodes[nid]
        node_type = str(props.get("type") or "Node")
        nodes_out.append(
            {
                "id": nid,
                "label": _label(node_type, props),
                "type": node_type if node_type in _RENDERED_TYPES else "Node",
                "props": _safe_props(props),
            }
        )

    included_set = {n["id"] for n in nodes_out}
    edges_out = [
        {"source": src, "target": tgt, "label": lbl}
        for src, tgt, lbl in edges
        if src in included_set and tgt in included_set
    ]

    return {"nodes": nodes_out, "edges": edges_out}
