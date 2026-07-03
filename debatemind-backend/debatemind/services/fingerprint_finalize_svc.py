"""Ordered end-of-session fingerprint writes: summary first, then re-index.

Sequencing (rather than firing summary + reindex as independent background
tasks) guarantees the session summary is captured by the same consolidating
cognify pass that follows it — see finalize_session_fingerprint and
finalize_voice_session_fingerprint below.
"""

import logging
from collections import Counter

from sqlalchemy import select

from debatemind.cognee import improve_fingerprint, remember_session_summary
from debatemind.database import AsyncSessionLocal
from debatemind.models.session import DebateSession, Exchange

logger = logging.getLogger(__name__)


async def write_chat_session_summary(user_id: str, session_id: str) -> None:
    """Read completed session exchanges and write a summary to the Cognee fingerprint.

    Gives the AI cross-session topic-level context: win rate on this topic,
    average thinking-style scores, and which patterns were weak this session.
    """
    try:
        async with AsyncSessionLocal() as db:
            session_row = (
                await db.execute(select(DebateSession).where(DebateSession.id == session_id))
            ).scalar_one_or_none()
            if not session_row:
                return
            exchanges = (
                (await db.execute(select(Exchange).where(Exchange.session_id == session_id)))
                .scalars()
                .all()
            )

        if not exchanges:
            return

        total = len(exchanges)
        won = sum(1 for e in exchanges if e.outcome == "Won")
        win_rate = won / total

        logics = [e.judge_logic for e in exchanges if e.judge_logic is not None]
        evidences = [e.judge_evidence for e in exchanges if e.judge_evidence is not None]
        rhetorics = [e.judge_rhetoric for e in exchanges if e.judge_rhetoric is not None]
        avg_logic = sum(logics) / len(logics) if logics else 0.0
        avg_evidence = sum(evidences) / len(evidences) if evidences else 0.0
        avg_rhetoric = sum(rhetorics) / len(rhetorics) if rhetorics else 0.0

        weak_counts = Counter(
            e.detected_pattern for e in exchanges if e.detected_pattern and e.outcome != "Won"
        )
        weak_patterns = [p for p, _ in weak_counts.most_common(3)]

        await remember_session_summary(
            user_id=user_id,
            session_id=session_id,
            topic=session_row.topic,
            mode="chat",
            difficulty=session_row.difficulty,
            rounds_played=total,
            win_rate=win_rate,
            avg_logic=avg_logic,
            avg_evidence=avg_evidence,
            avg_rhetoric=avg_rhetoric,
            weak_patterns=weak_patterns,
        )
    except Exception:
        logger.exception(
            "remember_session_summary failed for user %s session %s", user_id, session_id
        )


async def finalize_session_fingerprint(user_id: str, session_id: str) -> None:
    """Ordered end-of-session fingerprint update: summary first, then re-index."""
    await write_chat_session_summary(user_id, session_id)
    await improve_fingerprint(user_id)


async def finalize_voice_session_fingerprint(
    user_id: str,
    session_id: str,
    topic: str,
    difficulty: str,
    rounds_played: int,
    win_rate: float,
    weak_patterns: list[str],
    coaching_note: str = "",
) -> None:
    """Ordered end-of-voice-session fingerprint update: summary first, then re-index."""
    await remember_session_summary(
        user_id=user_id,
        session_id=session_id,
        topic=topic,
        mode="voice",
        difficulty=difficulty,
        rounds_played=rounds_played,
        win_rate=win_rate,
        avg_logic=0.0,
        avg_evidence=0.0,
        avg_rhetoric=0.0,
        weak_patterns=weak_patterns,
        coaching_note=coaching_note,
    )
    await improve_fingerprint(user_id)
