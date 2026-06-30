import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func as sqlfunc
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.agents.pipeline import debate_pipeline
from debatemind.agents.state import DebateState
from debatemind.database import get_db
from debatemind.deps import current_user_id
from debatemind.models.session import DebateSession, Exchange
from debatemind.schemas.session import (
    MessageIn,
    SessionOut,
    SessionStartIn,
    SourceStatusOut,
    SourceUrlOut,
)
from debatemind.services import storage_svc
from debatemind.services.cognee_svc import improve_fingerprint
from debatemind.services.graph_svc import build_graph
from debatemind.worker.tasks import index_source_task

router = APIRouter()

# In-memory consecutive-wins counter per session (resets on server restart).
_session_wins: dict[str, int] = {}

MAX_SOURCE_BYTES = 20 * 1024 * 1024


@router.post("/start", response_model=SessionOut)
async def start_session(
    body: SessionStartIn,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    session = DebateSession(
        user_id=user_id,
        topic=body.topic,
        description=body.description,
        difficulty=body.difficulty,
        user_position=body.user_position,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    _session_wins[session.id] = 0
    return SessionOut(
        session_id=session.id,
        topic=session.topic,
        description=session.description or "",
        difficulty=session.difficulty,
        has_source=False,
        source_status="none",
    )


@router.post("/{session_id}/source")
async def upload_source(
    session_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    data = await file.read()
    if len(data) > MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 20MB limit")

    object_key = storage_svc.upload_source(session_id, file.filename, data)

    await db.execute(
        update(DebateSession)
        .where(DebateSession.id == session_id)
        .values(
            source_filename=file.filename,
            source_object_key=object_key,
            source_status="pending",
        )
    )
    await db.commit()

    index_source_task.delay(session_id, object_key)

    return JSONResponse(
        status_code=202,
        content={"status": "pending", "source_filename": file.filename},
    )


@router.get("/{session_id}/source-status", response_model=SourceStatusOut)
async def get_source_status(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return SourceStatusOut(source_status=session.source_status)


@router.get("/{session_id}/source-file", response_model=SourceUrlOut)
async def get_source_file(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.source_object_key:
        raise HTTPException(status_code=404, detail="No source file for this session")
    return SourceUrlOut(url=storage_svc.get_source_url(session.source_object_key))


@router.post("/{session_id}/message")
async def send_message(
    session_id: str,
    body: MessageIn,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")

    count_result = await db.execute(
        select(sqlfunc.count(Exchange.id)).where(Exchange.session_id == session_id)
    )
    turn = (count_result.scalar() or 0) + 1

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
        has_source=(session.source_status == "indexed"),
        source_context=[],
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

    final_state = await debate_pipeline.ainvoke(initial_state)
    _session_wins[session_id] = final_state.get("consecutive_wins", 0)

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
    db.add(exchange)
    await db.commit()

    opponent_text = final_state.get("opponent_response", "")

    async def event_stream():
        words = opponent_text.split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
            await asyncio.sleep(0.055)
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
        graph = await build_graph(user_id, session.topic)
        yield f"data: {json.dumps({'type': 'graph', 'data': graph.model_dump()})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{session_id}/end")
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
    asyncio.create_task(improve_fingerprint(user_id, session_id))
    _session_wins.pop(session_id, None)
    return {"status": "ended"}


@router.get("/{session_id}/graph")
async def get_graph(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404)
    return await build_graph(user_id, session.topic)
