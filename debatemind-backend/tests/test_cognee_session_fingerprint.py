"""
Unit tests for debatemind.cognee.session_fingerprint.session_scoped_fingerprint
-- the session_id-scoped Cognitive Fingerprint. Unlike graph_svc.build_graph
(which aggregates every session sharing a topic), this is scoped strictly to
one session_id and merges in Postgres exchanges the async Neo4j write hasn't
caught up to yet. get_graph_engine() is mocked; Postgres is a real in-memory
SQLite.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.cognee import session_fingerprint
from debatemind.database import Base
from debatemind.models.session import DebateSession, Exchange


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


@pytest.fixture
async def seed(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(session_fingerprint, "AsyncSessionLocal", factory)

    async def _seed(session_id: str, user_id: str, topic: str, rows: list[tuple[str, str]]):
        """rows = [(detected_pattern, outcome), ...], oldest first."""
        async with factory() as db:
            db.add(DebateSession(id=session_id, user_id=user_id, topic=topic))
            await db.flush()
            for i, (pattern, outcome) in enumerate(rows):
                db.add(
                    Exchange(
                        session_id=session_id,
                        turn_number=i + 1,
                        user_message="msg",
                        detected_pattern=pattern,
                        outcome=outcome,
                    )
                )
            await db.commit()

    yield _seed
    await engine.dispose()


async def test_empty_session_returns_empty_graph(seed):
    await seed("s1", "u1", "UBI", [])
    with _patched([]):
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", "UBI")

    assert graph.nodes == []
    assert graph.edges == []


async def test_topic_node_is_first_and_label_truncated_to_20(seed):
    long_topic = "Should social media platforms be regulated by governments"
    await seed("s1", "u1", long_topic, [("StrawMan", "Lost")])
    with _patched([_record("a", "u1", "s1", "StrawMan", "Lost")]):
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", long_topic)

    assert graph.nodes[0].id == "topic"
    assert graph.nodes[0].type == "topic"
    assert graph.nodes[0].weight == 1.0
    assert graph.nodes[0].label == long_topic[:20]


async def test_fully_synced_session_uses_neo4j_tallies_without_duplication(seed):
    await seed("s1", "u1", "UBI", [("EvidenceBased", "Won")])
    with _patched([_record("a", "u1", "s1", "EvidenceBased", "Won")]):
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", "UBI")

    by_id = {n.id: n for n in graph.nodes}
    assert by_id["EvidenceBased"].type == "strength"
    assert by_id["EvidenceBased"].weight == 0.95  # 1/1 * 3 capped


async def test_merges_pending_exchange_neo4j_has_not_synced_yet(seed):
    # Neo4j only has the first exchange; the second hasn't synced yet.
    await seed("s1", "u1", "UBI", [("EvidenceBased", "Won"), ("StrawMan", "Lost")])
    with _patched([_record("a", "u1", "s1", "EvidenceBased", "Won")]):
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", "UBI")

    by_id = {n.id: n for n in graph.nodes}
    assert by_id["EvidenceBased"].type == "strength"
    assert by_id["StrawMan"].type == "weakness"


async def test_falls_back_to_postgres_when_neo4j_unavailable(seed):
    await seed("s1", "u1", "UBI", [("StrawMan", "Lost"), ("StrawMan", "Lost")])
    with patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", "UBI")

    by_id = {n.id: n for n in graph.nodes}
    assert by_id["StrawMan"].type == "weakness"


async def test_excludes_other_sessions_from_postgres_and_neo4j(seed):
    await seed("s1", "u1", "UBI", [("StrawMan", "Lost")])
    await seed("s2", "u1", "UBI", [("Concession", "Won")])  # different session, same topic
    with _patched([_record("a", "u1", "s1", "StrawMan", "Lost")]):
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", "UBI")

    ids = {n.id for n in graph.nodes if n.id != "topic"}
    assert ids == {"StrawMan"}


async def test_caps_pattern_nodes_at_eight(seed):
    # _neo4j_tallies() doesn't filter by _VALID_PATTERNS (Neo4j's ArgumentRecord
    # nodes are trusted, same as brain_view.user_brain_graph) -- these 10
    # synthetic pattern names are fine to exercise the most_common(8) cap.
    # No Postgres rows are seeded, so neo4j_count (10) exceeds len(rows) (0)
    # and _merge_pending_exchanges's rows[10:] slice is empty: every count
    # comes straight from Neo4j.
    neo4j_nodes = [_record(f"n{i}", "u1", "s1", f"Pattern{i}", "Won") for i in range(10)]
    await seed("s1", "u1", "UBI", [])
    with _patched(neo4j_nodes):
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", "UBI")

    pattern_nodes = [n for n in graph.nodes if n.id != "topic"]
    assert len(pattern_nodes) == 8
