"""
Unit tests for debatemind.cognee.recall — the graph+vector join that replaced
SearchType.CHUNKS search. get_graph_engine()/get_vector_engine() are mocked;
no real Cognee storage/LLM calls happen here.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from debatemind.cognee._base import classify_entity
from debatemind.cognee.recall import (
    cognitive_profile_text,
    filter_profile_patterns,
    owned_nodes,
    recall_cognitive_profile,
    recall_topic_weaknesses,
    recall_user_facts,
    recall_weaknesses,
)


def _node(node_type: str, **props):
    return (str(uuid4()), {"type": node_type, **props})


class _FakeGraphEngine:
    def __init__(self, nodes, edges=None):
        self._nodes = nodes
        self._edges = edges or []

    async def get_graph_data(self):
        return self._nodes, self._edges


class _FakeScoredResult:
    def __init__(self, node_id: str):
        self.id = node_id


def _patch_graph_engine(monkeypatch, nodes, edges=None):
    async def fake_get_graph_engine():
        return _FakeGraphEngine(nodes, edges)

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


# --- classify_entity (ontology vocab matching) -----------------------------


def test_classify_entity_matches_exact_and_fuzzy_names():
    assert classify_entity("StrawMan") == ("fallacy", "StrawMan")
    assert classify_entity("straw man") == ("fallacy", "StrawMan")  # cognify fuzz
    assert classify_entity("Confirmation-Bias") == ("bias", "ConfirmationBias")
    assert classify_entity("Inductive") == ("reasoning", "Inductive")
    assert classify_entity("Statistical") == ("evidence_type", "Statistical")


def test_classify_entity_returns_none_for_non_vocab():
    assert classify_entity("AI regulation") is None  # a topic, not vocabulary
    assert classify_entity("") is None
    assert classify_entity(None) is None


# --- recall_cognitive_profile ----------------------------------------------


async def test_profile_layer1_reads_fields_off_the_record(monkeypatch):
    # No edges at all — Layer 1 (fields on the owned record) must still work.
    id_a, node_a = _node(
        "ArgumentRecord",
        user_id="u1",
        fallacy="StrawMan",
        outcome="Lost",
        topic_name="AI regulation",
    )
    _patch_graph_engine(monkeypatch, [(id_a, node_a)])

    profile = await recall_cognitive_profile("u1")

    assert profile["record_count"] == 1
    assert profile["recurring_fallacies"] == ["StrawMan"]
    assert profile["weak_domains"] == ["AI regulation"]


async def test_profile_layer2_classifies_cognify_neighbours(monkeypatch):
    id_a, node_a = _node("ArgumentRecord", user_id="u1", outcome="Lost", topic_name="AI")
    bias_id, bias_node = _node("Entity", name="ConfirmationBias")  # cognify-derived, no user_id
    reasoning_id, reasoning_node = _node("Entity", name="Inductive")
    edges = [(id_a, bias_id, "exhibitsBias"), (reasoning_id, id_a, "usesReasoning")]
    _patch_graph_engine(
        monkeypatch,
        [(id_a, node_a), (bias_id, bias_node), (reasoning_id, reasoning_node)],
        edges,
    )

    profile = await recall_cognitive_profile("u1")

    assert profile["cognitive_biases"] == ["ConfirmationBias"]
    assert profile["reasoning_approaches"] == ["Inductive"]  # edge direction agnostic


async def test_profile_isolates_by_user_id(monkeypatch):
    id_a, node_a = _node("ArgumentRecord", user_id="u1", fallacy="StrawMan", outcome="Lost")
    id_b, node_b = _node("ArgumentRecord", user_id="u2", fallacy="AdHominem", outcome="Lost")
    # u2's record is wired to a bias node; it must not leak into u1's profile.
    bias_id, bias_node = _node("Entity", name="Overconfidence")
    edges = [(id_b, bias_id, "exhibitsBias")]
    _patch_graph_engine(monkeypatch, [(id_a, node_a), (id_b, node_b), (bias_id, bias_node)], edges)

    profile = await recall_cognitive_profile("u1")

    assert profile["record_count"] == 1
    assert profile["recurring_fallacies"] == ["StrawMan"]
    assert profile["cognitive_biases"] == []  # u2's neighbour excluded


async def test_profile_weights_lost_outcomes_higher(monkeypatch):
    # Two AdHominem (Won), one StrawMan (Lost). Lost counts double (2 > 1+1? no,
    # 2 == 2) — add a second StrawMan-Lost to make StrawMan rank first.
    won_a = _node("ArgumentRecord", user_id="u1", fallacy="AdHominem", outcome="Won")
    lost_a = _node("ArgumentRecord", user_id="u1", fallacy="StrawMan", outcome="Lost")
    lost_b = _node("ArgumentRecord", user_id="u1", fallacy="StrawMan", outcome="Lost")
    _patch_graph_engine(monkeypatch, [won_a, lost_a, lost_b])

    profile = await recall_cognitive_profile("u1")

    # StrawMan: 2 records * weight 2 = 4; AdHominem: 1 * 1 = 1.
    assert profile["recurring_fallacies"][0] == "StrawMan"


async def test_profile_filters_by_topic(monkeypatch):
    ai = _node("ArgumentRecord", user_id="u1", fallacy="StrawMan", topic_name="AI", outcome="Lost")
    climate = _node(
        "ArgumentRecord", user_id="u1", fallacy="AdHominem", topic_name="Climate", outcome="Lost"
    )
    _patch_graph_engine(monkeypatch, [ai, climate])

    profile = await recall_cognitive_profile("u1", topic="ai")  # case-insensitive

    assert profile["record_count"] == 1
    assert profile["recurring_fallacies"] == ["StrawMan"]


async def test_profile_empty_when_nothing_owned(monkeypatch):
    _patch_graph_engine(monkeypatch, [])

    profile = await recall_cognitive_profile("u1")

    assert profile["record_count"] == 0
    assert profile["recurring_fallacies"] == []
    assert cognitive_profile_text(profile) == ""


# --- filter_profile_patterns / cognitive_profile_text ----------------------


def test_filter_profile_patterns_drops_mastered_fallacies_only():
    profile = {
        "record_count": 3,
        "recurring_fallacies": ["StrawMan", "AdHominem"],
        "cognitive_biases": ["ConfirmationBias"],
        "reasoning_approaches": ["Inductive"],
        "evidence_types": [],
        "weak_domains": ["AI"],
    }

    filtered = filter_profile_patterns(profile, {"StrawMan"})

    assert filtered["recurring_fallacies"] == ["AdHominem"]
    assert filtered["cognitive_biases"] == ["ConfirmationBias"]  # biases never mastered away
    assert profile["recurring_fallacies"] == ["StrawMan", "AdHominem"]  # original not mutated


def test_filter_profile_patterns_noop_without_patterns():
    profile = {"recurring_fallacies": ["StrawMan"]}
    assert filter_profile_patterns(profile, None) is profile
    assert filter_profile_patterns(profile, set()) is profile


def test_cognitive_profile_text_renders_present_fields():
    profile = {
        "record_count": 5,
        "recurring_fallacies": ["StrawMan"],
        "cognitive_biases": ["ConfirmationBias"],
        "reasoning_approaches": [],
        "evidence_types": [],
        "weak_domains": ["AI regulation"],
    }
    text = cognitive_profile_text(profile)
    assert "recurring fallacies: StrawMan" in text
    assert "cognitive biases: ConfirmationBias" in text
    assert "weakest on topics: AI regulation" in text
    assert "leans on reasoning" not in text  # empty field omitted
