"""
Unit tests for debatemind.cognee.recall — the graph+vector join that replaced
SearchType.CHUNKS search. get_graph_engine()/get_vector_engine() are mocked;
no real Cognee storage/LLM calls happen here.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from debatemind.cognee.recall import (
    owned_nodes,
    recall_topic_weaknesses,
    recall_user_facts,
    recall_weaknesses,
)


def _node(node_type: str, **props):
    return (str(uuid4()), {"type": node_type, **props})


class _FakeGraphEngine:
    def __init__(self, nodes):
        self._nodes = nodes

    async def get_graph_data(self):
        return self._nodes, []


class _FakeScoredResult:
    def __init__(self, node_id: str):
        self.id = node_id


def _patch_graph_engine(monkeypatch, nodes):
    async def fake_get_graph_engine():
        return _FakeGraphEngine(nodes)

    monkeypatch.setattr(
        "cognee.infrastructure.databases.graph.get_graph_engine", fake_get_graph_engine
    )


def _patch_vector_engine(monkeypatch, ranked_ids):
    fake_engine = MagicMock()
    fake_engine.search = AsyncMock(return_value=[_FakeScoredResult(i) for i in ranked_ids])
    monkeypatch.setattr(
        "cognee.infrastructure.databases.vector.get_vector_engine", lambda: fake_engine
    )
    return fake_engine


async def test_owned_nodes_filters_by_type_and_user_id():
    u1_id, u1_node = _node("ArgumentRecord", user_id="u1", pattern_type="StrawMan")
    u2_id, u2_node = _node("ArgumentRecord", user_id="u2", pattern_type="StrawMan")
    topic_id_, topic_node = _node("Topic", user_id="u1", name="AI")
    engine = _FakeGraphEngine([(u1_id, u1_node), (u2_id, u2_node), (topic_id_, topic_node)])

    with patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(return_value=engine),
    ):
        result = await owned_nodes("ArgumentRecord", "u1")

    assert result == {u1_id: u1_node}


async def test_recall_weaknesses_ranks_by_vector_search(monkeypatch):
    id_a, node_a = _node(
        "ArgumentRecord", user_id="u1", pattern_type="StrawMan", summary="straw man summary"
    )
    id_b, node_b = _node(
        "ArgumentRecord", user_id="u1", pattern_type="AdHominem", summary="ad hominem summary"
    )
    _patch_graph_engine(monkeypatch, [(id_a, node_a), (id_b, node_b)])
    _patch_vector_engine(monkeypatch, [id_b, id_a])

    results = await recall_weaknesses("u1")

    assert [r["text"] for r in results] == ["ad hominem summary", "straw man summary"]
    assert [r["pattern_type"] for r in results] == ["AdHominem", "StrawMan"]


async def test_recall_weaknesses_excludes_mastered_patterns(monkeypatch):
    id_a, node_a = _node(
        "ArgumentRecord", user_id="u1", pattern_type="StrawMan", summary="straw man summary"
    )
    id_b, node_b = _node(
        "ArgumentRecord", user_id="u1", pattern_type="AdHominem", summary="ad hominem summary"
    )
    _patch_graph_engine(monkeypatch, [(id_a, node_a), (id_b, node_b)])
    _patch_vector_engine(monkeypatch, [id_a, id_b])

    results = await recall_weaknesses("u1", exclude_patterns={"StrawMan"})

    assert [r["text"] for r in results] == ["ad hominem summary"]


async def test_recall_weaknesses_isolates_by_user_id(monkeypatch):
    id_a, node_a = _node("ArgumentRecord", user_id="u1", pattern_type="StrawMan", summary="mine")
    id_b, node_b = _node(
        "ArgumentRecord", user_id="u2", pattern_type="StrawMan", summary="not mine"
    )
    _patch_graph_engine(monkeypatch, [(id_a, node_a), (id_b, node_b)])
    _patch_vector_engine(monkeypatch, [id_b, id_a])

    results = await recall_weaknesses("u1")

    assert [r["text"] for r in results] == ["mine"]


async def test_recall_weaknesses_falls_back_to_unranked_when_vector_search_misses(monkeypatch):
    id_a, node_a = _node(
        "ArgumentRecord", user_id="u1", pattern_type="StrawMan", summary="only record"
    )
    _patch_graph_engine(monkeypatch, [(id_a, node_a)])
    # Vector search returns ids that don't belong to this user (crowded out globally).
    _patch_vector_engine(monkeypatch, [str(uuid4())])

    results = await recall_weaknesses("u1")

    assert [r["text"] for r in results] == ["only record"]


async def test_recall_weaknesses_returns_empty_when_nothing_owned(monkeypatch):
    _patch_graph_engine(monkeypatch, [])
    vector_engine = _patch_vector_engine(monkeypatch, [])

    results = await recall_weaknesses("u1")

    assert results == []
    vector_engine.search.assert_not_awaited()


async def test_recall_topic_weaknesses_filters_by_topic_name(monkeypatch):
    id_a, node_a = _node(
        "ArgumentRecord",
        user_id="u1",
        pattern_type="StrawMan",
        topic_name="AI Safety",
        summary="about AI",
    )
    id_b, node_b = _node(
        "ArgumentRecord",
        user_id="u1",
        pattern_type="AdHominem",
        topic_name="Climate Policy",
        summary="about climate",
    )
    _patch_graph_engine(monkeypatch, [(id_a, node_a), (id_b, node_b)])
    _patch_vector_engine(monkeypatch, [id_a])

    results = await recall_topic_weaknesses("u1", "AI Safety")

    assert [r["text"] for r in results] == ["about AI"]


async def test_recall_topic_weaknesses_is_case_insensitive(monkeypatch):
    id_a, node_a = _node(
        "ArgumentRecord",
        user_id="u1",
        pattern_type="StrawMan",
        topic_name="AI Safety",
        summary="about AI",
    )
    _patch_graph_engine(monkeypatch, [(id_a, node_a)])
    _patch_vector_engine(monkeypatch, [id_a])

    results = await recall_topic_weaknesses("u1", "ai safety")

    assert [r["text"] for r in results] == ["about AI"]


async def test_recall_user_facts_returns_owned_facts(monkeypatch):
    id_a, node_a = _node("PersonalFact", user_id="u1", fact_text="I'm a nurse")
    id_b, node_b = _node("PersonalFact", user_id="u2", fact_text="not mine")
    _patch_graph_engine(monkeypatch, [(id_a, node_a), (id_b, node_b)])
    _patch_vector_engine(monkeypatch, [id_a, id_b])

    results = await recall_user_facts("u1")

    assert [r["text"] for r in results] == ["I'm a nurse"]
