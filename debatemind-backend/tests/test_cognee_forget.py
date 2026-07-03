"""
Unit tests for debatemind.cognee.forget — real graph-node + vector-embedding
deletion. get_graph_engine()/get_vector_engine()/recall.owned_nodes are
mocked; no real Cognee storage calls happen here.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from debatemind.cognee.forget import forget_pattern, forget_personal_fact


async def test_forget_pattern_deletes_matching_argument_records():
    owned = {
        "id-a": {"type": "ArgumentRecord", "user_id": "u1", "pattern_type": "StrawMan"},
        "id-b": {"type": "ArgumentRecord", "user_id": "u1", "pattern_type": "AdHominem"},
    }
    graph_engine = MagicMock()
    graph_engine.delete_nodes = AsyncMock()
    vector_engine = MagicMock()
    vector_engine.delete_data_points = AsyncMock()

    with (
        patch("debatemind.cognee.forget.owned_nodes", new=AsyncMock(return_value=owned)),
        patch(
            "cognee.infrastructure.databases.graph.get_graph_engine",
            new=AsyncMock(return_value=graph_engine),
        ),
        patch(
            "cognee.infrastructure.databases.vector.get_vector_engine",
            return_value=vector_engine,
        ),
    ):
        await forget_pattern("u1", "StrawMan")

    graph_engine.delete_nodes.assert_awaited_once_with(["id-a"])
    vector_engine.delete_data_points.assert_awaited_once_with("ArgumentRecord_summary", ["id-a"])


async def test_forget_pattern_noop_when_nothing_matches():
    graph_engine = MagicMock()
    graph_engine.delete_nodes = AsyncMock()

    with (
        patch("debatemind.cognee.forget.owned_nodes", new=AsyncMock(return_value={})),
        patch(
            "cognee.infrastructure.databases.graph.get_graph_engine",
            new=AsyncMock(return_value=graph_engine),
        ),
    ):
        await forget_pattern("u1", "StrawMan")

    graph_engine.delete_nodes.assert_not_awaited()


async def test_forget_pattern_vector_delete_failure_does_not_raise():
    owned = {"id-a": {"type": "ArgumentRecord", "user_id": "u1", "pattern_type": "StrawMan"}}
    graph_engine = MagicMock()
    graph_engine.delete_nodes = AsyncMock()
    vector_engine = MagicMock()
    vector_engine.delete_data_points = AsyncMock(side_effect=RuntimeError("boom"))

    with (
        patch("debatemind.cognee.forget.owned_nodes", new=AsyncMock(return_value=owned)),
        patch(
            "cognee.infrastructure.databases.graph.get_graph_engine",
            new=AsyncMock(return_value=graph_engine),
        ),
        patch(
            "cognee.infrastructure.databases.vector.get_vector_engine",
            return_value=vector_engine,
        ),
    ):
        await forget_pattern("u1", "StrawMan")  # must not raise

    graph_engine.delete_nodes.assert_awaited_once_with(["id-a"])


async def test_forget_personal_fact_deletes_owned_fact():
    owned = {"id-a": {"type": "PersonalFact", "user_id": "u1", "fact_text": "I'm a nurse"}}
    graph_engine = MagicMock()
    graph_engine.delete_nodes = AsyncMock()
    vector_engine = MagicMock()
    vector_engine.delete_data_points = AsyncMock()

    with (
        patch("debatemind.cognee.forget.owned_nodes", new=AsyncMock(return_value=owned)),
        patch(
            "cognee.infrastructure.databases.graph.get_graph_engine",
            new=AsyncMock(return_value=graph_engine),
        ),
        patch(
            "cognee.infrastructure.databases.vector.get_vector_engine",
            return_value=vector_engine,
        ),
    ):
        result = await forget_personal_fact("u1", "id-a")

    assert result == {"node_id": "id-a", "status": "forgotten"}
    graph_engine.delete_nodes.assert_awaited_once_with(["id-a"])
    vector_engine.delete_data_points.assert_awaited_once_with("PersonalFact_fact_text", ["id-a"])


async def test_forget_personal_fact_returns_not_found_for_unowned_node():
    with patch("debatemind.cognee.forget.owned_nodes", new=AsyncMock(return_value={})):
        result = await forget_personal_fact("u1", "someone-elses-node")

    assert result == {"node_id": "someone-elses-node", "status": "not_found"}
