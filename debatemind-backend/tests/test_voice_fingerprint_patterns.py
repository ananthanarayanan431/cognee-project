"""Unit tests for voice_score_svc.derive_voice_session_patterns — deriving
Cognitive Fingerprint argument patterns from a spoken voice transcript."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.session import DebateSession
from debatemind.models.voice_session import VoiceSession, VoiceSessionNote
from debatemind.services import voice_score_svc
from debatemind.services.voice_score_svc import derive_voice_session_patterns


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _mock_completion(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _cls(pattern, evidence, fallacy=None):
    return _mock_completion(
        '{"reasoning": "r", "pattern_type": "%s", "fallacy": %s, '
        '"reasoning_approach": null, "cognitive_bias": null, '
        '"evidence_quality": "%s", "personal_facts": []}'
        % (pattern, "null" if fallacy is None else f'"{fallacy}"', evidence)
    )


async def _make_voice_session(
    db, user_turns: list[str], patterns_derived_count: int = 0
) -> VoiceSession:
    s = DebateSession(user_id="u1", topic="AI regulation", user_position="against")
    db.add(s)
    await db.flush()
    vs = VoiceSession(
        debate_session_id=s.id,
        user_id="u1",
        status="ended",
        patterns_derived_count=patterns_derived_count,
    )
    db.add(vs)
    await db.flush()
    for t in user_turns:
        db.add(VoiceSessionNote(voice_session_id=vs.id, note_type="transcript_user", content=t))
    # AI turns must be ignored by the classifier.
    db.add(VoiceSessionNote(voice_session_id=vs.id, note_type="transcript_ai", content="AI reply"))
    await db.commit()
    return vs


async def test_real_arguments_are_dispatched_as_patterns(db_session, monkeypatch):
    vs = await _make_voice_session(
        db_session,
        ["The GDPR precedent shows global uptake.", "Anyone against this hates progress."],
    )
    create_mock = AsyncMock(
        side_effect=[
            _cls("EvidenceBased", "Strong"),
            _cls("StrawMan", "Absent", fallacy="Strawman"),
        ]
    )
    monkeypatch.setattr(voice_score_svc.openrouter.chat.completions, "create", create_mock)
    delay_mock = MagicMock()
    monkeypatch.setattr(voice_score_svc.remember_argument_task, "delay", delay_mock)

    dispatched = await derive_voice_session_patterns(db_session, vs.id)

    assert dispatched == 2
    assert delay_mock.call_count == 2
    calls = {c.kwargs["pattern_type"]: c.kwargs for c in delay_mock.call_args_list}
    # Evidence-backed argument → strength (Won); fallacy → weakness (Lost).
    assert calls["EvidenceBased"]["outcome"] == "Won"
    assert calls["StrawMan"]["outcome"] == "Lost"
    # Session/user scoping must match what the fingerprint read path filters on.
    assert calls["EvidenceBased"]["session_id"] == vs.debate_session_id
    assert calls["EvidenceBased"]["user_id"] == "u1"


async def test_small_talk_turns_are_skipped(db_session, monkeypatch):
    vs = await _make_voice_session(db_session, ["Yes.", "Cut the call."])
    # Extractor's neutral non-argument default.
    create_mock = AsyncMock(
        side_effect=[_cls("EvidenceBased", "Absent"), _cls("EvidenceBased", "Absent")]
    )
    monkeypatch.setattr(voice_score_svc.openrouter.chat.completions, "create", create_mock)
    delay_mock = MagicMock()
    monkeypatch.setattr(voice_score_svc.remember_argument_task, "delay", delay_mock)

    dispatched = await derive_voice_session_patterns(db_session, vs.id)

    assert dispatched == 0
    delay_mock.assert_not_called()


async def test_weak_evidence_argument_is_a_weakness(db_session, monkeypatch):
    vs = await _make_voice_session(db_session, ["My neighbor said prices dropped."])
    create_mock = AsyncMock(side_effect=[_cls("AnecdotalEvidence", "Weak")])
    monkeypatch.setattr(voice_score_svc.openrouter.chat.completions, "create", create_mock)
    delay_mock = MagicMock()
    monkeypatch.setattr(voice_score_svc.remember_argument_task, "delay", delay_mock)

    await derive_voice_session_patterns(db_session, vs.id)

    assert delay_mock.call_args.kwargs["outcome"] == "Lost"
    assert delay_mock.call_args.kwargs["pattern_type"] == "AnecdotalEvidence"


async def test_classification_failure_skips_dispatch(db_session, monkeypatch):
    # Extractor call blows up; the turn should be skipped, not crash the run.
    vs = await _make_voice_session(db_session, ["The GDPR precedent shows global uptake."])
    create_mock = AsyncMock(side_effect=RuntimeError("openrouter exploded"))
    monkeypatch.setattr(voice_score_svc.openrouter.chat.completions, "create", create_mock)
    delay_mock = MagicMock()
    monkeypatch.setattr(voice_score_svc.remember_argument_task, "delay", delay_mock)

    dispatched = await derive_voice_session_patterns(db_session, vs.id)

    assert dispatched == 0
    delay_mock.assert_not_called()


async def test_no_user_turns_dispatches_nothing(db_session, monkeypatch):
    s = DebateSession(user_id="u1", topic="AI regulation")
    db_session.add(s)
    await db_session.flush()
    vs = VoiceSession(debate_session_id=s.id, user_id="u1", status="ended")
    db_session.add(vs)
    await db_session.commit()
    create_mock = AsyncMock()
    monkeypatch.setattr(voice_score_svc.openrouter.chat.completions, "create", create_mock)

    dispatched = await derive_voice_session_patterns(db_session, vs.id)

    assert dispatched == 0
    create_mock.assert_not_called()


async def test_missing_session_returns_zero(db_session):
    assert await derive_voice_session_patterns(db_session, "nope") == 0


async def test_only_new_turns_are_processed(db_session, monkeypatch):
    # Two turns already derived live; only the third (new) turn should be
    # classified when derivation runs again.
    vs = await _make_voice_session(
        db_session,
        [
            "The GDPR precedent shows global uptake.",
            "Studies from the OECD back this up.",
            "So the regulation is clearly justified.",
        ],
        patterns_derived_count=2,
    )
    create_mock = AsyncMock(side_effect=[_cls("EvidenceBased", "Strong")])
    monkeypatch.setattr(voice_score_svc.openrouter.chat.completions, "create", create_mock)
    delay_mock = MagicMock()
    monkeypatch.setattr(voice_score_svc.remember_argument_task, "delay", delay_mock)

    dispatched = await derive_voice_session_patterns(db_session, vs.id)

    # Only the single un-derived turn is classified + dispatched.
    assert create_mock.call_count == 1
    assert dispatched == 1
    # Watermark advances to cover every turn seen so far.
    await db_session.refresh(vs)
    assert vs.patterns_derived_count == 3


async def test_pattern_written_to_note_for_fast_path(db_session, monkeypatch):
    # The fingerprint fast path reads the pattern straight off the note, so
    # derivation must persist detected_pattern/outcome synchronously.
    vs = await _make_voice_session(db_session, ["My neighbor said prices dropped."])
    create_mock = AsyncMock(side_effect=[_cls("AnecdotalEvidence", "Weak")])
    monkeypatch.setattr(voice_score_svc.openrouter.chat.completions, "create", create_mock)
    monkeypatch.setattr(voice_score_svc.remember_argument_task, "delay", MagicMock())

    await derive_voice_session_patterns(db_session, vs.id)

    note = (
        await db_session.execute(
            select(VoiceSessionNote).where(VoiceSessionNote.note_type == "transcript_user")
        )
    ).scalar_one()
    assert note.detected_pattern == "AnecdotalEvidence"
    assert note.outcome == "Lost"


async def test_repeated_derivation_does_not_double_count(db_session, monkeypatch):
    vs = await _make_voice_session(
        db_session,
        ["The GDPR precedent shows global uptake.", "Anyone against this hates progress."],
    )
    create_mock = AsyncMock(
        side_effect=[
            _cls("EvidenceBased", "Strong"),
            _cls("StrawMan", "Absent", fallacy="Strawman"),
        ]
    )
    monkeypatch.setattr(voice_score_svc.openrouter.chat.completions, "create", create_mock)
    delay_mock = MagicMock()
    monkeypatch.setattr(voice_score_svc.remember_argument_task, "delay", delay_mock)

    first = await derive_voice_session_patterns(db_session, vs.id)
    # A second sweep (e.g. the end-of-session dispatch after the live passes)
    # sees no new turns and must not re-classify or re-dispatch anything.
    second = await derive_voice_session_patterns(db_session, vs.id)

    assert first == 2
    assert second == 0
    assert create_mock.call_count == 2
    assert delay_mock.call_count == 2
