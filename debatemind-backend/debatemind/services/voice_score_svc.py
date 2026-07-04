"""Voice-session Logic / Evidence / Rhetoric scoring.

Text debates score every turn via agents/judge.py and surface a live
SessionScoreBar. Voice debates run no judge — observations go to
VoiceSessionNote and the score bar stayed 0 / 0 / 0. This service closes that
gap: after a voice session ends it feeds the spoken transcript (the user's
turns vs. the AI's turns) to the same per-exchange judge rubric and persists an
aggregate logic/evidence/rhetoric read on the VoiceSession row, which the
`GET /api/voice/{id}/summary` endpoint then exposes to the UI.

Dispatched fire-and-forget from voice_agent/router.py via asyncio.create_task —
same in-process pattern as session_score_svc.score_session_background (not
Celery, so it shares the request event loop and avoids the asyncpg
loop-binding pitfalls the Cognee tasks work around).
"""

import json
import logging

from sqlalchemy import select, update

from debatemind.agents.client import openrouter
from debatemind.agents.prompts.judge import JUDGE_RESPONSE_SCHEMA, judge_prompt
from debatemind.config import settings
from debatemind.database import AsyncSessionLocal
from debatemind.models.session import DebateSession
from debatemind.models.voice_session import VoiceSession, VoiceSessionNote

logger = logging.getLogger(__name__)

# Voice sessions currently being scored in this process — prevents a double
# dispatch (e.g. end_voice_session tool + a client disconnect) from running two
# judges for the same session.
_scoring_in_flight: set[str] = set()


async def compute_voice_session_score(db, voice_session_id: str) -> dict | None:
    """LLM-judge the voice transcript and persist the three score columns.

    Returns {"logic", "evidence", "rhetoric"} floats, or None when there is
    nothing to score (missing session, or the user never actually argued).
    """
    vs = (
        await db.execute(select(VoiceSession).where(VoiceSession.id == voice_session_id))
    ).scalar_one_or_none()
    if not vs:
        return None

    notes = (
        (
            await db.execute(
                select(VoiceSessionNote)
                .where(VoiceSessionNote.voice_session_id == voice_session_id)
                .order_by(VoiceSessionNote.created_at)
            )
        )
        .scalars()
        .all()
    )
    user_turns = [n.content for n in notes if n.note_type == "transcript_user"]
    ai_turns = [n.content for n in notes if n.note_type == "transcript_ai"]
    if not user_turns:
        # No spoken argument from the user — nothing to score. Leaving the
        # columns NULL keeps the bar at 0/0/0, which is truthful.
        return None

    session = (
        await db.execute(select(DebateSession).where(DebateSession.id == vs.debate_session_id))
    ).scalar_one_or_none()
    topic = session.topic if session else "the debate topic"

    # Aggregate the whole spoken debate into one exchange: all the user's turns
    # vs. all the opponent's, judged against the same rubric a text turn gets.
    user_argument = "\n\n".join(user_turns)
    opponent_argument = "\n\n".join(ai_turns) or "(no opponent turns recorded)"

    try:
        msg = await openrouter.chat.completions.create(
            model=settings.fast_model,
            max_tokens=300,
            messages=[
                {"role": "user", "content": judge_prompt(topic, user_argument, opponent_argument)}
            ],
            response_format={"type": "json_schema", "json_schema": JUDGE_RESPONSE_SCHEMA},
        )
        data = json.loads(msg.choices[0].message.content or "")
        scores = {
            "logic": float(data.get("logic", 5)),
            "evidence": float(data.get("evidence", 5)),
            "rhetoric": float(data.get("rhetoric", 5)),
        }
    except Exception:
        logger.exception("voice session scoring failed for %s", voice_session_id)
        return None

    await db.execute(
        update(VoiceSession)
        .where(VoiceSession.id == voice_session_id)
        .values(
            score_logic=scores["logic"],
            score_evidence=scores["evidence"],
            score_rhetoric=scores["rhetoric"],
        )
    )
    await db.commit()
    return scores


async def score_voice_session_background(voice_session_id: str) -> None:
    """Fire-and-forget wrapper: own DB session, never raises, de-duplicates."""
    if voice_session_id in _scoring_in_flight:
        return
    _scoring_in_flight.add(voice_session_id)
    try:
        async with AsyncSessionLocal() as db:
            await compute_voice_session_score(db, voice_session_id)
    except Exception:
        logger.exception("background voice scoring failed for %s", voice_session_id)
    finally:
        _scoring_in_flight.discard(voice_session_id)
