"""
Unit tests for debatemind.cognee.session_fingerprint.session_scoped_fingerprint
-- the session_id-scoped Cognitive Fingerprint. Unlike graph_svc.build_graph
(which aggregates every session sharing a topic), this is scoped strictly to
one session_id and merges in Postgres exchanges the async Neo4j write hasn't
caught up to yet. get_graph_engine() is mocked; Postgres is a real in-memory
SQLite.
"""

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
