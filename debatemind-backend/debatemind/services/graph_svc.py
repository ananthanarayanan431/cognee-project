from debatemind.agents.constants import PATTERN_TYPES
from debatemind.cognee import recall_weaknesses
from debatemind.schemas.graph import GraphEdge, GraphNode, GraphOut


async def build_graph(user_id: str, topic: str) -> GraphOut:
    results = await recall_weaknesses(user_id)
    nodes: list[GraphNode] = [GraphNode(id="topic", label=topic[:20], type="topic", weight=1.0)]
    edges: list[GraphEdge] = []
    seen: set[str] = set()

    for i, r in enumerate(results[:8]):
        text = r.get("text", "")
        for pattern in PATTERN_TYPES:
            if pattern.lower() in text.lower() and pattern not in seen:
                seen.add(pattern)
                weight = round(0.9 - i * 0.1, 2)
                nodes.append(
                    GraphNode(
                        id=pattern,
                        label=pattern,
                        type="weakness" if weight > 0.5 else "strength",
                        weight=weight,
                    )
                )
                edges.append(GraphEdge(source="topic", target=pattern, weight=weight))
                break

    return GraphOut(nodes=nodes, edges=edges)
