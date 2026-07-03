"""Root -> topic -> argument-pattern "brain map", sourced from Cognee's Neo4j
graph (GET /api/users/me/brain).

Previously this view was derived from Postgres (Exchange rows + MasteryLog) by
debatemind/services/graph_svc.py. It now reads the typed ArgumentRecord nodes
add_data_points() writes to the graph (debatemind/cognee/schema.py), so the
brain map and the raw knowledge-graph explorer share one source of truth — the
Cognee memory layer.

Two deliberate consequences of dropping Postgres:
  * strength/weakness is derived from win-rate over each record's `outcome`
    ("Won" vs everything else), not the judge-score average the Postgres view
    used — ArgumentRecord carries no judge scores.
  * there is no `mastered` tier. MASTERED is a Postgres MasteryLog concept the
    graph has no queryable equivalent for.

Like graph_view.py, the graph store is global across users, so every read MUST
filter ArgumentRecords on their explicit `user_id` property.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict

from debatemind.cognee.graph_view import _node_props

logger = logging.getLogger(__name__)

_MAX_PATTERNS_PER_TOPIC = 6


def _topic_id(topic: str) -> str:
    return "t_" + hashlib.md5(topic.encode()).hexdigest()[:8]


async def user_brain_graph(user_id: str) -> dict:
    """{nodes, edges} mastery graph for this user, built from their Neo4j
    ArgumentRecord nodes. Empty ({nodes: [], edges: []}) when the user has no
    argument records yet or the graph engine is unavailable."""
    from cognee.infrastructure.databases.graph import get_graph_engine

    try:
        engine = await get_graph_engine()
        raw_nodes, _raw_edges = await engine.get_graph_data()
    except Exception:
        logger.exception("get_graph_data failed for user %s", user_id)
        return {"nodes": [], "edges": [], "error": "graph unavailable"}

    # (topic, pattern) -> [count, wins]; ordered by first appearance so the
    # output is deterministic given a stable node order from the engine.
    tallies: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for entry in raw_nodes:
        _nid, props = _node_props(entry)
        if props.get("type") != "ArgumentRecord" or props.get("user_id") != user_id:
            continue
        topic = str(props.get("topic_name") or "").strip()
        pattern = str(props.get("pattern_type") or "").strip()
        if not topic or not pattern:
            continue
        tally = tallies[(topic, pattern)]
        tally[0] += 1
        if props.get("outcome") == "Won":
            tally[1] += 1

    if not tallies:
        return {"nodes": [], "edges": []}

    # Per topic, keep the most-argued patterns first, capped like the Postgres view.
    by_topic: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for (topic, pattern), (count, wins) in tallies.items():
        by_topic[topic].append((pattern, count, wins))

    nodes: list[dict] = [{"id": "brain", "label": "Brain", "type": "root", "weight": 1.0}]
    edges: list[dict] = []

    for topic in sorted(by_topic):
        tid = _topic_id(topic)
        nodes.append({"id": tid, "label": topic, "type": "topic", "weight": 0.9})
        edges.append({"source": "brain", "target": tid, "weight": 0.8})

        patterns = sorted(by_topic[topic], key=lambda pc: pc[1], reverse=True)
        for pattern, count, wins in patterns[:_MAX_PATTERNS_PER_TOPIC]:
            win_rate = wins / count if count else 0.0
            node_type = "strength" if win_rate >= 0.5 else "weakness"
            weight = round(min(0.9, 0.3 + count * 0.1), 2)
            pid = f"{tid}_{pattern}"
            nodes.append({"id": pid, "label": pattern, "type": node_type, "weight": weight})
            edges.append({"source": tid, "target": pid, "weight": weight})

    return {"nodes": nodes, "edges": edges}
