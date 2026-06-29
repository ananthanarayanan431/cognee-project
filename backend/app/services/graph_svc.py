from app.services.cognee_svc import recall_weaknesses
from app.schemas.graph import GraphOut, GraphNode, GraphEdge


async def build_graph(user_id: str, topic: str) -> GraphOut:
    """Build a D3-ready graph from Cognee recall results."""
    results = await recall_weaknesses(user_id)
    nodes: list[GraphNode] = [
        GraphNode(id="topic", label=topic[:20], type="topic", weight=1.0)
    ]
    edges: list[GraphEdge] = []
    seen = set()
    for i, r in enumerate(results[:8]):
        text = r.get("text", "")
        # Heuristically extract pattern names from Cognee recall text
        for pattern in [
            "AppealToAuthority", "StrawMan", "AdHominem", "SlipperySlope",
            "FalseEquivalence", "EmotionalAppeal", "AnecdotalEvidence",
            "EvidenceBased", "Concession",
        ]:
            if pattern.lower() in text.lower() and pattern not in seen:
                seen.add(pattern)
                weight = round(0.9 - i * 0.1, 2)
                node_type = "weakness" if weight > 0.5 else "strength"
                nodes.append(GraphNode(id=pattern, label=pattern, type=node_type, weight=weight))
                edges.append(GraphEdge(source="topic", target=pattern, weight=weight))
                break
    return GraphOut(nodes=nodes, edges=edges)
