from collections import Counter

from sqlalchemy import select

from debatemind.agents.constants import PATTERN_TYPES
from debatemind.database import AsyncSessionLocal
from debatemind.models.session import DebateSession, Exchange
from debatemind.schemas.graph import GraphEdge, GraphNode, GraphOut

_VALID_PATTERNS = set(PATTERN_TYPES)


async def build_graph(user_id: str, topic: str) -> GraphOut:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Exchange.detected_pattern, Exchange.outcome)
            .join(DebateSession, Exchange.session_id == DebateSession.id)
            .where(DebateSession.user_id == user_id)
            .where(DebateSession.topic == topic)
            .where(Exchange.detected_pattern.is_not(None))
            .order_by(Exchange.created_at.desc())
        )
        rows = result.fetchall()

    pattern_counts: Counter[str] = Counter()
    pattern_wins: Counter[str] = Counter()

    for detected_pattern, outcome in rows:
        if detected_pattern in _VALID_PATTERNS:
            pattern_counts[detected_pattern] += 1
            if outcome == "Won":
                pattern_wins[detected_pattern] += 1

    if not pattern_counts:
        return GraphOut(nodes=[], edges=[])

    total = sum(pattern_counts.values())
    nodes: list[GraphNode] = [GraphNode(id="topic", label=topic[:20], type="topic", weight=1.0)]
    edges: list[GraphEdge] = []

    for pattern, count in pattern_counts.most_common(8):
        weight = round(min(count / total * 3, 0.95), 2)
        win_rate = pattern_wins[pattern] / count
        node_type = "strength" if win_rate >= 0.5 else "weakness"
        nodes.append(GraphNode(id=pattern, label=pattern, type=node_type, weight=weight))
        edges.append(GraphEdge(source="topic", target=pattern, weight=weight))

    return GraphOut(nodes=nodes, edges=edges)
