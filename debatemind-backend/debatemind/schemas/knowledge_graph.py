from typing import Any

from pydantic import BaseModel


class KnowledgeGraphNode(BaseModel):
    id: str
    label: str
    type: str
    props: dict[str, Any]


class KnowledgeGraphEdge(BaseModel):
    source: str
    target: str
    label: str


class KnowledgeGraphOut(BaseModel):
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]
