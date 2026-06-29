import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func as sqlfunc
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.agents.pipeline import debate_pipeline
from debatemind.agents.state import DebateState
from debatemind.database import get_db
from debatemind.deps import current_user_id
from debatemind.models.session import DebateSession, Exchange
from debatemind.schemas.session import MessageIn, SessionOut, SessionStartIn
from debatemind.services.cognee_svc import improve_fingerprint
from debatemind.services.graph_svc import build_graph
from debatemind.websocket.manager import ws_manager

router = APIRouter()

# In-memory consecutive-wins counter per session (resets on server restart).
_session_wins: dict[str, int] = {}


@router.post("/start", response_model=SessionOut)
async def start_session(
    body: SessionStartIn,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    session = DebateSession(
        user_id=user_id,
        topic=body.topic,
        difficulty=body.difficulty,
        user_position=body.user_position,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    _session_wins[session.id] = 0
    return SessionOut(session_id=session.id, topic=session.topic, difficulty=session.difficulty)


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
        difficulty=session.difficulty,
        user_position=session.user_position,
        user_message=body.text,
        turn_number=turn,
        consecutive_wins=_session_wins.get(session_id, 0),
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

    async def _push_graph():
        await asyncio.sleep(2)
        graph = await build_graph(user_id, session.topic)
        await ws_manager.broadcast_graph(session_id, graph.model_dump())

    asyncio.create_task(_push_graph())

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
