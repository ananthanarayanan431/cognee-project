"""Tests for debatemind.services.fingerprint_finalize_svc.

write_chat_session_summary is moved verbatim out of routers/sessions.py (which
had no direct test coverage of its stat computation); these tests lock in that
behavior. finalize_session_fingerprint / finalize_voice_session_fingerprint
tests verify the summary-before-reindex ordering the sessions.py code comment
has always relied on.
"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.session import DebateSession, Exchange
from debatemind.services import fingerprint_finalize_svc as svc


@pytest.fixture
async def session_factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(svc, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


async def test_write_chat_session_summary_computes_win_rate_and_averages(
    session_factory, monkeypatch
):
    async with session_factory() as db:
        db.add(DebateSession(id="s1", user_id="u1", topic="AI Safety", difficulty="Hard"))
        db.add(
            Exchange(
                session_id="s1",
                turn_number=1,
                user_message="AI regulation is necessary",
                outcome="Won",
                judge_logic=8.0,
                judge_evidence=7.0,
                judge_rhetoric=6.0,
                detected_pattern=None,
            )
        )
        db.add(
            Exchange(
                session_id="s1",
                turn_number=2,
                user_message="but it should be minimal",
                outcome="Lost",
                judge_logic=4.0,
                judge_evidence=3.0,
                judge_rhetoric=5.0,
                detected_pattern="SlipperySlope",
            )
        )
        await db.commit()

    mock_summary = AsyncMock()
    monkeypatch.setattr(svc, "remember_session_summary", mock_summary)

    await svc.write_chat_session_summary("u1", "s1")

    mock_summary.assert_awaited_once()
    kwargs = mock_summary.call_args.kwargs
    assert kwargs["win_rate"] == 0.5
    assert kwargs["avg_logic"] == 6.0
    assert kwargs["weak_patterns"] == ["SlipperySlope"]


async def test_write_chat_session_summary_skips_missing_session(session_factory, monkeypatch):
    mock_summary = AsyncMock()
    monkeypatch.setattr(svc, "remember_session_summary", mock_summary)

    await svc.write_chat_session_summary("u1", "does-not-exist")

    mock_summary.assert_not_awaited()


async def test_finalize_session_fingerprint_writes_summary_before_reindex(monkeypatch):
    call_order = []

    async def track_summary(user_id, session_id):
        call_order.append("summary")

    async def track_reindex(user_id):
        call_order.append("reindex")

    monkeypatch.setattr(svc, "write_chat_session_summary", track_summary)
    monkeypatch.setattr(svc, "improve_fingerprint", track_reindex)

    await svc.finalize_session_fingerprint("u1", "s1")

    assert call_order == ["summary", "reindex"]


async def test_finalize_voice_session_fingerprint_writes_summary_before_reindex(monkeypatch):
    call_order = []

    async def track_summary(**kwargs):
        call_order.append("summary")

    async def track_reindex(user_id):
        call_order.append("reindex")

    monkeypatch.setattr(svc, "remember_session_summary", track_summary)
    monkeypatch.setattr(svc, "improve_fingerprint", track_reindex)

    await svc.finalize_voice_session_fingerprint(
        user_id="u1",
        session_id="s1",
        topic="AI Safety",
        difficulty="Hard",
        rounds_played=3,
        win_rate=0.7,
        weak_patterns=["Concession"],
        coaching_note="Good job",
    )

    assert call_order == ["summary", "reindex"]
