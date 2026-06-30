"""
Unit/integration tests for progress_svc.get_progress_stats — exercises real
SQLAlchemy queries against an in-memory SQLite DB (no mocking of SQL).
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.session import DebateSession, Exchange
from debatemind.services.progress_svc import get_progress_stats


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def _session(user_id: str) -> DebateSession:
    return DebateSession(user_id=user_id, topic="AI Safety")


def _exchange(session_id: str, turn_number: int, outcome: str | None, **scores) -> Exchange:
    return Exchange(
        session_id=session_id,
        turn_number=turn_number,
        user_message="msg",
        outcome=outcome,
        judge_logic=scores.get("logic"),
        judge_evidence=scores.get("evidence"),
        judge_rhetoric=scores.get("rhetoric"),
    )


async def test_no_data_returns_zeroed_stats(db_session):
    stats = await get_progress_stats(db_session, "u1")

    assert stats == {
        "sessions": 0,
        "win_rate": 0.0,
        "thinking_style": {"logic": 0.0, "evidence": 0.0, "rhetoric": 0.0},
    }


async def test_computes_session_count_win_rate_and_thinking_style(db_session):
    s1 = _session("u1")
    db_session.add(s1)
    await db_session.flush()
    db_session.add_all(
        [
            _exchange(s1.id, 1, "Won", logic=8.0, evidence=6.0, rhetoric=7.0),
            _exchange(s1.id, 2, "Lost", logic=4.0, evidence=4.0, rhetoric=5.0),
            _exchange(s1.id, 3, "Neutral", logic=6.0, evidence=5.0, rhetoric=6.0),
        ]
    )
    await db_session.commit()

    stats = await get_progress_stats(db_session, "u1")

    assert stats["sessions"] == 1
    # Won/decided = 1/2 (Neutral excluded from the denominator)
    assert stats["win_rate"] == 0.5
    assert stats["thinking_style"] == {"logic": 6.0, "evidence": 5.0, "rhetoric": 6.0}


async def test_scopes_stats_to_the_given_user_only(db_session):
    mine = _session("u1")
    other = _session("u2")
    db_session.add_all([mine, other])
    await db_session.flush()
    db_session.add_all(
        [
            _exchange(mine.id, 1, "Won", logic=10.0, evidence=10.0, rhetoric=10.0),
            _exchange(other.id, 1, "Lost", logic=0.0, evidence=0.0, rhetoric=0.0),
        ]
    )
    await db_session.commit()

    stats = await get_progress_stats(db_session, "u1")

    assert stats["sessions"] == 1
    assert stats["win_rate"] == 1.0
    assert stats["thinking_style"] == {"logic": 10.0, "evidence": 10.0, "rhetoric": 10.0}
