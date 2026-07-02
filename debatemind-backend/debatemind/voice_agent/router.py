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
POST /{session_id}/token    Mint ephemeral key + create VoiceSession row
POST /{session_id}/tools    Execute a tool call dispatched by the AI
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.config import settings
from debatemind.database import AsyncSessionLocal, get_db
from debatemind.deps import current_user_id
from debatemind.models.session import DebateSession
from debatemind.models.voice_session import VoiceSession
from debatemind.types.responses import SuccessResponse
from debatemind.voice_agent.session import create_voice_session
from debatemind.voice_agent.tools import execute_tool

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ToolCallRequest(BaseModel):
    voice_session_id: str
    tool: str
    arguments: dict = {}


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
    Response shape:

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
    body: ToolCallRequest,
    user_id: str = Depends(current_user_id),
):
    """
    Request body:
        {
          "voice_session_id": "...",
          "tool": "save_debate_observation",
          "arguments": {"note_type": "fallacy", "content": "..."}
        }

    Response: whatever the tool handler returns (a JSON-serialisable dict).
    """
    # Verify the voice session belongs to this user and debate session
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

    return SuccessResponse(data=result)
