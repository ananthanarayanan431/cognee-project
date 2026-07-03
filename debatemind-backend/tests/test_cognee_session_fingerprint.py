"""
Unit tests for debatemind.cognee.session_fingerprint.session_scoped_fingerprint
-- the session_id-scoped Cognitive Fingerprint. Unlike graph_svc.build_graph
(which aggregates every session sharing a topic), this is scoped strictly to
one session_id and merges in Postgres exchanges the async Neo4j write hasn't
caught up to yet. get_graph_engine() is mocked; Postgres is a real in-memory
SQLite.
"""

from unittest.mock import AsyncMock, patch

from debatemind.cognee import session_fingerprint


def test_merge_only_applies_to_the_tail_past_neo4j_count():
    tallies = {"StrawMan": [2, 2]}  # Neo4j already has 2 synced StrawMan wins
    rows = [
        ("StrawMan", "Won"),
        ("StrawMan", "Won"),
        ("EvidenceBased", "Lost"),
    ]
    result = session_fingerprint._merge_pending_exchanges(tallies, neo4j_count=2, rows=rows)
    assert result == {"StrawMan": [2, 2], "EvidenceBased": [1, 0]}


def test_merge_reconstructs_everything_when_neo4j_count_is_zero():
    tallies: dict = {}
    rows = [("StrawMan", "Lost"), ("StrawMan", "Won")]
    result = session_fingerprint._merge_pending_exchanges(tallies, neo4j_count=0, rows=rows)
    assert result == {"StrawMan": [2, 1]}


def test_merge_ignores_patterns_outside_pattern_types():
    result = session_fingerprint._merge_pending_exchanges(
        {}, neo4j_count=0, rows=[("NotReal", "Won")]
    )
    assert result == {}


def test_merge_is_a_no_op_when_neo4j_already_has_every_exchange():
    tallies = {"StrawMan": [3, 1]}
    rows = [("StrawMan", "Lost"), ("StrawMan", "Lost"), ("StrawMan", "Won")]
    result = session_fingerprint._merge_pending_exchanges(tallies, neo4j_count=3, rows=rows)
    assert result == {"StrawMan": [3, 1]}


class _FakeGraphEngine:
    def __init__(self, nodes):
        self._nodes = nodes

    async def get_graph_data(self):
        return self._nodes, []


def _patched(nodes):
    return patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(return_value=_FakeGraphEngine(nodes)),
    )


def _record(nid, user_id, session_id, pattern, outcome):
    return (
        nid,
        {
            "id": nid,
            "type": "ArgumentRecord",
            "user_id": user_id,
            "session_id": session_id,
            "pattern_type": pattern,
            "outcome": outcome,
        },
    )


async def test_neo4j_tallies_counts_matching_records():
    nodes = [
        _record("a", "u1", "s1", "StrawMan", "Lost"),
        _record("b", "u1", "s1", "StrawMan", "Won"),
    ]
    with _patched(nodes):
        tallies, count = await session_fingerprint._neo4j_tallies("u1", "s1")

    assert tallies == {"StrawMan": [2, 1]}
    assert count == 2


async def test_neo4j_tallies_excludes_other_sessions_and_users():
    nodes = [
        _record("a", "u1", "s1", "StrawMan", "Won"),
        _record("b", "u1", "s2", "AdHominem", "Won"),  # other session
        _record("c", "u2", "s1", "Concession", "Won"),  # other user
    ]
    with _patched(nodes):
        tallies, count = await session_fingerprint._neo4j_tallies("u1", "s1")

    assert tallies == {"StrawMan": [1, 1]}
    assert count == 1


async def test_neo4j_tallies_ignores_non_argument_record_nodes():
    nodes = [("e", {"id": "e", "type": "Entity", "name": "StrawMan"})]
    with _patched(nodes):
        tallies, count = await session_fingerprint._neo4j_tallies("u1", "s1")

    assert tallies == {}
    assert count == 0


async def test_neo4j_tallies_returns_empty_on_engine_failure():
    with patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        tallies, count = await session_fingerprint._neo4j_tallies("u1", "s1")

    assert tallies == {}
    assert count == 0
