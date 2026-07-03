"""
Integration tests for graph_svc.build_graph — exercises the real SQLAlchemy
query against an in-memory SQLite DB. build_graph derives the per-topic
fingerprint graph from persisted Exchange rows (detected_pattern + outcome),
NOT from Cognee — this is the isolation-safe, deterministic data path that
backs the UI graph.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.session import DebateSession, Exchange
from debatemind.services import graph_svc


@pytest.fixture
async def seed(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    # build_graph opens its own AsyncSessionLocal, so point it at the test DB.
    monkeypatch.setattr(graph_svc, "AsyncSessionLocal", factory)

    async def _seed(user_id: str, topic: str, rows: list[tuple[str, str]]):
        """rows = [(detected_pattern, outcome), ...]"""
        async with factory() as db:
            session = DebateSession(user_id=user_id, topic=topic)
            db.add(session)
            await db.flush()
            for i, (pattern, outcome) in enumerate(rows):
                db.add(
                    Exchange(
                        session_id=session.id,
                        turn_number=i + 1,
                        user_message="msg",
                        detected_pattern=pattern,
                        outcome=outcome,
                    )
                )
            await db.commit()

    yield _seed
    await engine.dispose()


async def test_no_data_returns_empty_graph(seed):
    graph = await graph_svc.build_graph("u1", "Climate Policy")
    assert graph.nodes == []
    assert graph.edges == []


async def test_topic_node_is_first_and_label_truncated_to_20(seed):
    long_topic = "Should social media platforms be regulated by governments"
    await seed("u1", long_topic, [("StrawMan", "Lost")])

    graph = await graph_svc.build_graph("u1", long_topic)

    assert graph.nodes[0].id == "topic"
    assert graph.nodes[0].type == "topic"
    assert graph.nodes[0].weight == 1.0
    assert graph.nodes[0].label == long_topic[:20]
    assert len(graph.nodes[0].label) == 20


async def test_losing_pattern_is_a_weakness_winning_pattern_is_a_strength(seed):
    await seed(
        "u1",
        "AI Safety",
        [("StrawMan", "Lost"), ("EvidenceBased", "Won"), ("EvidenceBased", "Won")],
    )

    graph = await graph_svc.build_graph("u1", "AI Safety")
    by_id = {n.id: n for n in graph.nodes}

    assert by_id["StrawMan"].type == "weakness"  # 0/1 wins
    assert by_id["EvidenceBased"].type == "strength"  # 2/2 wins
    # Every pattern node has a topic->pattern edge.
    assert {(e.source, e.target) for e in graph.edges} == {
        ("topic", "StrawMan"),
        ("topic", "EvidenceBased"),
    }


async def test_weight_is_capped_and_rounded(seed):
    # One pattern, one exchange: count/total = 1.0, *3 -> capped at 0.95.
    await seed("u1", "T", [("AdHominem", "Lost")])
    graph = await graph_svc.build_graph("u1", "T")
    node = next(n for n in graph.nodes if n.id == "AdHominem")
    assert node.weight == 0.95


async def test_unknown_patterns_are_ignored(seed):
    await seed("u1", "T", [("NotARealPattern", "Lost"), ("StrawMan", "Lost")])
    graph = await graph_svc.build_graph("u1", "T")
    ids = {n.id for n in graph.nodes}
    assert "NotARealPattern" not in ids
    assert "StrawMan" in ids


async def test_only_the_requested_user_and_topic_are_included(seed):
    await seed("u1", "T", [("StrawMan", "Lost")])
    await seed("u2", "T", [("AdHominem", "Lost")])  # different user
    await seed("u1", "Other", [("SlipperySlope", "Lost")])  # different topic

    graph = await graph_svc.build_graph("u1", "T")
    ids = {n.id for n in graph.nodes if n.id != "topic"}
    assert ids == {"StrawMan"}
