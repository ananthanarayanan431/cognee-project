"""
OpenAI Realtime API ephemeral-key minter.

WebRTC + ephemeral-key pattern (recommended by OpenAI for browser clients):
  1. Backend calls POST /v1/realtime/client_secrets with the full session config
     (system prompt, voice, turn-detection, tool definitions) using the standard API key.
  2. OpenAI returns a short-lived ephemeral key (valid ~60 seconds).
  3. Backend creates a VoiceSession row in the DB, then returns the ephemeral key
     and the voice_session_id to the browser.
  4. Browser uses the ephemeral key to open a WebRTC peer connection directly
     with OpenAI — the backend is not in the audio media path at all.
  5. When OpenAI calls a tool, the browser POSTs to /api/voice/{id}/tools, our
     backend executes it, and the browser relays the result back via data-channel.
"""

import asyncio
import hashlib
import logging

import httpx

from debatemind.cognee import recall_topic_weaknesses, recall_weaknesses
from debatemind.config import settings
from debatemind.database import AsyncSessionLocal
from debatemind.models.session import DebateSession
from debatemind.models.voice_session import VoiceSession
from debatemind.voice_agent.prompts import build_voice_system_prompt
from debatemind.voice_agent.tools import TOOL_DEFINITIONS

logger = logging.getLogger(__name__)

_SESSIONS_URL = "https://api.openai.com/v1/realtime/client_secrets"
_MODEL = "gpt-4o-realtime-preview"
_VOICE = "shimmer"


async def create_voice_session(session: DebateSession, user_id: str) -> dict:
    """
    Mint a short-lived ephemeral key from OpenAI, create a VoiceSession DB row,
    and return a combined dict:

        {
          # everything OpenAI returned:
          "client_secret": {"value": "ek_...", "expires_at": <unix ts>},
          "id": "sess_...",
          "model": "gpt-4o-realtime-preview",
          ...
          # our addition:
          "voice_session_id": "<uuid>"
        }

    The browser extracts:
      - client_secret.value  → ephemeral Bearer token for WebRTC
      - voice_session_id     → passed to POST /api/voice/{sid}/tools
    """
    # Fetch weakness patterns from Cognee: both generic (cross-topic) and
    # topic-specific (session summaries + exchanges on this exact topic).
    # Merge and deduplicate so the AI gets the richest possible context.
    try:
        generic_items, topic_items = await asyncio.gather(
            recall_weaknesses(user_id),
            recall_topic_weaknesses(user_id, session.topic),
            return_exceptions=True,
        )
        seen: set[str] = set()
        cognee_weaknesses: list[str] = []
        for items in (topic_items, generic_items):  # topic context first — more specific
            if isinstance(items, Exception):
                continue
            for w in items:
                text = w.get("text", "")
                if text and text not in seen:
                    seen.add(text)
                    cognee_weaknesses.append(text)
    except Exception:
        logger.warning("Cognee recall failed for user %s — starting without memory", user_id)
        cognee_weaknesses = []

    system_prompt = build_voice_system_prompt(
        topic=session.topic,
        description=session.description or "",
        difficulty=session.difficulty,
        user_position=session.user_position,
        cognee_weaknesses=cognee_weaknesses,
    )

    payload = {
        "session": {
            "model": _MODEL,
            "modalities": ["audio", "text"],
            "instructions": system_prompt,
            "voice": _VOICE,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {"model": "whisper-1"},
            # server_vad: OpenAI handles silence detection automatically.
            # 800 ms silence gives debaters more thinking time than the 500 ms default.
            # create_response + interrupt_response are required in conversation mode.
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 800,
                "create_response": True,
                "interrupt_response": True,
            },
            "tools": TOOL_DEFINITIONS,
            "tool_choice": "auto",
        }
    }

    # Stable, privacy-preserving safety identifier bound to this ephemeral token.
    safety_id = hashlib.sha256(user_id.encode()).hexdigest()

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            _SESSIONS_URL,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
                "OpenAI-Safety-Identifier": safety_id,
            },
            json=payload,
        )

    if response.is_error:
        logger.error(
            "OpenAI client_secrets failed: status=%s body=%s",
            response.status_code,
            response.text,
        )
        response.raise_for_status()

    openai_data = response.json()

    # Create the VoiceSession row so tool handlers have something to look up.
    openai_session_id = openai_data.get("id")
    async with AsyncSessionLocal() as db:
        voice_session = VoiceSession(
            debate_session_id=session.id,
            user_id=user_id,
            openai_session_id=openai_session_id,
            status="active",
        )
        db.add(voice_session)
        await db.commit()
        await db.refresh(voice_session)
        voice_session_id = voice_session.id

    logger.info(
        "VoiceSession created: vs=%s debate=%s openai=%s",
        voice_session_id,
        session.id,
        openai_session_id,
    )

    return {**openai_data, "voice_session_id": voice_session_id}
