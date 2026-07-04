"""
Voice agent REST endpoints.

Pattern (WebRTC + ephemeral key + server-side tool execution):

  Browser                    Backend                        OpenAI
    |                           |                              |
    | POST /api/voice/{id}/token|                              |
    |-------------------------->|  POST /v1/realtime/client_secrets
    |                           |----------------------------->|
    |                           |  ephemeral key + session id  |
    |                           |<-----------------------------|
    |                           |  (creates VoiceSession in DB)|
    |  {client_secret, vs_id}   |                              |
    |<--------------------------|                              |
    |                           |                              |
    |  WebRTC + ephemeral key (direct, backend not in path)   |
    |<------------------------------------------------------------>|
    |  AI calls tool via data-channel event                        |
    |  POST /api/voice/{id}/tools                                  |
    |-------------------------->|  execute_tool() → DB query   |
    |  tool result JSON         |<-----------------------------|
    |<--------------------------|                              |
    |  send result via data-channel → AI continues speaking   |
    |------------------------------------------------------------>|

Endpoints
─────────
POST /{session_id}/token           Mint ephemeral key + create VoiceSession row
POST /{session_id}/tools           Execute a tool call dispatched by the AI
POST /{session_id}/transcript-line Persist a single transcript line (user or AI)
GET  /{session_id}/summary         Load the most recent voice session's notes + transcript
"""

