"""
Unit/integration tests for progress_svc.get_progress_stats — exercises real
SQLAlchemy queries against an in-memory SQLite DB (no mocking of SQL).
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.mastery import MasteryLog
from debatemind.models.session import DebateSession, Exchange
from debatemind.services.progress_svc import (
    get_mastered_patterns,
    get_progress_stats,
    get_streak,
    get_weakness_trend,
    get_win_rate_by_topic,
)


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


async def test_get_streak_zero_with_no_sessions(db_session):
    assert await get_streak(db_session, "u1") == 0


async def test_get_streak_counts_consecutive_days_ending_today(db_session):
    today = date.today()
    db_session.add_all(
        [
            DebateSession(user_id="u1", topic="A", started_at=today),
            DebateSession(user_id="u1", topic="B", started_at=today - timedelta(days=1)),
            DebateSession(user_id="u1", topic="C", started_at=today - timedelta(days=2)),
            DebateSession(user_id="u1", topic="D", started_at=today - timedelta(days=10)),
        ]
    )
    await db_session.commit()

    assert await get_streak(db_session, "u1") == 3


async def test_get_win_rate_by_topic_groups_correctly(db_session):
    s1 = DebateSession(user_id="u1", topic="AI regulation")
    s2 = DebateSession(user_id="u1", topic="UBI")
    db_session.add_all([s1, s2])
    await db_session.flush()
    db_session.add_all(
        [
            _exchange(s1.id, 1, "Won"),
            _exchange(s1.id, 2, "Lost"),
            _exchange(s2.id, 1, "Won"),
        ]
    )
    await db_session.commit()

    rates = {r["topic"]: r["win_rate"] for r in await get_win_rate_by_topic(db_session, "u1")}
    assert rates["AI regulation"] == 0.5
    assert rates["UBI"] == 1.0


async def test_get_mastered_patterns_orders_by_recency_and_flags_reactivated(db_session):
    db_session.add_all(
        [
            MasteryLog(user_id="u1", pattern_type="StrawMan", rounds_to_mastery=4),
            MasteryLog(
                user_id="u1",
                pattern_type="AdHominem",
                rounds_to_mastery=6,
                reactivated_at=date.today(),
            ),
        ]
    )
    await db_session.commit()

    patterns = await get_mastered_patterns(db_session, "u1")
    by_name = {p["pattern"]: p for p in patterns}
    assert by_name["StrawMan"]["reactivated"] is False
    assert by_name["AdHominem"]["reactivated"] is True
    assert by_name["AdHominem"]["rounds_to_mastery"] == 6


async def test_get_weakness_trend_excludes_mastered_unreactivated_patterns(db_session):
    s = DebateSession(user_id="u1", topic="A")
    db_session.add(s)
    await db_session.flush()
    db_session.add_all(
        [
            Exchange(
                session_id=s.id,
                turn_number=1,
                user_message="m",
                detected_pattern="StrawMan",
                outcome="Lost",
                judge_logic=3.0,
                judge_evidence=3.0,
                judge_rhetoric=3.0,
            ),
            Exchange(
                session_id=s.id,
                turn_number=2,
                user_message="m",
                detected_pattern="AdHominem",
                outcome="Lost",
                judge_logic=2.0,
                judge_evidence=2.0,
                judge_rhetoric=2.0,
            ),
        ]
    )
    db_session.add(MasteryLog(user_id="u1", pattern_type="StrawMan", rounds_to_mastery=3))
    await db_session.commit()

    trend = await get_weakness_trend(db_session, "u1")
    patterns = {t["pattern"] for t in trend}
    assert "StrawMan" not in patterns
    assert "AdHominem" in patterns
