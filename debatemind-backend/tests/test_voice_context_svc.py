"""Unit tests for voice_context_svc — spanning voice + text in-session memory."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.session import DebateSession, Exchange
from debatemind.models.voice_session import VoiceSession, VoiceSessionNote
from debatemind.services.voice_context_svc import (
    MAX_SESSION_TURNS,
    recent_exchanges_with_voice,
    voice_transcript_exchanges,
)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _session(db) -> DebateSession:
    s = DebateSession(user_id="u1", topic="Remote work", user_position="against")
    db.add(s)
    await db.flush()
    return s


async def _voice(db, session_id, turns: list[tuple[str, str]]) -> VoiceSession:
    """turns is a list of (note_type suffix, text): ('ai', ...)/('user', ...)."""
    vs = VoiceSession(debate_session_id=session_id, user_id="u1", status="ended")
    db.add(vs)
    await db.flush()
    for kind, text in turns:
        db.add(
            VoiceSessionNote(voice_session_id=vs.id, note_type=f"transcript_{kind}", content=text)
        )
        await db.flush()  # distinct created_at ordering
    await db.commit()
    return vs


async def test_pairs_user_turn_with_following_ai_turn(db_session):
    s = await _session(db_session)
    await _voice(
        db_session,
        s.id,
        [
            ("ai", "Opening: remote work erodes cohesion."),  # leading AI — no user, skipped
            ("user", "But async comms keep teams aligned."),
            ("ai", "Alignment on paper, not culture."),
            ("user", "Culture is built through outcomes."),
            ("ai", "Outcomes without trust don't scale."),
        ],
    )

    pairs = await voice_transcript_exchanges(db_session, s.id, limit=10)

    assert pairs == [
        {
            "user_message": "But async comms keep teams aligned.",
            "opponent_response": "Alignment on paper, not culture.",
        },
        {
            "user_message": "Culture is built through outcomes.",
            "opponent_response": "Outcomes without trust don't scale.",
        },
    ]


async def test_limit_returns_most_recent_pairs(db_session):
    s = await _session(db_session)
    await _voice(
        db_session,
        s.id,
        [("user", "u1"), ("ai", "a1"), ("user", "u2"), ("ai", "a2"), ("user", "u3"), ("ai", "a3")],
    )

    pairs = await voice_transcript_exchanges(db_session, s.id, limit=2)

    assert [p["user_message"] for p in pairs] == ["u2", "u3"]


async def test_recent_exchanges_backfills_with_voice_when_no_text(db_session):
    s = await _session(db_session)
    await _voice(db_session, s.id, [("user", "voice point"), ("ai", "voice reply")])

    got = await recent_exchanges_with_voice(db_session, s.id, limit=3)

    assert got == [{"user_message": "voice point", "opponent_response": "voice reply"}]


async def test_text_exchanges_take_precedence_and_voice_fills_the_gap(db_session):
    s = await _session(db_session)
    await _voice(db_session, s.id, [("user", "voice point"), ("ai", "voice reply")])
    db_session.add(
        Exchange(
            session_id=s.id,
            turn_number=1,
            user_message="typed point",
            opponent_response="typed reply",
        )
    )
    await db_session.commit()

    got = await recent_exchanges_with_voice(db_session, s.id, limit=3)

    # One text turn, two voice slots to fill — voice context comes first (older).
    assert got[-1] == {"user_message": "typed point", "opponent_response": "typed reply"}
    assert {"user_message": "voice point", "opponent_response": "voice reply"} in got


async def test_enough_text_exchanges_skips_voice(db_session):
    s = await _session(db_session)
    await _voice(db_session, s.id, [("user", "voice point"), ("ai", "voice reply")])
    for i in range(1, 4):
        db_session.add(
            Exchange(
                session_id=s.id,
                turn_number=i,
                user_message=f"typed {i}",
                opponent_response=f"reply {i}",
            )
        )
    await db_session.commit()

    got = await recent_exchanges_with_voice(db_session, s.id, limit=3)

    assert len(got) == 3
    assert all("voice" not in g["user_message"] for g in got)


async def test_no_voice_no_text_is_empty(db_session):
    s = await _session(db_session)
    assert await recent_exchanges_with_voice(db_session, s.id, limit=3) == []
    assert await voice_transcript_exchanges(db_session, s.id, limit=3) == []


async def test_default_returns_whole_session_not_just_last_three(db_session):
    s = await _session(db_session)
    for i in range(1, 6):
        db_session.add(
            Exchange(
                session_id=s.id,
                turn_number=i,
                user_message=f"typed {i}",
                opponent_response=f"reply {i}",
            )
        )
    await db_session.commit()

    got = await recent_exchanges_with_voice(db_session, s.id)

    # No explicit limit → the opponent sees every turn of the session, not a tail.
    assert [g["user_message"] for g in got] == [f"typed {i}" for i in range(1, 6)]


async def test_ceiling_caps_a_runaway_session_to_most_recent(db_session):
    s = await _session(db_session)
    total = MAX_SESSION_TURNS + 5
    for i in range(1, total + 1):
        db_session.add(
            Exchange(
                session_id=s.id,
                turn_number=i,
                user_message=f"typed {i}",
                opponent_response=f"reply {i}",
            )
        )
    await db_session.commit()

    got = await recent_exchanges_with_voice(db_session, s.id)

    assert len(got) == MAX_SESSION_TURNS
    # The most recent MAX_SESSION_TURNS turns, chronological.
    assert got[-1]["user_message"] == f"typed {total}"
    assert got[0]["user_message"] == f"typed {total - MAX_SESSION_TURNS + 1}"
