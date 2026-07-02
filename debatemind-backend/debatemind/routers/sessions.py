import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import delete as sqldelete
from sqlalchemy import func as sqlfunc
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.agents.opponent import generate_continuation, generate_opening
from debatemind.agents.pipeline import debate_pipeline
from debatemind.agents.state import DebateState
from debatemind.cognee import improve_fingerprint, remember_session_summary
from debatemind.database import AsyncSessionLocal, get_db
from debatemind.deps import current_user_id
from debatemind.models.session import DebateSession, Exchange
from debatemind.models.voice_session import VoiceSession
from debatemind.schemas.graph import GraphOut
from debatemind.schemas.session import (
    EndSessionOut,
    MessageIn,
    SessionListItemOut,
    SessionOut,
    SessionStartIn,
    SessionSummaryOut,
    TranscriptExchange,
    TranscriptOut,
)
from debatemind.services.graph_svc import build_graph
from debatemind.services.mastery_svc import record_mastery_events
from debatemind.services.summary_svc import get_session_summary
from debatemind.services.title_svc import generate_session_title
from debatemind.services.transcript_svc import format_transcript_text
from debatemind.types import (
    NotFoundError,
    SuccessResponse,
    UnauthorizedError,
)

router = APIRouter()

# In-memory consecutive-wins counter per session (resets on server restart).
_session_wins: dict[str, int] = {}

logger = logging.getLogger(__name__)