import asyncio
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.config import settings
from debatemind.database import AsyncSessionLocal, get_db
from debatemind.deps import current_user_id
from debatemind.models.session import DebateSession
from debatemind.models.voice_session import VoiceSession, VoiceSessionNote
from debatemind.schemas.voice import (
    ToolCallIn,
    TranscriptLineIn,
    TranscriptLineOut,
    TranscriptLineSavedOut,
    VoiceSessionSummaryOut,
)
from debatemind.services.voice_score_svc import (
    derive_voice_session_patterns_background,
    score_voice_session_background,
)
from debatemind.types.responses import SuccessResponse
from debatemind.voice_agent.session import create_voice_session
from debatemind.voice_agent.tools import execute_tool

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{session_id}/token",
    summary="Mint voice session token",
    description=(
        "Creates an OpenAI Realtime ephemeral key scoped to this debate session "
        "and registers a VoiceSession row in the database. "
        "The browser uses `client_secret.value` to open a WebRTC peer connection "
        "directly with OpenAI and passes `voice_session_id` to the tools endpoint. "
        "Tokens expire in ~60 seconds — call this immediately before connecting."
    ),
)
async def get_voice_token(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Response shape (passthrough from OpenAI + our voice_session_id):

        {
          "client_secret": {"value": "ek_...", "expires_at": <unix ts>},
          "id": "sess_...",          // OpenAI session id
          "model": "gpt-4o-realtime-preview",
          ...
          "voice_session_id": "..."  // our DB row id — pass to /tools
        }
    """
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="Voice feature not configured — set OPENAI_API_KEY on the server.",
        )

    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        token_data = await create_voice_session(session, user_id)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "OpenAI client_secrets error for session %s: %s %s",
            session_id,
            exc.response.status_code,
            exc.response.text,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Failed to create voice session ({exc.response.status_code})",
        ) from exc
    except Exception:
        logger.exception("Unexpected error minting voice token for session %s", session_id)
        raise HTTPException(status_code=502, detail="Failed to create voice session")

    logger.info(
        "Voice token minted: debate=%s vs=%s user=%s",
        session_id,
        token_data.get("voice_session_id"),
        user_id,
    )
    return SuccessResponse(data=token_data)


@router.post(
    "/{session_id}/tools",
    summary="Execute AI tool call",
    description=(
        "Executes a function-tool call dispatched by OpenAI during a voice session. "
        "The browser receives tool-call events via the WebRTC data channel, POSTs here "
        "to run the tool, then sends the JSON result back via data-channel so the AI "
        "can continue speaking."
    ),
)
async def run_tool(
    session_id: str,
    body: ToolCallIn,
    user_id: str = Depends(current_user_id),
):
    async with AsyncSessionLocal() as db:
        vs_row = await db.execute(
            select(VoiceSession).where(VoiceSession.id == body.voice_session_id)
        )
        vs = vs_row.scalar_one_or_none()

        if not vs or vs.user_id != user_id or vs.debate_session_id != session_id:
            raise HTTPException(status_code=404, detail="Voice session not found")

        result = await execute_tool(
            db=db,
            tool_name=body.tool,
            arguments=body.arguments,
            voice_session_id=vs.id,
            debate_session_id=vs.debate_session_id,
            user_id=user_id,
        )

    if "error" in result:
        logger.warning(
            "Tool %s returned error for vs=%s: %s",
            body.tool,
            body.voice_session_id,
            result["error"],
        )

    # When the AI ends the session, LLM-judge the spoken transcript for
    # Logic/Evidence/Rhetoric so the SessionScoreBar reflects voice debates too.
    # Fire-and-forget on the request loop; the client polls /summary for the
    # scores once the judge lands. score_voice_session_background de-dupes and
    # never raises. Voice writes no Exchange rows, so text scoring never covers
    # this path — hence a dedicated voice scorer.
    if body.tool == "end_voice_session" and "error" not in result:
        asyncio.create_task(score_voice_session_background(body.voice_session_id))

    return SuccessResponse(data=result)


@router.post(
    "/{session_id}/transcript-line",
    response_model=SuccessResponse[TranscriptLineSavedOut],
    summary="Persist a single transcript line",
    description=(
        "Saves one transcript line (user speech or AI utterance) to the database "
        "so voice session history can be replayed after the session ends."
    ),
)
async def save_transcript_line(
    session_id: str,
    body: TranscriptLineIn,
    user_id: str = Depends(current_user_id),
):
    if not body.text.strip():
        return SuccessResponse(data=TranscriptLineSavedOut(ok=True))

    async with AsyncSessionLocal() as db:
        vs_result = await db.execute(
            select(VoiceSession).where(
                VoiceSession.id == body.voice_session_id,
                VoiceSession.user_id == user_id,
                VoiceSession.debate_session_id == session_id,
            )
        )
        vs = vs_result.scalar_one_or_none()
        if not vs:
            raise HTTPException(status_code=404, detail="Voice session not found")

        vs_id = vs.id
        note = VoiceSessionNote(
            voice_session_id=vs_id,
            note_type=f"transcript_{body.speaker}",
            content=body.text.strip(),
        )
        db.add(note)
        await db.commit()

    # Build the Cognitive Fingerprint live: each user turn is classified into an
    # argument pattern as soon as it's transcribed, so the graph grows while the
    # user is still speaking (the frontend polls the graph every few seconds)
    # instead of only filling in after hang-up. Fire-and-forget; watermark-
    # idempotent, so it never double-counts with the end-of-session sweep.
    if body.speaker == "user":
        asyncio.create_task(derive_voice_session_patterns_background(vs_id))

    return SuccessResponse(data=TranscriptLineSavedOut(ok=True))


@router.get(
    "/{session_id}/summary",
    response_model=SuccessResponse[VoiceSessionSummaryOut],
    summary="Load most recent voice session history",
    description=(
        "Returns the transcript, AI observations (fallacies, strong arguments, "
        "concessions, position flips), closing summary, and duration for the most "
        "recent voice session tied to this debate session."
    ),
)
async def get_voice_summary(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    vs_result = await db.execute(
        select(VoiceSession)
        .where(
            VoiceSession.debate_session_id == session_id,
            VoiceSession.user_id == user_id,
        )
        .order_by(VoiceSession.created_at.desc())
        .limit(1)
    )
    vs = vs_result.scalar_one_or_none()
    if not vs:
        return SuccessResponse(data=VoiceSessionSummaryOut(has_voice_session=False))

    notes_result = await db.execute(
        select(VoiceSessionNote)
        .where(VoiceSessionNote.voice_session_id == vs.id)
        .order_by(VoiceSessionNote.created_at.asc())
    )
    notes = notes_result.scalars().all()

    transcript: list[TranscriptLineOut] = []
    fallacies: list[str] = []
    strong_arguments: list[str] = []
    concessions: list[str] = []
    position_flips: list[str] = []

    for n in notes:
        if n.note_type == "transcript_user":
            transcript.append(TranscriptLineOut(speaker="user", text=n.content))
        elif n.note_type == "transcript_ai":
            transcript.append(TranscriptLineOut(speaker="ai", text=n.content))
        elif n.note_type == "fallacy":
            fallacies.append(n.content)
        elif n.note_type == "strong_argument":
            strong_arguments.append(n.content)
        elif n.note_type == "concession":
            concessions.append(n.content)
        elif n.note_type == "position_flip":
            position_flips.append(n.content)

    return SuccessResponse(
        data=VoiceSessionSummaryOut(
            has_voice_session=True,
            voice_session_id=vs.id,
            status=vs.status,
            duration_seconds=vs.duration_seconds,
            closing_summary=vs.closing_summary,
            transcript=transcript,
            fallacies=fallacies,
            strong_arguments=strong_arguments,
            concessions=concessions,
            position_flips=position_flips,
            score_logic=vs.score_logic,
            score_evidence=vs.score_evidence,
            score_rhetoric=vs.score_rhetoric,
        )
    )
