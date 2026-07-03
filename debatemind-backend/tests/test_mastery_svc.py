import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.mastery import MasteryLog
from debatemind.services.mastery_svc import reactivate_pattern, record_mastery_events


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_record_mastery_events_writes_one_row_per_pattern(db_session):
    await record_mastery_events(db_session, "u1", ["StrawMan", "AdHominem"])

    rows = (await db_session.execute(select(MasteryLog))).scalars().all()
    assert {r.pattern_type for r in rows} == {"StrawMan", "AdHominem"}
    assert all(r.rounds_to_mastery == 3 for r in rows)
    assert all(r.user_id == "u1" for r in rows)


async def test_record_mastery_events_noop_on_empty_list(db_session):
    await record_mastery_events(db_session, "u1", [])
    rows = (await db_session.execute(select(MasteryLog))).scalars().all()
    assert rows == []


async def test_reactivate_pattern_sets_reactivated_at(db_session):
    db_session.add(MasteryLog(user_id="u1", pattern_type="StrawMan", rounds_to_mastery=3))
    await db_session.commit()

    ok = await reactivate_pattern(db_session, "u1", "StrawMan")

    assert ok is True
    row = (await db_session.execute(select(MasteryLog))).scalar_one()
    assert row.reactivated_at is not None


async def test_reactivate_pattern_returns_false_when_not_mastered(db_session):
    ok = await reactivate_pattern(db_session, "u1", "Nonexistent")
    assert ok is False
