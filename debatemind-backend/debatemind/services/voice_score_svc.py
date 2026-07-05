"""Voice-session end-of-call scoring and Cognitive Fingerprint pattern derivation,
computed off the spoken transcript since voice debates run no per-turn judge."""

import asyncio
import json
import logging

from sqlalchemy import select, update

from debatemind.agents.client import openrouter
from debatemind.agents.prompts.extractor import EXTRACTOR_RESPONSE_SCHEMA, extractor_prompt
from debatemind.agents.prompts.judge import JUDGE_RESPONSE_SCHEMA, judge_prompt
from debatemind.config import settings
from debatemind.database import AsyncSessionLocal
from debatemind.models.session import DebateSession
from debatemind.models.voice_session import VoiceSession, VoiceSessionNote
from debatemind.worker.tasks import remember_argument_task

logger = logging.getLogger(__name__)

# Voice sessions currently being scored, to dedupe concurrent dispatches.
_scoring_in_flight: set[str] = set()

# Evidence tiers that count as a merited (Won) turn for the fingerprint.
_MERITED_EVIDENCE = {"Strong", "Moderate"}

# Cap on concurrent extractor calls per transcript, to avoid rate limits.
_MAX_CONCURRENT_CLASSIFICATIONS = 5


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
        return None

    session = (
        await db.execute(select(DebateSession).where(DebateSession.id == vs.debate_session_id))
    ).scalar_one_or_none()
    topic = session.topic if session else "the debate topic"

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


def _outcome_for(pattern_type: str, evidence_quality: str) -> str:
    """Won vs. Lost for a single voice turn's argument pattern."""
    if pattern_type == "EvidenceBased" and evidence_quality in _MERITED_EVIDENCE:
        return "Won"
    return "Lost"


async def _classify_turn(topic: str, argument: str) -> dict | None:
    """Classify one user turn; returns None for non-arguments (small talk)."""
    try:
        msg = await openrouter.chat.completions.create(
            model=settings.fast_model,
            max_tokens=300,
            messages=[{"role": "user", "content": extractor_prompt(topic, argument)}],
            response_format={"type": "json_schema", "json_schema": EXTRACTOR_RESPONSE_SCHEMA},
        )
        data = json.loads(msg.choices[0].message.content or "")
    except Exception:
        logger.exception("voice turn classification failed")
        return None

    pattern_type = data.get("pattern_type", "EvidenceBased")
    evidence_quality = data.get("evidence_quality", "Absent")
    fallacy = data.get("fallacy")
    # Extractor's neutral default for non-arguments (e.g. "Yes.") — skip these.
    if pattern_type == "EvidenceBased" and evidence_quality == "Absent" and not fallacy:
        return None
    return {
        "pattern_type": pattern_type,
        "evidence_quality": evidence_quality,
        "fallacy": fallacy,
        "reasoning": data.get("reasoning", ""),
        "reasoning_approach": data.get("reasoning_approach"),
        "cognitive_bias": data.get("cognitive_bias"),
    }


async def derive_voice_session_patterns(db, voice_session_id: str) -> int:
    """Classify user turns past the watermark into argument patterns; idempotent."""
    # Row lock so a live pass and the end-of-session pass can't claim the same turns.
    vs = (
        await db.execute(
            select(VoiceSession).where(VoiceSession.id == voice_session_id).with_for_update()
        )
    ).scalar_one_or_none()
    if not vs:
        return 0

    notes = (
        (
            await db.execute(
                select(VoiceSessionNote)
                .where(VoiceSessionNote.voice_session_id == voice_session_id)
                .where(VoiceSessionNote.note_type == "transcript_user")
                .order_by(VoiceSessionNote.created_at)
            )
        )
        .scalars()
        .all()
    )
    turns = [(n.id, n.content) for n in notes if n.content and n.content.strip()]

    start = vs.patterns_derived_count or 0
    if start >= len(turns):
        await db.commit()
        return 0

    pending = turns[start:]
    # Advance the watermark before classification so a concurrent pass can't claim these.
    user_id = vs.user_id
    debate_session_id = vs.debate_session_id
    vs.patterns_derived_count = len(turns)
    await db.commit()

    session = (
        await db.execute(select(DebateSession).where(DebateSession.id == debate_session_id))
    ).scalar_one_or_none()
    topic = session.topic if session else "the debate topic"

    sem = asyncio.Semaphore(_MAX_CONCURRENT_CLASSIFICATIONS)

    async def _classify_bounded(turn: str) -> dict | None:
        async with sem:
            return await _classify_turn(topic, turn)

    classified = await asyncio.gather(*(_classify_bounded(c) for _nid, c in pending))

    dispatched = 0
    for (note_id, turn), cls in zip(pending, classified):
        if not cls:
            continue
        outcome = _outcome_for(cls["pattern_type"], cls["evidence_quality"])
        # Fast path: write the pattern onto the note so the fingerprint reflects
        # it immediately, without waiting on the async Cognee/Neo4j write below.
        await db.execute(
            update(VoiceSessionNote)
            .where(VoiceSessionNote.id == note_id)
            .values(detected_pattern=cls["pattern_type"], outcome=outcome)
        )
        try:
            remember_argument_task.delay(
                user_id=user_id,
                session_id=debate_session_id,
                topic=topic,
                claim_text=turn,
                pattern_type=cls["pattern_type"],
                fallacy=cls["fallacy"],
                evidence_quality=cls["evidence_quality"],
                outcome=outcome,
                reasoning=cls["reasoning"],
                reasoning_approach=cls["reasoning_approach"],
                cognitive_bias=cls["cognitive_bias"],
            )
            dispatched += 1
        except Exception:
            logger.exception("remember_argument dispatch failed (voice patterns)")

    await db.commit()

    logger.info(
        "voice fingerprint: dispatched %d/%d new patterns for session %s",
        dispatched,
        len(pending),
        voice_session_id,
    )
    return dispatched


async def derive_voice_session_patterns_background(voice_session_id: str) -> None:
    """Fire-and-forget wrapper: own DB session, never raises."""
    try:
        async with AsyncSessionLocal() as db:
            await derive_voice_session_patterns(db, voice_session_id)
    except Exception:
        logger.exception("live voice pattern derivation failed for %s", voice_session_id)


async def score_voice_session_background(voice_session_id: str) -> None:
    """Fire-and-forget wrapper: scores + derives patterns, deduped, never raises."""
    if voice_session_id in _scoring_in_flight:
        return
    _scoring_in_flight.add(voice_session_id)
    try:
        async with AsyncSessionLocal() as db:
            vs = (
                await db.execute(select(VoiceSession).where(VoiceSession.id == voice_session_id))
            ).scalar_one_or_none()
            if vs is None or vs.score_logic is not None:
                return
            await compute_voice_session_score(db, voice_session_id)
            await derive_voice_session_patterns(db, voice_session_id)
    except Exception:
        logger.exception("background voice scoring failed for %s", voice_session_id)
    finally:
        _scoring_in_flight.discard(voice_session_id)
