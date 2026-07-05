"""OpenAI Realtime API ephemeral-key minter. The browser uses the key to open a
WebRTC connection directly with OpenAI; the backend is not in the audio path."""

import asyncio
import hashlib
import logging

import httpx

from debatemind.cognee import (
    cognitive_profile_text,
    filter_profile_patterns,
    recall_cognitive_profile,
    recall_topic_weaknesses,
    recall_user_facts,
    recall_weaknesses,
)
from debatemind.config import settings
from debatemind.database import AsyncSessionLocal
from debatemind.models.session import DebateSession
from debatemind.models.voice_session import VoiceSession
from debatemind.services.mastery_svc import get_active_mastered_patterns
from debatemind.voice_agent.prompts import build_voice_system_prompt
from debatemind.voice_agent.tools import TOOL_DEFINITIONS

logger = logging.getLogger(__name__)

_SESSIONS_URL = "https://api.openai.com/v1/realtime/client_secrets"
_MODEL = "gpt-realtime"
_VOICE = "shimmer"
_AUDIO_FORMAT = {"type": "audio/pcm", "rate": 24000}


async def create_voice_session(session: DebateSession, user_id: str) -> dict:
    """Mint an ephemeral key from OpenAI, create a VoiceSession row, and return
    both merged (client_secret.value for WebRTC, voice_session_id for tool calls)."""
    cognee_weaknesses: list[str] = []
    personal_facts: list[str] = []
    profile_line = ""
    try:
        async with AsyncSessionLocal() as db:
            excluded = await get_active_mastered_patterns(db, user_id)
        generic_items, topic_items, fact_items, profile = await asyncio.gather(
            recall_weaknesses(user_id, exclude_patterns=excluded),
            recall_topic_weaknesses(user_id, session.topic, exclude_patterns=excluded),
            recall_user_facts(user_id, session.topic),
            recall_cognitive_profile(user_id),
            return_exceptions=True,
        )
        seen: set[str] = set()
        for items in (topic_items, generic_items):  # topic-specific first
            if isinstance(items, Exception):
                continue
            for w in items:
                text = w.get("text", "")
                if text and text not in seen:
                    seen.add(text)
                    cognee_weaknesses.append(text)
        if not isinstance(fact_items, Exception):
            personal_facts = [f["text"] for f in fact_items if f.get("text")]
        if not isinstance(profile, Exception):
            profile_line = cognitive_profile_text(filter_profile_patterns(profile, excluded))
    except Exception:
        logger.warning("Cognee recall failed for user %s — starting without memory", user_id)

    system_prompt = build_voice_system_prompt(
        topic=session.topic,
        description=session.description or "",
        difficulty=session.difficulty,
        user_position=session.user_position,
        cognee_weaknesses=cognee_weaknesses,
        personal_facts=personal_facts,
        cognitive_profile=profile_line,
    )

    payload = {
        "session": {
            "type": "realtime",
            "model": _MODEL,
            "instructions": system_prompt,
            "audio": {
                "input": {
                    "format": _AUDIO_FORMAT,
                    "transcription": {"model": "whisper-1"},
                    # 800 ms silence gives debaters more thinking time than the default.
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 800,
                        "create_response": True,
                        "interrupt_response": True,
                    },
                },
                "output": {"voice": _VOICE, "format": _AUDIO_FORMAT},
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
    ga_session = openai_data.get("session") or {}
    openai_session_id = ga_session.get("id") or openai_data.get("id")
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

    ephemeral_value = openai_data.get("value")
    expires_at = openai_data.get("expires_at") or ga_session.get("expires_at")
    return {
        **openai_data,
        "client_secret": {"value": ephemeral_value, "expires_at": expires_at},
        "id": openai_session_id,
        "model": ga_session.get("model") or _MODEL,
        "voice_session_id": voice_session_id,
    }
