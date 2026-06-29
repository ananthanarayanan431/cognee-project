from pydantic import BaseModel


class GraphNode(BaseModel):
    id: str
    label: str
    type: str        # weakness | strength | mastered | topic
    weight: float


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
