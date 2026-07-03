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


def _label(node_type: str, props: dict) -> str:
    for field in _LABEL_FIELDS:
        val = props.get(field)
        if val:
            text = str(val)
            return text if len(text) <= 60 else text[:57] + "…"
    return node_type


def _safe_props(props: dict) -> dict:
    return {k: v for k, v in props.items() if k != "embedding"}


async def user_graph_view(user_id: str, limit: int = 400) -> dict:
    """{nodes, edges} for this user: owned typed nodes, plus any node one edge
    hop away from one of them (covers cognify-derived generic entities, which
    carry no `user_id` property of their own)."""
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

    owned_ids = {nid for nid, props in all_nodes.items() if props.get("user_id") == user_id}

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
                "type": node_type if node_type in _TYPED_TYPES else "Node",
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
