"""
Unit tests for debatemind.cognee.graph_view.user_graph_view — the ownership +
one-hop-adjacency filter that scopes the global Cognee graph to one user for
the knowledge-graph explorer panel. get_graph_engine() is mocked.
"""

from unittest.mock import AsyncMock, patch

from debatemind.cognee.graph_view import user_graph_view


class _FakeGraphEngine:
    def __init__(self, nodes, edges):
        self._nodes = nodes
        self._edges = edges

    async def get_graph_data(self):
        return self._nodes, self._edges


def _patched(nodes, edges):
    return patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(return_value=_FakeGraphEngine(nodes, edges)),
    )


async def test_includes_owned_nodes():
    nodes = [("a", {"id": "a", "type": "ArgumentRecord", "user_id": "u1", "summary": "s"})]
    with _patched(nodes, []):
        result = await user_graph_view("u1")

    assert [n["id"] for n in result["nodes"]] == ["a"]
    assert result["nodes"][0]["type"] == "ArgumentRecord"
    assert result["nodes"][0]["label"] == "s"


async def test_excludes_other_users_unconnected_nodes():
    nodes = [
        ("a", {"id": "a", "type": "ArgumentRecord", "user_id": "u1", "summary": "mine"}),
        ("b", {"id": "b", "type": "ArgumentRecord", "user_id": "u2", "summary": "not mine"}),
    ]
    with _patched(nodes, []):
        result = await user_graph_view("u1")

    assert [n["id"] for n in result["nodes"]] == ["a"]


async def test_includes_cognify_derived_entity_one_hop_from_owned_node():
    nodes = [
        ("a", {"id": "a", "type": "ArgumentRecord", "user_id": "u1", "summary": "mine"}),
        ("e", {"id": "e", "type": "Entity", "name": "SlipperySlope"}),  # no user_id
    ]
    edges = [("a", "e", "mentions")]
    with _patched(nodes, edges):
        result = await user_graph_view("u1")

    ids = {n["id"] for n in result["nodes"]}
    assert ids == {"a", "e"}
    entity = next(n for n in result["nodes"] if n["id"] == "e")
    assert entity["type"] == "Node"  # untyped/cognify-derived, not one of our schema classes
    assert entity["label"] == "SlipperySlope"


async def test_excludes_entities_not_connected_to_any_owned_node():
    nodes = [
        ("a", {"id": "a", "type": "ArgumentRecord", "user_id": "u1", "summary": "mine"}),
        ("f", {"id": "f", "type": "Entity", "name": "unrelated"}),
    ]
    with _patched(nodes, []):
        result = await user_graph_view("u1")

    assert {n["id"] for n in result["nodes"]} == {"a"}


async def test_edges_only_included_when_both_endpoints_present():
    nodes = [
        ("a", {"id": "a", "type": "ArgumentRecord", "user_id": "u1", "summary": "mine"}),
        ("b", {"id": "b", "type": "ArgumentRecord", "user_id": "u2", "summary": "not mine"}),
    ]
    edges = [("a", "b", "unrelated_edge")]
    with _patched(nodes, edges):
        result = await user_graph_view("u1")

    # b is not owned and not reachable from an owned node via any OTHER edge,
    # but this edge itself makes b adjacent to a — so b is included, and the
    # edge is included too (adjacency inheritance is intentionally one-hop-open).
    assert {n["id"] for n in result["nodes"]} == {"a", "b"}
    assert result["edges"] == [{"source": "a", "target": "b", "label": "unrelated_edge"}]


async def test_returns_empty_on_graph_engine_failure():
    with patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await user_graph_view("u1")

    assert result["nodes"] == []
    assert result["edges"] == []
    assert "error" in result


async def test_drops_embedding_property_from_output():
    nodes = [
        (
            "a",
            {
                "id": "a",
                "type": "ArgumentRecord",
                "user_id": "u1",
                "summary": "mine",
                "embedding": [0.1, 0.2],
            },
        )
    ]
    with _patched(nodes, []):
        result = await user_graph_view("u1")

    assert "embedding" not in result["nodes"][0]["props"]
