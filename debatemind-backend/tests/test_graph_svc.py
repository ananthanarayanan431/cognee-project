"""
Unit tests for graph_svc.build_graph — verifies it turns recalled weaknesses
into GraphNode/GraphEdge models with the correct weighting, type, dedup, and
truncation rules. recall_weaknesses is mocked; no real Cognee calls happen here.
"""

from unittest.mock import AsyncMock

from debatemind.services import graph_svc


def _mock_recall(monkeypatch, results):
    recall_mock = AsyncMock(return_value=results)
    monkeypatch.setattr(graph_svc, "recall_weaknesses", recall_mock)
    return recall_mock


async def test_build_graph_with_no_results_returns_only_topic_node(monkeypatch):
    _mock_recall(monkeypatch, [])

    graph = await graph_svc.build_graph("u1", "Climate Policy")

    assert len(graph.nodes) == 1
    topic_node = graph.nodes[0]
    assert topic_node.id == "topic"
    assert topic_node.label == "Climate Policy"
    assert topic_node.type == "topic"
    assert topic_node.weight == 1.0
    assert graph.edges == []


async def test_build_graph_truncates_long_topic_label_to_20_chars(monkeypatch):
    _mock_recall(monkeypatch, [])

    long_topic = "Should social media platforms be regulated by governments"
    graph = await graph_svc.build_graph("u1", long_topic)

    assert graph.nodes[0].label == long_topic[:20]
    assert len(graph.nodes[0].label) == 20


async def test_build_graph_creates_weakness_node_for_matching_pattern(monkeypatch):
    _mock_recall(monkeypatch, [{"text": "This argument relies on a StrawMan pattern found"}])

    graph = await graph_svc.build_graph("u1", "Topic")

    assert len(graph.nodes) == 2
    pattern_node = graph.nodes[1]
    assert pattern_node.id == "StrawMan"
    assert pattern_node.label == "StrawMan"
    assert pattern_node.type == "weakness"
    assert pattern_node.weight == 0.9

    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.source == "topic"
    assert edge.target == "StrawMan"
    assert edge.weight == 0.9


async def test_build_graph_weight_decreases_with_result_index(monkeypatch):
    _mock_recall(
        monkeypatch,
        [
            {"text": "irrelevant text"},
            {"text": "StrawMan spotted here"},
        ],
    )

    graph = await graph_svc.build_graph("u1", "Topic")

    pattern_node = next(n for n in graph.nodes if n.id == "StrawMan")
    assert pattern_node.weight == 0.8


async def test_build_graph_marks_node_as_strength_when_weight_drops_to_half_or_below(monkeypatch):
    results = [{"text": "irrelevant"}] * 4 + [{"text": "AdHominem detected"}]

    _mock_recall(monkeypatch, results)

    graph = await graph_svc.build_graph("u1", "Topic")

    pattern_node = next(n for n in graph.nodes if n.id == "AdHominem")
    assert pattern_node.weight == 0.5
    assert pattern_node.type == "strength"


async def test_build_graph_pattern_matching_is_case_insensitive(monkeypatch):
    _mock_recall(monkeypatch, [{"text": "this debate used strawman tactics"}])

    graph = await graph_svc.build_graph("u1", "Topic")

    assert any(n.id == "StrawMan" for n in graph.nodes)


async def test_build_graph_dedupes_repeated_pattern_across_results(monkeypatch):
    _mock_recall(
        monkeypatch,
        [
            {"text": "StrawMan here"},
            {"text": "StrawMan again"},
        ],
    )

    graph = await graph_svc.build_graph("u1", "Topic")

    strawman_nodes = [n for n in graph.nodes if n.id == "StrawMan"]
    assert len(strawman_nodes) == 1
    assert strawman_nodes[0].weight == 0.9
    assert len([e for e in graph.edges if e.target == "StrawMan"]) == 1


