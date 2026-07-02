import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.mastery import MasteryLog
from debatemind.models.session import DebateSession, Exchange
from debatemind.services.summary_svc import get_session_summary


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_returns_none_for_missing_or_foreign_session(db_session):
    assert await get_session_summary(db_session, "u1", "nope") is None

    other = DebateSession(user_id="u2", topic="X")
    db_session.add(other)
    await db_session.commit()
    assert await get_session_summary(db_session, "u1", other.id) is None


async def test_computes_score_exchanges_and_weaknesses_exposed(db_session):
    s = DebateSession(user_id="u1", topic="AI regulation", difficulty="targeted")
    db_session.add(s)
    await db_session.flush()
    db_session.add_all(
        [
            Exchange(
                session_id=s.id,
                turn_number=1,
                user_message="m1",
                detected_pattern="AppealToAuthority",
                outcome="Lost",
                judge_logic=4.0,
                judge_evidence=3.0,
                judge_rhetoric=7.0,
            ),
            Exchange(
                session_id=s.id,
                turn_number=2,
                user_message="m2",
                detected_pattern="AppealToAuthority",
                outcome="Won",
                judge_logic=8.0,
                judge_evidence=8.0,
                judge_rhetoric=8.0,
            ),
        ]
    )
    await db_session.commit()

    summary = await get_session_summary(db_session, "u1", s.id)

    assert summary.topic == "AI regulation"
    assert summary.exchanges == 2
    assert summary.rounds_won == 1
    assert summary.weaknesses_exposed == 1  # only the Lost exchange's pattern counts
    assert summary.score == pytest.approx((4 + 3 + 7 + 8 + 8 + 8) / 6, abs=0.01)


async def test_before_uses_prior_sessions_after_uses_current_session(db_session):
    earlier = DebateSession(user_id="u1", topic="Topic A")
    db_session.add(earlier)
    await db_session.flush()
    db_session.add(
        Exchange(
            session_id=earlier.id,
            turn_number=1,
            user_message="m",
            detected_pattern="StrawMan",
            outcome="Lost",
            judge_logic=2.0,
            judge_evidence=2.0,
            judge_rhetoric=2.0,
        )
    )
    await db_session.commit()

    later = DebateSession(user_id="u1", topic="Topic B")
    db_session.add(later)
    await db_session.flush()
    db_session.add(
        Exchange(
            session_id=later.id,
            turn_number=1,
            user_message="m",
            detected_pattern="StrawMan",
            outcome="Won",
            judge_logic=9.0,
            judge_evidence=9.0,
            judge_rhetoric=9.0,
        )
    )
    await db_session.commit()

    summary = await get_session_summary(db_session, "u1", later.id)
    change = next(p for p in summary.patterns if p.pattern == "StrawMan")

    assert change.before == pytest.approx(1 - 2 / 10, abs=0.01)
    assert change.after == pytest.approx(1 - 9 / 10, abs=0.01)


async def test_pattern_with_no_prior_history_has_equal_before_and_after(db_session):
    s = DebateSession(user_id="u1", topic="Topic A")
    db_session.add(s)
    await db_session.flush()
    db_session.add(
        Exchange(
            session_id=s.id,
            turn_number=1,
            user_message="m",
            detected_pattern="SlipperySlope",
            outcome="Lost",
            judge_logic=5.0,
            judge_evidence=5.0,
            judge_rhetoric=5.0,
        )
    )
    await db_session.commit()

    summary = await get_session_summary(db_session, "u1", s.id)
    change = next(p for p in summary.patterns if p.pattern == "SlipperySlope")

    assert change.before == change.after


async def test_mastered_pattern_flagged_with_rounds_to_mastery(db_session):
    s = DebateSession(user_id="u1", topic="Topic A")
    db_session.add(s)
    await db_session.flush()
    db_session.add(
        Exchange(
            session_id=s.id,
            turn_number=1,
            user_message="m",
            detected_pattern="AdHominem",
            outcome="Won",
            judge_logic=9.0,
            judge_evidence=9.0,
            judge_rhetoric=9.0,
        )
    )
    await db_session.commit()
    db_session.add(MasteryLog(user_id="u1", pattern_type="AdHominem", rounds_to_mastery=3))
    await db_session.commit()

    summary = await get_session_summary(db_session, "u1", s.id)
    change = next(p for p in summary.patterns if p.pattern == "AdHominem")

    assert change.mastered is True
    assert change.rounds_to_mastery == 3
    assert summary.mastered_count == 1
