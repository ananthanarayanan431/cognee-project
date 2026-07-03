"""Unit tests for services.session_score_svc — LLM-as-judge session scoring."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.session import DebateSession, Exchange
from debatemind.services import session_score_svc
from debatemind.services.session_score_svc import compute_session_score


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _mock_completion(content: str | None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


async def _make_session(db, with_exchanges: bool = True) -> DebateSession:
    s = DebateSession(
        user_id="u1",
        topic="AI regulation",
        difficulty="targeted",
        user_position="against",
        status="ended",
    )
    db.add(s)
    await db.flush()
    if with_exchanges:
        db.add_all(
            [
                Exchange(
                    session_id=s.id,
                    turn_number=1,
                    user_message="Strict rules protect citizens.",
                    opponent_response="They also entrench incumbents.",
                    outcome="Lost",
                    judge_logic=4.0,
                    judge_evidence=3.0,
                    judge_rhetoric=5.0,
                ),
                Exchange(
                    session_id=s.id,
                    turn_number=2,
                    user_message="The GDPR precedent shows global uptake.",
                    opponent_response="GDPR compliance costs hit SMEs hardest.",
                    outcome="Won",
                    judge_logic=8.0,
                    judge_evidence=7.0,
                    judge_rhetoric=6.0,
                ),
            ]
        )
    await db.commit()
    return s


async def test_llm_score_is_persisted(db_session, monkeypatch):
    s = await _make_session(db_session)
    create_mock = AsyncMock(
        return_value=_mock_completion('{"reasoning": "Solid recovery in turn 2.", "score": 6.8}')
    )
    monkeypatch.setattr(session_score_svc.openrouter.chat.completions, "create", create_mock)

    score = await compute_session_score(db_session, "u1", s.id)

    assert score == 6.8
    row = (
        await db_session.execute(select(DebateSession).where(DebateSession.id == s.id))
    ).scalar_one()
    assert row.overall_score == 6.8


async def test_prompt_contains_transcript_and_judge_scores(db_session, monkeypatch):
    s = await _make_session(db_session)
    create_mock = AsyncMock(return_value=_mock_completion('{"reasoning": "x", "score": 5}'))
    monkeypatch.setattr(session_score_svc.openrouter.chat.completions, "create", create_mock)

    await compute_session_score(db_session, "u1", s.id)

    _, kwargs = create_mock.call_args
    prompt = kwargs["messages"][0]["content"]
    assert "AI regulation" in prompt
    assert "Strict rules protect citizens." in prompt
    assert "They also entrench incumbents." in prompt
    assert "against" in prompt
    # Per-turn judge context rides along
    assert "Won" in prompt and "Lost" in prompt
    assert kwargs["response_format"]["type"] == "json_schema"


async def test_falls_back_to_exchange_average_when_llm_fails(db_session, monkeypatch):
    s = await _make_session(db_session)
    create_mock = AsyncMock(side_effect=RuntimeError("LLM down"))
    monkeypatch.setattr(session_score_svc.openrouter.chat.completions, "create", create_mock)

    score = await compute_session_score(db_session, "u1", s.id)

    expected = round((4 + 3 + 5 + 8 + 7 + 6) / 6, 1)
    assert score == expected
    row = (
        await db_session.execute(select(DebateSession).where(DebateSession.id == s.id))
    ).scalar_one()
    assert row.overall_score == expected


async def test_falls_back_on_malformed_llm_content(db_session, monkeypatch):
    s = await _make_session(db_session)
    create_mock = AsyncMock(return_value=_mock_completion("not json"))
    monkeypatch.setattr(session_score_svc.openrouter.chat.completions, "create", create_mock)

    score = await compute_session_score(db_session, "u1", s.id)

    assert score == round((4 + 3 + 5 + 8 + 7 + 6) / 6, 1)


async def test_llm_score_clamped_to_valid_range(db_session, monkeypatch):
    s = await _make_session(db_session)
    create_mock = AsyncMock(
        return_value=_mock_completion(json.dumps({"reasoning": "x", "score": 42}))
    )
    monkeypatch.setattr(session_score_svc.openrouter.chat.completions, "create", create_mock)

    score = await compute_session_score(db_session, "u1", s.id)

    assert score == 10.0


async def test_no_exchanges_leaves_score_untouched(db_session, monkeypatch):
    s = await _make_session(db_session, with_exchanges=False)
    create_mock = AsyncMock()
    monkeypatch.setattr(session_score_svc.openrouter.chat.completions, "create", create_mock)

    score = await compute_session_score(db_session, "u1", s.id)

    assert score is None
    create_mock.assert_not_called()
    row = (
        await db_session.execute(select(DebateSession).where(DebateSession.id == s.id))
    ).scalar_one()
    assert row.overall_score == 0.0


async def test_returns_none_for_missing_or_foreign_session(db_session):
    assert await compute_session_score(db_session, "u1", "nope") is None

    other = DebateSession(user_id="u2", topic="X")
    db_session.add(other)
    await db_session.commit()
    assert await compute_session_score(db_session, "u1", other.id) is None
