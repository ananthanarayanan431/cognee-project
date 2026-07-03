"""
Unit tests for debatemind.cognee.brain_view.user_brain_graph — the root -> topic
-> argument-pattern mastery graph, sourced from Cognee's Neo4j ArgumentRecord
nodes (was Postgres). strength/weakness is derived from win-rate over `outcome`;
there is deliberately no `mastered` tier (that status is Postgres-only).
get_graph_engine() is mocked.
"""

from unittest.mock import AsyncMock, patch

from debatemind.cognee.brain_view import user_brain_graph


class _FakeGraphEngine:
    def __init__(self, nodes, edges):
        self._nodes = nodes
        self._edges = edges

    async def get_graph_data(self):
        return self._nodes, self._edges


def _patched(nodes, edges=None):
    return patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(return_value=_FakeGraphEngine(nodes, edges or [])),
    )


def _record(nid, user_id, topic, pattern, outcome):
    return (
        nid,
        {
            "id": nid,
            "type": "ArgumentRecord",
            "user_id": user_id,
            "topic_name": topic,
            "pattern_type": pattern,
            "outcome": outcome,
        },
    )


def _by_id(result):
    return {n["id"]: n for n in result["nodes"]}


async def test_builds_root_topic_pattern_hierarchy():
    nodes = [_record("a", "u1", "UBI", "StrawMan", "Won")]
    with _patched(nodes):
        result = await user_brain_graph("u1")

    types = {n["type"] for n in result["nodes"]}
    assert "root" in types and "topic" in types
    root = next(n for n in result["nodes"] if n["type"] == "root")
    topic = next(n for n in result["nodes"] if n["type"] == "topic")
    assert topic["label"] == "UBI"
    # root -> topic and topic -> pattern edges both present
    srcs = {(e["source"], e["target"]) for e in result["edges"]}
    assert (root["id"], topic["id"]) in srcs
    assert any(s == topic["id"] for s, _ in srcs)


async def test_strength_when_win_rate_at_least_half():
    nodes = [
        _record("a", "u1", "UBI", "Causal", "Won"),
        _record("b", "u1", "UBI", "Causal", "Lost"),
    ]  # 1/2 == 0.5 -> strength
    with _patched(nodes):
        result = await user_brain_graph("u1")

    pattern = next(n for n in result["nodes"] if n["label"] == "Causal")
    assert pattern["type"] == "strength"


async def test_weakness_when_win_rate_below_half():
    nodes = [
        _record("a", "u1", "UBI", "StrawMan", "Won"),
        _record("b", "u1", "UBI", "StrawMan", "Lost"),
        _record("c", "u1", "UBI", "StrawMan", "Lost"),
    ]  # 1/3 < 0.5 -> weakness
    with _patched(nodes):
        result = await user_brain_graph("u1")

    pattern = next(n for n in result["nodes"] if n["label"] == "StrawMan")
    assert pattern["type"] == "weakness"


async def test_neutral_outcome_counts_against_win_rate():
    nodes = [
        _record("a", "u1", "UBI", "AdHominem", "Won"),
        _record("b", "u1", "UBI", "AdHominem", "Neutral"),
        _record("c", "u1", "UBI", "AdHominem", "Neutral"),
    ]  # 1 win / 3 total < 0.5
    with _patched(nodes):
        result = await user_brain_graph("u1")

    pattern = next(n for n in result["nodes"] if n["label"] == "AdHominem")
    assert pattern["type"] == "weakness"


async def test_excludes_other_users():
    nodes = [
        _record("a", "u1", "UBI", "Causal", "Won"),
        _record("b", "u2", "Taxes", "StrawMan", "Lost"),
    ]
    with _patched(nodes):
        result = await user_brain_graph("u1")

    labels = {n["label"] for n in result["nodes"]}
    assert "UBI" in labels and "Causal" in labels
    assert "Taxes" not in labels and "StrawMan" not in labels


async def test_ignores_non_argument_record_nodes():
    nodes = [
        ("e", {"id": "e", "type": "Entity", "name": "SlipperySlope"}),
        ("c", {"id": "c", "type": "DocumentChunk", "text": "User: u1\n..."}),
    ]
    with _patched(nodes):
        result = await user_brain_graph("u1")

    assert result["nodes"] == []
    assert result["edges"] == []


async def test_never_emits_mastered_type():
    nodes = [
        _record("a", "u1", "UBI", "Causal", "Won"),
        _record("b", "u1", "AI", "StrawMan", "Lost"),
    ]
    with _patched(nodes):
        result = await user_brain_graph("u1")

    assert all(n["type"] != "mastered" for n in result["nodes"])
    assert {n["type"] for n in result["nodes"]} <= {"root", "topic", "strength", "weakness"}


async def test_empty_when_no_records():
    with _patched([]):
        result = await user_brain_graph("u1")

    assert result == {"nodes": [], "edges": []}


async def test_caps_patterns_per_topic_at_six():
    nodes = [_record(f"n{i}", "u1", "UBI", f"Pattern{i}", "Won") for i in range(9)]
    with _patched(nodes):
        result = await user_brain_graph("u1")

    pattern_nodes = [n for n in result["nodes"] if n["type"] in ("strength", "weakness")]
    assert len(pattern_nodes) == 6


async def test_returns_empty_on_graph_engine_failure():
    with patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await user_brain_graph("u1")

    assert result["nodes"] == []
    assert result["edges"] == []
    assert "error" in result
