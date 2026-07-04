"""Voice-session end-of-call analysis: scoring + Cognitive Fingerprint patterns.

Text debates score every turn via agents/judge.py and classify every turn via
agents/extractor.py — the first feeds the live SessionScoreBar, the second
feeds the Cognitive Fingerprint (ArgumentRecord nodes in Cognee/Neo4j, read
back by cognee/session_fingerprint.py). Voice debates run neither per turn:
the realtime AI only *optionally* logs observations via the
`save_debate_observation` tool, which in practice it rarely does, so the score
bar stayed 0/0/0 and the fingerprint stayed empty for voice-only sessions.

This service closes both gaps deterministically off the spoken transcript,
which IS captured reliably every session:

  * compute_voice_session_score() feeds the user's turns vs. the AI's to the
    same judge rubric a text turn gets and persists an aggregate
    logic/evidence/rhetoric read on the VoiceSession row (exposed by
    GET /api/voice/{id}/summary).
  * derive_voice_session_patterns() classifies each user turn with the same
    extractor a text turn gets and writes an ArgumentRecord per real argument,
    so the fingerprint graph populates for voice exactly as it does for text.

Dispatched fire-and-forget from voice_agent/router.py via asyncio.create_task —
same in-process pattern as session_score_svc.score_session_background. The
Cognee writes are still handed to Celery (remember_argument_task) rather than
awaited in-process, matching the text pipeline and side-stepping the asyncpg
loop-binding pitfalls the Cognee tasks work around.
"""

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

# Voice sessions currently being scored in this process — prevents a double
# dispatch (e.g. end_voice_session tool + a client disconnect) from running two
# judges for the same session.
_scoring_in_flight: set[str] = set()

# Evidence tiers that count as "the turn actually stood on something" — used to
# decide Won vs. Lost when tallying the fingerprint (voice has no per-turn judge
# comparing the user against the opponent, so we read merit off the turn itself).
_MERITED_EVIDENCE = {"Strong", "Moderate"}


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


def _outcome_for(pattern_type: str, evidence_quality: str) -> str:
    """Won vs. Lost for a single voice turn's argument pattern.

    Mirrors the intent of _COGNEE_NOTE_MAP in voice_agent/tools.py: an
    evidence-backed argument is a strength, everything else (fallacies,
    concessions, bare assertions) a weakness. This is what colours the
    fingerprint node green vs. red via the win-rate in session_fingerprint.py.
    """
    if pattern_type == "EvidenceBased" and evidence_quality in _MERITED_EVIDENCE:
        return "Won"
    return "Lost"


async def _classify_turn(topic: str, argument: str) -> dict | None:
    """Run one user turn through the same extractor a text turn gets.

    Returns the classification dict, or None when the turn is not a real
    argument (small talk, a bare question) so it never pollutes the graph —
    the extractor flags these as EvidenceBased / Absent / no-fallacy.
    """
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
    # Neutral small-talk default the extractor emits for non-arguments — skip so
    # "Yes." / "cut the call" don't show up as EvidenceBased nodes.
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
    """Classify the voice transcript into argument patterns and record them.

    Reads the user's spoken turns, classifies each with the shared extractor,
    and dispatches one remember_argument_task per real argument so the
    Cognitive Fingerprint (Cognee/Neo4j ArgumentRecord nodes, read by
    session_fingerprint.py) populates for voice sessions the same way it does
    for text. Returns the number of patterns dispatched.
    """
    vs = (
        await db.execute(select(VoiceSession).where(VoiceSession.id == voice_session_id))
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
    user_turns = [n.content for n in notes if n.content and n.content.strip()]
    if not user_turns:
        return 0

    session = (
        await db.execute(select(DebateSession).where(DebateSession.id == vs.debate_session_id))
    ).scalar_one_or_none()
    topic = session.topic if session else "the debate topic"

    classified = await asyncio.gather(*(_classify_turn(topic, t) for t in user_turns))

    dispatched = 0
    for turn, cls in zip(user_turns, classified):
        if not cls:
            continue
        outcome = _outcome_for(cls["pattern_type"], cls["evidence_quality"])
        try:
            remember_argument_task.delay(
                user_id=vs.user_id,
                session_id=vs.debate_session_id,
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

    logger.info(
        "voice fingerprint: dispatched %d/%d patterns for session %s",
        dispatched,
        len(user_turns),
        voice_session_id,
    )
    return dispatched


async def score_voice_session_background(voice_session_id: str) -> None:
    """Fire-and-forget wrapper: own DB session, never raises, de-duplicates.

    Runs both the aggregate score and the fingerprint pattern derivation. Guards
    on the persisted score so a second dispatch (the AI's end_voice_session tool
    plus the client's disconnect both fire it) doesn't re-run the classifier and
    double-write ArgumentRecord nodes.
    """
    if voice_session_id in _scoring_in_flight:
        return
    _scoring_in_flight.add(voice_session_id)
    try:
        async with AsyncSessionLocal() as db:
            vs = (
                await db.execute(select(VoiceSession).where(VoiceSession.id == voice_session_id))
            ).scalar_one_or_none()
            if vs is None or vs.score_logic is not None:
                # Missing, or already processed by an earlier dispatch.
                return
            await compute_voice_session_score(db, voice_session_id)
            await derive_voice_session_patterns(db, voice_session_id)
    except Exception:
        logger.exception("background voice scoring failed for %s", voice_session_id)
    finally:
        _scoring_in_flight.discard(voice_session_id)
