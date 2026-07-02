"""
Unit tests for schemas.graph — verifies GraphNode/GraphEdge/GraphOut enforce
required fields and serialize the way the frontend graph viewer expects.
"""

import pytest
from pydantic import ValidationError

from debatemind.schemas.graph import GraphEdge, GraphNode, GraphOut


def test_graph_node_requires_all_fields():
    with pytest.raises(ValidationError):
        GraphNode(id="topic", label="Topic")


def test_graph_node_round_trips_through_model_dump():
    node = GraphNode(id="StrawMan", label="StrawMan", type="weakness", weight=0.9)

    assert node.model_dump() == {
        "id": "StrawMan",
        "label": "StrawMan",
        "type": "weakness",
        "weight": 0.9,
    }


def test_graph_edge_requires_all_fields():
    with pytest.raises(ValidationError):
        GraphEdge(source="topic")


def test_graph_edge_round_trips_through_model_dump():
    edge = GraphEdge(source="topic", target="StrawMan", weight=0.9)

    assert edge.model_dump() == {"source": "topic", "target": "StrawMan", "weight": 0.9}


def test_graph_out_serializes_nodes_and_edges_lists():
    graph = GraphOut(
        nodes=[GraphNode(id="topic", label="Topic", type="topic", weight=1.0)],
        edges=[],
    )

    dumped = graph.model_dump()
    assert dumped["nodes"] == [{"id": "topic", "label": "Topic", "type": "topic", "weight": 1.0}]
    assert dumped["edges"] == []


def test_graph_out_defaults_are_not_provided_and_must_be_explicit():
    with pytest.raises(ValidationError):
        GraphOut()