async def test_build_graph_only_considers_first_eight_results(monkeypatch):
    results = [{"text": "irrelevant"}] * 8 + [{"text": "Concession reached"}]

    _mock_recall(monkeypatch, results)

    graph = await graph_svc.build_graph("u1", "Topic")

    assert len(graph.nodes) == 1
    assert not any(n.id == "Concession" for n in graph.nodes)


async def test_build_graph_skips_results_with_no_pattern_match(monkeypatch):
    _mock_recall(monkeypatch, [{"text": "nothing notable here"}])

    graph = await graph_svc.build_graph("u1", "Topic")

    assert len(graph.nodes) == 1
    assert graph.edges == []


async def test_build_graph_handles_missing_text_key(monkeypatch):
    _mock_recall(monkeypatch, [{}])

    graph = await graph_svc.build_graph("u1", "Topic")

    assert len(graph.nodes) == 1
    assert graph.edges == []


async def test_build_graph_only_adds_one_node_per_result_even_with_multiple_pattern_hits(
    monkeypatch,
):
    _mock_recall(monkeypatch, [{"text": "StrawMan and AdHominem both present"}])

    graph = await graph_svc.build_graph("u1", "Topic")

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1


async def test_topic_node_is_always_first_and_has_fixed_attributes(monkeypatch):
    _mock_recall(monkeypatch, [{"text": "StrawMan spotted"}])

    graph = await graph_svc.build_graph("u1", "Topic")

    topic_node = graph.nodes[0]
    assert topic_node.id == "topic"
    assert topic_node.type == "topic"
    assert topic_node.weight == 1.0


async def test_pattern_node_label_always_equals_its_id(monkeypatch):
    _mock_recall(monkeypatch, [{"text": "EmotionalAppeal used heavily"}])

    graph = await graph_svc.build_graph("u1", "Topic")

    pattern_node = next(n for n in graph.nodes if n.id != "topic")
    assert pattern_node.label == pattern_node.id


async def test_pattern_node_weight_boundary_just_above_half_is_weakness(monkeypatch):
    results = [{"text": "irrelevant"}] * 3 + [{"text": "AdHominem detected"}]

    _mock_recall(monkeypatch, results)

    graph = await graph_svc.build_graph("u1", "Topic")

    pattern_node = next(n for n in graph.nodes if n.id == "AdHominem")
    assert pattern_node.weight == 0.6
    assert pattern_node.type == "weakness"


async def test_pattern_node_weight_is_rounded_to_two_decimals_at_low_index(monkeypatch):
    results = [{"text": "irrelevant"}] * 7 + [{"text": "Concession reached"}]

    _mock_recall(monkeypatch, results)

    graph = await graph_svc.build_graph("u1", "Topic")

    pattern_node = next(n for n in graph.nodes if n.id == "Concession")
    assert pattern_node.weight == 0.2


async def test_each_distinct_pattern_across_eight_results_produces_its_own_node(monkeypatch):
    results = [
        {"text": "EvidenceBased claim"},
        {"text": "AppealToAuthority cited"},
        {"text": "StrawMan distortion"},
        {"text": "AdHominem attack"},
        {"text": "SlipperySlope warning"},
        {"text": "FalseEquivalence drawn"},
        {"text": "EmotionalAppeal made"},
        {"text": "AnecdotalEvidence shared"},
    ]

    _mock_recall(monkeypatch, results)

    graph = await graph_svc.build_graph("u1", "Topic")

    pattern_nodes = [n for n in graph.nodes if n.id != "topic"]
    assert {n.id for n in pattern_nodes} == {
        "EvidenceBased",
        "AppealToAuthority",
        "StrawMan",
        "AdHominem",
        "SlipperySlope",
        "FalseEquivalence",
        "EmotionalAppeal",
        "AnecdotalEvidence",
    }
    assert [n.weight for n in pattern_nodes] == [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]
    assert len(graph.edges) == 8
