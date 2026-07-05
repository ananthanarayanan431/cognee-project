"""Shared in-session history for the text opponent, spanning voice + text.

A debate session can be argued by voice and later reopened in text (or vice
versa). The text pipeline feeds the opponent the last few `recent_exchanges`
(user_message / opponent_response pairs) for in-session memory — but those come
only from Postgres Exchange rows, which voice never writes. So a session that
was argued entirely by voice looked brand-new the moment the user switched to
text: the opponent had no idea what had just been discussed.

recent_exchanges_with_voice() closes that: it returns the text exchanges as
before, and when there are fewer than `limit` of them it backfills the
remaining slots with the tail of the spoken voice transcript — so the opponent
picks up the conversation with the voice context in hand, whether it is
re-engaging (/continue) or answering the first typed argument (/message).

The opponent (agents/opponent.py) is a plain LLM call with no history tools, so
this window is the *only* memory it has of the current debate — anything past it
is invisible. We therefore hand it the whole session rather than a short tail:
a full debate is a few thousand tokens against a 100k+ context, so the coherence
win (no forgetting earlier concessions/contradictions, no repeating counters)
far outweighs the token cost. MAX_SESSION_TURNS is a safety ceiling so a
pathologically long session can't blow up the prompt — for any real debate it's
effectively "everything".
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.models.session import Exchange
from debatemind.models.voice_session import VoiceSession, VoiceSessionNote

# Ceiling on recent turns replayed to the opponent — a token guardrail, not a design constraint.
MAX_SESSION_TURNS = 50


def _pair_transcript(notes: list[VoiceSessionNote]) -> list[dict[str, str]]:
    """Fold a chronological voice transcript into {user_message,
    opponent_response} pairs, matching the text Exchange shape.

    Each user turn is paired with the AI turn that follows it. A leading AI
    turn (the spoken opening, before the user has said anything) has no user
    message to attach to and is skipped — it carries no user argument the
    opponent needs to remember.
    """
    pairs: list[dict[str, str]] = []
    pending_user: str | None = None
    for n in notes:
        text = (n.content or "").strip()
        if not text:
            continue
        if n.note_type == "transcript_user":
            # Two user turns in a row (the AI stayed silent): flush the first
            # with an empty opponent response rather than dropping it.
            if pending_user is not None:
                pairs.append({"user_message": pending_user, "opponent_response": ""})
            pending_user = text
        elif n.note_type == "transcript_ai":
            if pending_user is not None:
                pairs.append({"user_message": pending_user, "opponent_response": text})
                pending_user = None
    if pending_user is not None:
        pairs.append({"user_message": pending_user, "opponent_response": ""})
    return pairs


async def voice_transcript_exchanges(
    db: AsyncSession, debate_session_id: str, limit: int
) -> list[dict[str, str]]:
    """The last `limit` voice-transcript exchange pairs for a debate session
    (most recent voice session), chronological. Empty when there's no voice
    transcript to draw on."""
    if limit <= 0:
        return []

    vs = (
        await db.execute(
            select(VoiceSession)
            .where(VoiceSession.debate_session_id == debate_session_id)
            .order_by(VoiceSession.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not vs:
        return []

    notes = (
        (
            await db.execute(
                select(VoiceSessionNote)
                .where(VoiceSessionNote.voice_session_id == vs.id)
                .where(VoiceSessionNote.note_type.in_(("transcript_user", "transcript_ai")))
                .order_by(VoiceSessionNote.created_at)
            )
        )
        .scalars()
        .all()
    )
    return _pair_transcript(list(notes))[-limit:]


async def recent_exchanges_with_voice(
    db: AsyncSession, session_id: str, limit: int = MAX_SESSION_TURNS
) -> list[dict[str, str]]:
    """The current session's exchanges for the opponent's in-session memory: the
    text Exchange rows (most recent `limit`), backfilled with the tail of the
    voice transcript when there aren't enough text turns to fill the window
    (e.g. a voice session just reopened in text). Defaults to the whole session
    up to MAX_SESSION_TURNS."""
    text_rows = (
        (
            await db.execute(
                select(Exchange)
                .where(Exchange.session_id == session_id)
                .order_by(Exchange.turn_number.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    text_exchanges = [
        {"user_message": ex.user_message, "opponent_response": ex.opponent_response or ""}
        for ex in reversed(text_rows)
    ]
    if len(text_exchanges) >= limit:
        return text_exchanges

    voice = await voice_transcript_exchanges(db, session_id, limit - len(text_exchanges))
    return voice + text_exchanges
