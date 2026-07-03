"""Session-level LLM-as-judge scoring.

The per-exchange judge (agents/judge.py) scores each turn in isolation;
nothing ever wrote DebateSession.overall_score, so the session list showed no
score. This service closes that gap: it feeds the full transcript — user and
opponent arguments plus the per-turn judge scores and outcomes — to an LLM
judge for a session-level 1-10 score and persists it. If the LLM call fails,
it falls back to the plain average of the per-exchange judge dimensions so an
ended session with turns always ends up with a score.
"""

import json
import logging

from sqlalchemy import select, update

from debatemind.agents.client import openrouter
from debatemind.agents.prompts.session_judge import (
    SESSION_JUDGE_RESPONSE_SCHEMA,
    session_judge_prompt,
)
from debatemind.config import settings
from debatemind.database import AsyncSessionLocal
from debatemind.models.session import DebateSession, Exchange

logger = logging.getLogger(__name__)

# Sessions currently being scored by a background task in this process —
# prevents list_sessions from dispatching duplicate judges for the same
# session while one is already in flight.
_scoring_in_flight: set[str] = set()


def _format_transcript(exchanges) -> str:
    lines = []
    for e in exchanges:
        lines.append(f"[Turn {e.turn_number}]")
        lines.append(f"User: {e.user_message}")
        lines.append(f"Opponent: {e.opponent_response or ''}")
        judge_bits = []
        if e.judge_logic is not None:
            judge_bits.append(f"logic {e.judge_logic:g}")
        if e.judge_evidence is not None:
            judge_bits.append(f"evidence {e.judge_evidence:g}")
        if e.judge_rhetoric is not None:
            judge_bits.append(f"rhetoric {e.judge_rhetoric:g}")
        if e.outcome:
            judge_bits.append(f"outcome {e.outcome}")
        if e.fallacy:
            judge_bits.append(f"fallacy {e.fallacy}")
        if judge_bits:
            lines.append(f"Per-turn judge: {', '.join(judge_bits)}")
        lines.append("")
    return "\n".join(lines).strip()


def _fallback_average(exchanges) -> float | None:
    raw = [
        s
        for e in exchanges
        for s in (e.judge_logic, e.judge_evidence, e.judge_rhetoric)
        if s is not None
    ]
    return round(sum(raw) / len(raw), 1) if raw else None


async def _llm_session_score(session: DebateSession, exchanges) -> float:
    prompt = session_judge_prompt(
        topic=session.topic,
        description=session.description or "",
        difficulty=session.difficulty,
        user_position=session.user_position,
        transcript=_format_transcript(exchanges),
    )
    msg = await openrouter.chat.completions.create(
        model=settings.fast_model,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_schema", "json_schema": SESSION_JUDGE_RESPONSE_SCHEMA},
    )
    data = json.loads(msg.choices[0].message.content or "")
    return round(min(10.0, max(1.0, float(data["score"]))), 1)


async def compute_session_score(db, user_id: str, session_id: str) -> float | None:
    """LLM-judge the session transcript and persist DebateSession.overall_score.

    Returns the persisted score, or None when there is nothing to score
    (missing/foreign session or a session with no exchanges).
    """
    session = (
        await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    ).scalar_one_or_none()
    if not session or session.user_id != user_id:
        return None

    exchanges = (
        (
            await db.execute(
                select(Exchange)
                .where(Exchange.session_id == session_id)
                .order_by(Exchange.turn_number)
            )
        )
        .scalars()
        .all()
    )
    if not exchanges:
        return None

    try:
        score = await _llm_session_score(session, exchanges)
    except Exception:
        logger.exception(
            "LLM session scoring failed for session %s — falling back to exchange average",
            session_id,
        )
        score = _fallback_average(exchanges)
        if score is None:
            return None

    await db.execute(
        update(DebateSession).where(DebateSession.id == session_id).values(overall_score=score)
    )
    await db.commit()
    return score


async def score_session_background(user_id: str, session_id: str) -> None:
    """Fire-and-forget wrapper: own DB session, never raises, de-duplicates."""
    if session_id in _scoring_in_flight:
        return
    _scoring_in_flight.add(session_id)
    try:
        async with AsyncSessionLocal() as db:
            await compute_session_score(db, user_id, session_id)
    except Exception:
        logger.exception("background session scoring failed for session %s", session_id)
    finally:
        _scoring_in_flight.discard(session_id)