async def _write_chat_session_summary(user_id: str, session_id: str) -> None:
    """Read completed session exchanges and write a summary to the Cognee fingerprint.

    Gives the AI cross-session topic-level context: win rate on this topic,
    average thinking-style scores, and which patterns were weak this session.
    Runs as a background task so end_session stays fast.
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

        from collections import Counter

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


async def _finalize_session_fingerprint(user_id: str, session_id: str) -> None:
    """Ordered end-of-session fingerprint update: summary first, then re-index.

    Sequencing these (rather than firing both as concurrent tasks) guarantees
    the session summary is written before the consolidating cognify runs.
    """
    await _write_chat_session_summary(user_id, session_id)
    await improve_fingerprint(user_id)


# User-meaningful pipeline nodes, in execution order. remember/prune are
# internal bookkeeping (memory-graph writes, mastery pruning) with no
# user-facing meaning and are intentionally not surfaced as stage events.
STAGE_ORDER = ["extract", "opponent", "judge", "mastery"]


@router.get(
    "",
    response_model=SuccessResponse[list[SessionListItemOut]],
    summary="List user sessions",
    description="Retrieve all debate sessions for the current user, newest first.",
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
    },
)
async def list_sessions(
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    count_subq = (
        select(Exchange.session_id, sqlfunc.count(Exchange.id).label("cnt"))
        .join(DebateSession, Exchange.session_id == DebateSession.id)
        .where(DebateSession.user_id == user_id)
        .group_by(Exchange.session_id)
        .subquery()
    )
    voice_subq = select(VoiceSession.debate_session_id).distinct().subquery()
    result = await db.execute(
        select(DebateSession, count_subq.c.cnt, voice_subq.c.debate_session_id)
        .outerjoin(count_subq, DebateSession.id == count_subq.c.session_id)
        .outerjoin(voice_subq, DebateSession.id == voice_subq.c.debate_session_id)
        .where(DebateSession.user_id == user_id)
        .order_by(DebateSession.started_at.desc())
    )
    rows = result.all()
    return SuccessResponse(
        data=[
            SessionListItemOut(
                session_id=session.id,
                topic_id=session.topic_id,
                topic=session.topic,
                title=session.title,
                difficulty=session.difficulty,
                position=session.user_position,
                status=session.status,
                overall_score=session.overall_score,
                exchanges=cnt or 0,
                has_voice_session=voice_session_marker is not None,
                started_at=session.started_at,
                ended_at=session.ended_at,
            )
            for session, cnt, voice_session_marker in rows
        ]
    )


@router.post(
    "/start",
    response_model=SuccessResponse[SessionOut],
    summary="Start debate session",
    description=(
        "Create a new debate session with the specified topic, difficulty level, and user position."
    ),
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
    },
)
async def start_session(
    body: SessionStartIn,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    session = DebateSession(
        user_id=user_id,
        topic_id=body.topic_id,
        topic=body.topic,
        description=body.description,
        difficulty=body.difficulty,
        user_position=body.user_position,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    _session_wins[session.id] = 0

    # Fire-and-forget: generate a short title in the background so /start stays fast.
    async def _write_title(sid: str, topic: str, description: str) -> None:
        title = await generate_session_title(topic, description)
        async with AsyncSessionLocal() as title_db:
            await title_db.execute(
                update(DebateSession).where(DebateSession.id == sid).values(title=title)
            )
            await title_db.commit()

    asyncio.create_task(_write_title(session.id, session.topic, session.description or ""))

    return SuccessResponse(
        data=SessionOut(
            session_id=session.id,
            topic_id=session.topic_id,
            topic=session.topic,
            description=session.description or "",
            difficulty=session.difficulty,
        )
    )


@router.post(
    "/{session_id}/message",
    summary="Send debate message",
    description=(
        "Submit a user argument and receive a streamed opponent response with "
        "judge scores (SSE). Events: stage | token | judge | graph | [DONE]."
    ),
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Session not found"},
    },
)
async def send_message(
    session_id: str,
    body: MessageIn,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
    x_model: str | None = Header(None, alias="X-Model"),
    x_judge_model: str | None = Header(None, alias="X-Judge-Model"),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")

    count_result = await db.execute(
        select(sqlfunc.count(Exchange.id)).where(Exchange.session_id == session_id)
    )
    turn = (count_result.scalar() or 0) + 1

    # Last 3 exchanges, chronological — gives the opponent real in-session memory
    # of what's already been argued, matching the pattern used by /continue.
    history_result = await db.execute(
        select(Exchange)
        .where(Exchange.session_id == session_id)
        .order_by(Exchange.turn_number.desc())
        .limit(3)
    )
    recent_exchanges = [
        {"user_message": ex.user_message, "opponent_response": ex.opponent_response}
        for ex in reversed(history_result.scalars().all())
    ]

    initial_state = DebateState(
        user_id=user_id,
        session_id=session_id,
        topic=session.topic,
        description=session.description or "",
        difficulty=session.difficulty,
        user_position=session.user_position,
        user_message=body.text,
        turn_number=turn,
        consecutive_wins=_session_wins.get(session_id, 0),
        recent_exchanges=recent_exchanges,
        model=x_model or None,
        judge_model=x_judge_model or None,
        extracted_pattern=None,
        extracted_fallacy=None,
        evidence_quality=None,
        weakness_context=[],
        opponent_response=None,
        judge_logic=None,
        judge_evidence=None,
        judge_rhetoric=None,
        judge_fallacy=None,
        outcome=None,
        mastery_events=[],
    )

    async def event_stream():
        final_state = dict(initial_state)
        stage_idx = 0
        yield f"data: {json.dumps({'type': 'stage', 'stage': STAGE_ORDER[0]})}\n\n"
        try:
            async for update in debate_pipeline.astream(initial_state, stream_mode="updates"):
                node_name, node_state = next(iter(update.items()))
                final_state.update(node_state)

                if node_name == "opponent":
                    opponent_text = final_state.get("opponent_response") or ""
                    words = opponent_text.split()
                    for i, word in enumerate(words):
                        chunk = word + (" " if i < len(words) - 1 else "")
                        yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
                        await asyncio.sleep(0.055)

                stage_idx += 1
                if stage_idx < len(STAGE_ORDER):
                    stage_event = {
                        "type": "stage",
                        "stage": STAGE_ORDER[stage_idx],
                    }
                    yield f"data: {json.dumps(stage_event)}\n\n"
        except Exception:
            logger.exception("debate pipeline failed for session %s turn %s", session_id, turn)
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "detail": "Something went wrong generating a response.",
                    }
                )
                + "\n\n"
            )
            return

        try:
            exchange = Exchange(
                session_id=session_id,
                turn_number=turn,
                user_message=body.text,
                opponent_response=final_state.get("opponent_response", ""),
                detected_pattern=final_state.get("extracted_pattern"),
                fallacy=final_state.get("judge_fallacy") or final_state.get("extracted_fallacy"),
                judge_logic=final_state.get("judge_logic"),
                judge_evidence=final_state.get("judge_evidence"),
                judge_rhetoric=final_state.get("judge_rhetoric"),
                outcome=final_state.get("outcome"),
            )
            # The FastAPI-injected `db` is already closed by the time the
            # StreamingResponse generator runs, so we open a fresh session here.
            async with AsyncSessionLocal() as save_db:
                save_db.add(exchange)
                await record_mastery_events(save_db, user_id, final_state.get("mastery_events", []))
                await save_db.commit()
            _session_wins[session_id] = final_state.get("consecutive_wins", 0)

            judge_payload = {
                "type": "judge",
                "logic": final_state.get("judge_logic"),
                "evidence": final_state.get("judge_evidence"),
                "rhetoric": final_state.get("judge_rhetoric"),
                "fallacy": final_state.get("judge_fallacy"),
                "outcome": final_state.get("outcome"),
                "mastery": final_state.get("mastery_events", []),
            }
            yield f"data: {json.dumps(judge_payload)}\n\n"
        except Exception:
            logger.exception("session persistence failed for session %s turn %s", session_id, turn)
            yield (
                "data: "
                + json.dumps(
                    {"type": "error", "detail": "Something went wrong saving the response."}
                )
                + "\n\n"
            )
            return

        try:
            graph = await build_graph(user_id, session.topic)
            yield f"data: {json.dumps({'type': 'graph', 'data': graph.model_dump()})}\n\n"
        except Exception:
            logger.exception("build_graph failed for session %s turn %s", session_id, turn)

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post(
    "/{session_id}/opening",
    summary="Stream opponent opening message",
    description=(
        "Generate the opponent's opening message for a fresh session and stream "
        "it token-by-token (SSE). Events: token | error | [DONE]. Nothing is "
        "persisted — the opening is ephemeral framing, not a scored exchange."
    ),
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Session not found"},
    },
)
async def session_opening(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
    x_model: str | None = Header(None, alias="X-Model"),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_stream():
        try:
            opening = await generate_opening(
                topic=session.topic,
                description=session.description or "",
                difficulty=session.difficulty,
                user_position=session.user_position,
                model=x_model or None,
            )
        except Exception:
            logger.exception("opening generation failed for session %s", session_id)
            yield (
                "data: "
                + json.dumps(
                    {"type": "error", "detail": "Something went wrong starting the debate."}
                )
                + "\n\n"
            )
            return

        words = opening.split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
            await asyncio.sleep(0.03)

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post(
    "/{session_id}/continue",
    summary="Stream opponent continuation message",
    description=(
        "Generate a re-engagement message for a returning user based on the last "
        "few exchanges, streamed token-by-token (SSE). Events: token | error | [DONE]. "
        "Nothing is persisted — continuation is ephemeral, like the opening."
    ),
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Session not found"},
    },
)
async def session_continue(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
    x_model: str | None = Header(None, alias="X-Model"),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")

    exchanges_result = await db.execute(
        select(Exchange)
        .where(Exchange.session_id == session_id)
        .order_by(Exchange.turn_number.desc())
        .limit(3)
    )
    exchanges = list(reversed(exchanges_result.scalars().all()))
    last_exchanges = [
        {"user_message": ex.user_message, "opponent_response": ex.opponent_response}
        for ex in exchanges
    ]

    async def event_stream():
        try:
            continuation = await generate_continuation(
                topic=session.topic,
                description=session.description or "",
                difficulty=session.difficulty,
                user_position=session.user_position,
                last_exchanges=last_exchanges,
                model=x_model or None,
            )
        except Exception:
            logger.exception("continuation generation failed for session %s", session_id)
            yield (
                "data: "
                + json.dumps(
                    {"type": "error", "detail": "Something went wrong generating a continuation."}
                )
                + "\n\n"
            )
            return

        words = continuation.split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
            await asyncio.sleep(0.03)

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post(
    "/{session_id}/end",
    response_model=SuccessResponse[EndSessionOut],
    summary="End debate session",
    description="Mark the debate session as ended and trigger background fingerprint improvement.",
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Session not found"},
    },
)
async def end_session(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.execute(
        update(DebateSession)
        .where(DebateSession.id == session_id)
        .values(status="ended", ended_at=datetime.now(timezone.utc))
    )
    await db.commit()

    _session_wins.pop(session_id, None)

    # Finalize the fingerprint in one ordered background task: write the
    # session summary first, THEN re-index. Running these as two independent
    # tasks (as before) let improve_fingerprint's cognify race ahead of the
    # summary write, so the summary could miss the current re-index pass.
    def _log_finalize_exc(task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception():
            logger.error(
                "session fingerprint finalize failed for user %s session %s",
                user_id,
                session_id,
                exc_info=task.exception(),
            )

    finalize_task = asyncio.create_task(_finalize_session_fingerprint(user_id, session_id))
    finalize_task.add_done_callback(_log_finalize_exc)

    return SuccessResponse(data=EndSessionOut(status="ended"))


@router.delete(
    "/{session_id}",
    response_model=SuccessResponse[EndSessionOut],
    summary="Delete debate session",
    description="Permanently delete a debate session and all of its exchanges.",
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Session not found"},
    },
)
async def delete_session(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")

    # Remove child exchanges first (no DB-level cascade defined), then the session.
    await db.execute(sqldelete(Exchange).where(Exchange.session_id == session_id))
    await db.execute(sqldelete(DebateSession).where(DebateSession.id == session_id))
    await db.commit()

    _session_wins.pop(session_id, None)
    return SuccessResponse(data=EndSessionOut(status="deleted"))


@router.get(
    "/{session_id}/graph",
    response_model=SuccessResponse[GraphOut],
    summary="Get session knowledge graph",
    description=(
        "Retrieve the knowledge graph of argument patterns and weaknesses for the session topic."
    ),
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Session not found"},
    },
)
async def get_graph(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404)
    return SuccessResponse(data=await build_graph(user_id, session.topic))


@router.get(
    "/{session_id}/summary",
    response_model=SuccessResponse[SessionSummaryOut],
    summary="Get session summary",
    description=(
        "Retrieve aggregate score, exchange count, and per-pattern "
        "before/after weakness weight changes for a completed session."
    ),
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Session not found"},
    },
)
async def get_summary(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    summary = await get_session_summary(db, user_id, session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SuccessResponse(data=summary)


async def _build_transcript(session_id: str, user_id: str, db: AsyncSession) -> TranscriptOut:
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")

    ex_result = await db.execute(
        select(Exchange).where(Exchange.session_id == session_id).order_by(Exchange.turn_number)
    )
    exchanges = ex_result.scalars().all()
    return TranscriptOut(
        session_id=session.id,
        topic_id=session.topic_id,
        topic=session.topic,
        difficulty=session.difficulty,
        started_at=session.started_at,
        exchanges=[
            TranscriptExchange(
                turn_number=e.turn_number,
                user_message=e.user_message,
                opponent_response=e.opponent_response or "",
                judge_logic=e.judge_logic,
                judge_evidence=e.judge_evidence,
                judge_rhetoric=e.judge_rhetoric,
                fallacy=e.fallacy,
                outcome=e.outcome,
                created_at=e.created_at,
            )
            for e in exchanges
        ],
    )


@router.get(
    "/{session_id}/transcript",
    response_model=SuccessResponse[TranscriptOut],
    summary="Get session transcript",
    description=(
        "Retrieve the full ordered exchange history for a session, with judge scores inline."
    ),
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Session not found"},
    },
)
async def get_transcript(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return SuccessResponse(data=await _build_transcript(session_id, user_id, db))


@router.get(
    "/{session_id}/transcript/export",
    summary="Export session transcript",
    description="Download the session transcript as a plain-text file.",
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Session not found"},
    },
)
async def export_transcript(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    transcript = await _build_transcript(session_id, user_id, db)
    text = format_transcript_text(transcript)
    return PlainTextResponse(
        text,
        headers={"Content-Disposition": f'attachment; filename="transcript_{session_id}.txt"'},
    )
