"""
Verifies the new description/source columns on DebateSession round-trip
through a real (in-memory SQLite) async session — same fixture pattern as
test_progress_svc.py.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.session import DebateSession


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def test_description_and_source_fields_default_to_none(db_session):
    session = DebateSession(user_id="u1", topic="AI Safety")
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    assert session.description is None
    assert session.source_filename is None
    assert session.source_object_key is None


async def test_description_and_source_fields_persist(db_session):
    session = DebateSession(
        user_id="u1",
        topic="AI Safety",
        description="Focus on EU AI Act enforcement",
        source_filename="report.pdf",
        source_object_key="sources/s1/report.pdf",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    result = await db_session.execute(select(DebateSession).where(DebateSession.id == session.id))
    fetched = result.scalar_one()
    assert fetched.description == "Focus on EU AI Act enforcement"
    assert fetched.source_filename == "report.pdf"
    assert fetched.source_object_key == "sources/s1/report.pdf"
