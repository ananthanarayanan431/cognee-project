"""Unit tests for the pure mapping in debatemind.scripts.backfill_neo4j —
Postgres exchange rows -> typed Cognee DataPoint nodes. No DB or graph I/O.
"""

from debatemind.cognee.schema import (
    ArgumentRecord,
    Topic,
    UserProfile,
    deterministic_id,
)
from debatemind.scripts.backfill_neo4j import _build_typed_nodes, _evidence_label


def _row(**over):
    row = {
        "user_id": "u1",
        "session_id": "s1",
        "topic": "UBI",
        "exchange_id": "e1",
        "claim_text": "we should do X",
        "pattern_type": "StrawMan",
        "fallacy": None,
        "evidence_score": 5.0,
        "outcome": "Lost",
    }
    row.update(over)
    return row


def _split(nodes):
    owners = [n for n in nodes if isinstance(n, UserProfile)]
    topics = [n for n in nodes if isinstance(n, Topic)]
    args = [n for n in nodes if isinstance(n, ArgumentRecord)]
    return owners, topics, args


def test_builds_owner_topic_and_argument_from_one_row():
    owners, topics, args = _split(_build_typed_nodes([_row()]))

    assert len(owners) == 1 and owners[0].user_id == "u1"
    assert len(topics) == 1 and topics[0].name == "UBI"
    assert len(args) == 1
    rec = args[0]
    assert rec.user_id == "u1"
    assert rec.topic_name == "UBI"
    assert rec.pattern_type == "StrawMan"
    assert rec.outcome == "Lost"
    assert rec.claim_text == "we should do X"
    # typed edges wired to the shared owner/topic instances
    assert rec.owner is owners[0]
    assert rec.topic is topics[0]


def test_dedupes_owner_and_topic_across_rows():
    rows = [
        _row(exchange_id="e1", pattern_type="StrawMan"),
        _row(exchange_id="e2", pattern_type="Causal"),
        _row(exchange_id="e3", topic="AI safety", pattern_type="Deductive"),
    ]
    owners, topics, args = _split(_build_typed_nodes(rows))

    assert len(owners) == 1  # same user
    assert {t.name for t in topics} == {"UBI", "AI safety"}
    assert len(args) == 3


def test_argument_id_is_deterministic_across_runs():
    first = _split(_build_typed_nodes([_row()]))[2][0]
    second = _split(_build_typed_nodes([_row()]))[2][0]
    assert first.id == second.id  # idempotent re-run updates same node
    assert first.id == deterministic_id("ArgumentRecord", "s1", "e1")


def test_distinct_exchanges_get_distinct_argument_ids():
    _, _, args = _split(_build_typed_nodes([_row(exchange_id="e1"), _row(exchange_id="e2")]))
    assert args[0].id != args[1].id


def test_skips_rows_missing_user_topic_or_pattern():
    rows = [
        _row(pattern_type=None),
        _row(topic=None),
        _row(user_id=None),
        _row(exchange_id="ok"),
    ]
    _, _, args = _split(_build_typed_nodes(rows))
    assert len(args) == 1


def test_outcome_defaults_to_neutral_when_missing():
    _, _, args = _split(_build_typed_nodes([_row(outcome=None)]))
    assert args[0].outcome == "Neutral"


def test_evidence_label_thresholds():
    assert _evidence_label(None) == "Moderate"
    assert _evidence_label(9.0) == "Strong"
    assert _evidence_label(7.0) == "Strong"
    assert _evidence_label(4.0) == "Moderate"
    assert _evidence_label(1.0) == "Weak"


def test_argument_carries_evidence_label_not_raw_score():
    _, _, args = _split(_build_typed_nodes([_row(evidence_score=9.0)]))
    assert args[0].evidence_quality == "Strong"
