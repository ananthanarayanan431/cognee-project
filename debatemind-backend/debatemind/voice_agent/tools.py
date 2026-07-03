"""
Debate voice-agent tools.

Two layers:
  1. TOOL_DEFINITIONS  — JSON schema fed to OpenAI Realtime session config so
                          the AI knows which tools exist and when to call them.
  2. execute_tool()    — dispatches an AI tool-call to the appropriate handler,
                          runs the DB query, and returns a JSON-serialisable dict.

Flow (WebRTC):
  OpenAI (data-channel) → browser → POST /api/voice/{id}/tools → execute_tool()
                                  ← JSON result                ←
  browser sends conversation.item.create with result → OpenAI continues speaking
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.cognee import (
    filter_profile_patterns,
    recall_cognitive_profile,
    recall_topic_weaknesses,
    recall_weaknesses,
)
from debatemind.models.mastery import MasteryLog
from debatemind.models.session import DebateSession, Exchange
from debatemind.models.voice_session import VoiceSession, VoiceSessionNote
from debatemind.services.mastery_svc import get_active_mastered_patterns
from debatemind.worker.tasks import (
    finalize_voice_session_fingerprint_task,
    forget_pattern_task,
    improve_fingerprint_task,
    remember_argument_task,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Tool definitions (sent to OpenAI in session.update)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "name": "get_session_context",
        "description": (
            "Fetch the full context for the current debate: topic, description, difficulty, "
            "the user's declared position, overall score so far, and the argument patterns "
            "the user has already mastered (so you know what NOT to rely on as an easy win). "
            "Call this once at the very start of every voice session before saying anything."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "get_exchange_history",
        "description": (
            "Retrieve the user's past text-debate exchanges for this session, paginated newest "
            "first. Use this when you need to reference a specific argument that was made earlier "
            "in the debate or to avoid repeating counters you already gave."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "integer",
                    "description": "Page number (1-indexed, default 1).",
                },
                "per_page": {
                    "type": "integer",
                    "description": "Exchanges per page (default 10, max 50).",
                },
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_recent_exchanges",
        "description": (
            "Fetch the most recent N exchanges for quick context. Prefer this over "
            "get_exchange_history when you just need to recall what was last argued."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "How many recent exchanges to return (default 5, max 10).",
                },
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_voice_session_info",
        "description": (
            "Return metadata about the current voice session: session ID, start time, "
            "elapsed seconds, status, and how many observations have been saved so far."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "get_knowledge_context",
        "description": (
            "Query this user's long-term knowledge graph (Cognee) for weakness patterns "
            "beyond what was preloaded at session start. Returns both specific past "
            "weaknesses ('patterns') and a 'cognitive_profile' — their typed trait over "
            "all debates: recurring fallacies, cognitive biases, reasoning style, and "
            "the topics they're weakest on. Call this when: the debate "
            "shifts to a sub-topic or angle not covered by your initial context; the "
            "user directly asks about their history or trends ('what have I struggled "
            "with before', 'how am I doing on this topic over time'); or the user's "
            "position or framing pivots mid-session and you want fresh topic-specific "
            "context. Use the cognitive_profile to anticipate HOW they argue — pre-empt "
            "the reasoning move, bait the recurring fallacy. For sharpening your strategy "
            "only — never read any of it aloud verbatim."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": (
                        "The specific sub-topic, angle, or motion phrasing to search "
                        "for. Defaults to the session's original motion if omitted."
                    ),
                },
                "include_generic": {
                    "type": "boolean",
                    "description": (
                        "Whether to also include cross-topic weakness patterns from "
                        "the user's other debates (default true). Set false for a "
                        "topic-only query."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "save_debate_observation",
        "description": (
            "Persist a key moment from the voice debate to the database for coaching review. "
            "Call this immediately whenever you: (a) catch a logical fallacy, (b) hear a "
            "genuinely strong argument from the user, (c) witness a concession from either "
            "side, or (d) detect the user contradicting their declared position. "
            "Do NOT wait until the end — record observations in real time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "note_type": {
                    "type": "string",
                    "enum": [
                        "observation",
                        "fallacy",
                        "strong_argument",
                        "concession",
                        "position_flip",
                    ],
                    "description": "Category of the observation.",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Specific, concrete description. For fallacies include the name "
                        "and the exact reasoning that triggered it. For strong arguments "
                        "summarise what made it effective."
                    ),
                },
            },
            "required": ["note_type", "content"],
        },
    },
    {
        "type": "function",
        "name": "save_session_metadata",
        "description": (
            "Record timing metadata for the voice session. "
            "Call with action='start' immediately after get_session_context succeeds. "
            "Call with action='end' just before end_voice_session."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "end"],
                    "description": (
                        "'start' stamps the session start; 'end' stamps the session end."
                    ),
                },
            },
            "required": ["action"],
        },
    },
    {
        "type": "function",
        "name": "end_voice_session",
        "description": (
            "Mark the voice session as complete and persist a coaching summary. "
            "Call this when the user says they are done ('stop', 'end', 'I'm done', "
            "'let's finish', 'that's enough'), or when the debate has reached a natural "
            "conclusion. After the tool returns, deliver your closing remarks aloud."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "closing_summary": {
                    "type": "string",
                    "description": (
                        "1–2 sentences for the coaching log: what the user did well, "
                        "what they should practise, and the overall tenor of the debate."
                    ),
                },
            },
            "required": ["closing_summary"],
        },
    },
]


# ---------------------------------------------------------------------------
# 2. Tool handlers
# ---------------------------------------------------------------------------

# Maps voice note_type → (pattern_type, evidence_quality, outcome) for Cognee writes.
# "observation" is intentionally excluded — too generic for the fingerprint.
_COGNEE_NOTE_MAP: dict[str, tuple[str, str, str]] = {
    "fallacy": ("FallacyUsed", "Weak", "Lost"),
    "concession": ("Concession", "Weak", "Lost"),
    "position_flip": ("PositionFlip", "Weak", "Lost"),
    "strong_argument": ("StrongArgument", "Strong", "Won"),
}

# Mirrors the MASTERY_THRESHOLD in agents/mastery.py — 3 strong arguments in a
# single voice session signals the user has mastered that pattern in live debate.
_VOICE_MASTERY_THRESHOLD = 3

# In-memory strong-argument counter per voice session, keyed by voice_session_id.
# Same lifecycle risk as _session_wins in sessions.py (resets on restart),
# which is acceptable since sessions are short-lived.
_voice_strong_arg_counts: dict[str, int] = {}


def _dispatch(task_fn, *args, op_name: str, **kwargs) -> None:
    try:
        task_fn.delay(*args, **kwargs)
    except Exception:
        logger.exception("%s dispatch failed (voice)", op_name)


async def execute_tool(
    db: AsyncSession,
    tool_name: str,
    arguments: dict[str, Any],
    voice_session_id: str,
    debate_session_id: str,
    user_id: str,
) -> dict[str, Any]:
    """Dispatch an AI tool-call to the correct handler and return a result dict."""
    handlers = {
        "get_session_context": _get_session_context,
        "get_exchange_history": _get_exchange_history,
        "get_recent_exchanges": _get_recent_exchanges,
        "get_voice_session_info": _get_voice_session_info,
        "get_knowledge_context": _get_knowledge_context,
        "save_debate_observation": _save_debate_observation,
        "save_session_metadata": _save_session_metadata,
        "end_voice_session": _end_voice_session,
    }
    handler = handlers.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return await handler(db, arguments, voice_session_id, debate_session_id, user_id)
    except Exception:
        logger.exception("Tool %s failed (voice_session=%s)", tool_name, voice_session_id)
        return {"error": f"Tool '{tool_name}' failed — see server logs."}


# --- individual handlers ----------------------------------------------------


async def _get_session_context(
    db: AsyncSession, _args: dict, _vs_id: str, debate_session_id: str, user_id: str
) -> dict:
    session_row = await db.execute(
        select(DebateSession).where(DebateSession.id == debate_session_id)
    )
    session = session_row.scalar_one_or_none()
    if not session:
        return {"error": "Debate session not found."}

    exchange_count_row = await db.execute(
        select(func.count(Exchange.id)).where(Exchange.session_id == debate_session_id)
    )
    exchange_count = exchange_count_row.scalar() or 0

    mastery_rows = await db.execute(
        select(MasteryLog)
        .where(MasteryLog.user_id == user_id, MasteryLog.status == "MASTERED")
        .order_by(MasteryLog.mastered_at.desc())
        .limit(10)
    )
    mastered = [m.pattern_type for m in mastery_rows.scalars().all()]

    return {
        "topic": session.topic,
        "description": session.description or "",
        "difficulty": session.difficulty,
        "user_position": session.user_position,
        "overall_score": session.overall_score,
        "session_status": session.status,
        "total_text_exchanges": exchange_count,
        "mastered_argument_patterns": mastered,
        "coaching_note": (
            "Mastered patterns are strengths — attack the user's weaknesses instead. "
            "Target patterns NOT in the mastered list."
        ),
    }


async def _get_exchange_history(
    db: AsyncSession, args: dict, _vs_id: str, debate_session_id: str, _user_id: str
) -> dict:
    page = max(1, int(args.get("page", 1)))
    per_page = min(50, max(1, int(args.get("per_page", 10))))
    offset = (page - 1) * per_page

    total_row = await db.execute(
        select(func.count(Exchange.id)).where(Exchange.session_id == debate_session_id)
    )
    total = total_row.scalar() or 0

    rows = await db.execute(
        select(Exchange)
        .where(Exchange.session_id == debate_session_id)
        .order_by(Exchange.turn_number.desc())
        .offset(offset)
        .limit(per_page)
    )
    exchanges = rows.scalars().all()

    return {
        "exchanges": [
            {
                "turn": ex.turn_number,
                "user_message": ex.user_message,
                "opponent_response": ex.opponent_response or "",
                "outcome": ex.outcome,
                "fallacy": ex.fallacy,
                "judge_logic": ex.judge_logic,
                "judge_evidence": ex.judge_evidence,
                "judge_rhetoric": ex.judge_rhetoric,
            }
            for ex in exchanges
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 1,
    }


async def _get_recent_exchanges(
    db: AsyncSession, args: dict, _vs_id: str, debate_session_id: str, _user_id: str
) -> dict:
    limit = min(10, max(1, int(args.get("limit", 5))))

    rows = await db.execute(
        select(Exchange)
        .where(Exchange.session_id == debate_session_id)
        .order_by(Exchange.turn_number.desc())
        .limit(limit)
    )
    exchanges = list(reversed(rows.scalars().all()))  # chronological order

    return {
        "exchanges": [
            {
                "turn": ex.turn_number,
                "user_message": ex.user_message,
                "opponent_response": ex.opponent_response or "",
                "outcome": ex.outcome,
                "fallacy": ex.fallacy,
            }
            for ex in exchanges
        ],
        "count": len(exchanges),
    }


async def _get_voice_session_info(
    db: AsyncSession, _args: dict, voice_session_id: str, debate_session_id: str, _user_id: str
) -> dict:
    vs_row = await db.execute(select(VoiceSession).where(VoiceSession.id == voice_session_id))
    vs = vs_row.scalar_one_or_none()
    if not vs:
        return {"error": "Voice session not found."}

    note_count_row = await db.execute(
        select(func.count(VoiceSessionNote.id)).where(
            VoiceSessionNote.voice_session_id == voice_session_id
        )
    )
    note_count = note_count_row.scalar() or 0

    now = datetime.now(timezone.utc)
    started = vs.started_at
    if started and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    elapsed = int((now - started).total_seconds()) if started else 0

    return {
        "voice_session_id": vs.id,
        "debate_session_id": vs.debate_session_id,
        "status": vs.status,
        "started_at": started.isoformat() if started else None,
        "elapsed_seconds": elapsed,
        "observations_saved": note_count,
    }


async def _get_knowledge_context(
    db: AsyncSession, args: dict, _vs_id: str, debate_session_id: str, user_id: str
) -> dict:
    session_row = await db.execute(
        select(DebateSession).where(DebateSession.id == debate_session_id)
    )
    session = session_row.scalar_one_or_none()
    topic = args.get("topic") or (session.topic if session else "")
    include_generic = args.get("include_generic", True)

    excluded = await get_active_mastered_patterns(db, user_id)

    tasks = [recall_topic_weaknesses(user_id, topic, exclude_patterns=excluded)] if topic else []
    if include_generic:
        tasks.append(recall_weaknesses(user_id, exclude_patterns=excluded))
    # Graph-aware cognitive profile (cross-topic trait): same typed signal the
    # chat opponent now gets — recurring fallacies, biases, reasoning style,
    # weak domains — so voice and chat sharpen strategy off the same graph.
    tasks.append(recall_cognitive_profile(user_id))
    profile_idx = len(tasks) - 1

    results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

    profile_result = results[profile_idx] if results else None
    profile: dict = {}
    if isinstance(profile_result, dict):
        profile = filter_profile_patterns(profile_result, excluded)

    seen: set[str] = set()
    patterns: list[str] = []
    for items in results[:profile_idx]:
        if isinstance(items, Exception):
            continue
        for item in items:
            text = item.get("text", "")
            if text and text not in seen:
                seen.add(text)
                patterns.append(text)

    patterns = patterns[:10]
    return {
        "topic_queried": topic,
        "patterns": patterns,
        "count": len(patterns),
        "cognitive_profile": profile,
        "note": "Internal strategy context only — never read this aloud.",
    }


async def _save_debate_observation(
    db: AsyncSession, args: dict, voice_session_id: str, debate_session_id: str, user_id: str
) -> dict:
    note_type = args.get("note_type", "observation")
    content = args.get("content", "")
    if not content:
        return {"error": "content is required."}

    note = VoiceSessionNote(
        voice_session_id=voice_session_id,
        note_type=note_type,
        content=content,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    # Write semantically meaningful observations into the Cognee fingerprint so
    # future sessions (chat or voice) can recall patterns identified during voice.
    if note_type in _COGNEE_NOTE_MAP:
        pattern_type, evidence_quality, outcome = _COGNEE_NOTE_MAP[note_type]
        session_row = await db.execute(
            select(DebateSession).where(DebateSession.id == debate_session_id)
        )
        session = session_row.scalar_one_or_none()
        topic = session.topic if session else "unknown"

        _dispatch(
            remember_argument_task,
            user_id=user_id,
            session_id=debate_session_id,
            topic=topic,
            claim_text=content,
            pattern_type=pattern_type,
            fallacy=content if note_type == "fallacy" else None,
            evidence_quality=evidence_quality,
            outcome=outcome,
            op_name="remember_argument",
        )

        # Mirror chat mastery: when the user lands enough strong arguments in a
        # single voice session, mark that pattern as mastered in both Cognee and
        # MasteryLog SQL — same as pipeline's _mastery_prune_node + record_mastery_events.
        if note_type == "strong_argument":
            count = _voice_strong_arg_counts.get(voice_session_id, 0) + 1
            _voice_strong_arg_counts[voice_session_id] = count
            if count >= _VOICE_MASTERY_THRESHOLD:
                _voice_strong_arg_counts[voice_session_id] = 0
                # 1. Cognee: mark pattern as mastered in the knowledge graph
                _dispatch(forget_pattern_task, user_id, pattern_type, op_name="forget_pattern")
                # 2. SQL: write MasteryLog row so brain graph, reactivate API,
                #    and get_session_context tool all see the mastery
                db.add(
                    MasteryLog(
                        user_id=user_id,
                        pattern_type=pattern_type,
                        rounds_to_mastery=_VOICE_MASTERY_THRESHOLD,
                    )
                )
                await db.commit()
                logger.info(
                    "voice mastery threshold reached: user=%s pattern=%s",
                    user_id,
                    pattern_type,
                )

    return {"saved": True, "note_id": note.id, "note_type": note_type}


async def _save_session_metadata(
    db: AsyncSession, args: dict, voice_session_id: str, _ds_id: str, _user_id: str
) -> dict:
    action = args.get("action")
    now = datetime.now(timezone.utc)

    vs_row = await db.execute(select(VoiceSession).where(VoiceSession.id == voice_session_id))
    vs = vs_row.scalar_one_or_none()
    if not vs:
        return {"error": "Voice session not found."}

    if action == "start":
        vs.started_at = now
    elif action == "end":
        vs.ended_at = now
        started = vs.started_at
        if started:
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            vs.duration_seconds = (now - started).total_seconds()
    else:
        return {"error": "action must be 'start' or 'end'."}

    await db.commit()
    return {"saved": True, "action": action, "timestamp": now.isoformat()}


async def _end_voice_session(
    db: AsyncSession, args: dict, voice_session_id: str, debate_session_id: str, user_id: str
) -> dict:
    closing_summary = args.get("closing_summary", "")

    vs_row = await db.execute(select(VoiceSession).where(VoiceSession.id == voice_session_id))
    vs = vs_row.scalar_one_or_none()
    if not vs:
        return {"error": "Voice session not found."}

    now = datetime.now(timezone.utc)
    vs.status = "ended"
    vs.ended_at = now
    vs.closing_summary = closing_summary

    started = vs.started_at
    if started:
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        vs.duration_seconds = (now - started).total_seconds()

    note_count_row = await db.execute(
        select(func.count(VoiceSessionNote.id)).where(
            VoiceSessionNote.voice_session_id == voice_session_id
        )
    )
    note_count = note_count_row.scalar() or 0

    # Load observations to compute voice session summary stats for Cognee.
    notes_row = await db.execute(
        select(VoiceSessionNote).where(VoiceSessionNote.voice_session_id == voice_session_id)
    )
    notes = notes_row.scalars().all()

    # Load debate session for topic + difficulty.
    session_row = await db.execute(
        select(DebateSession).where(DebateSession.id == debate_session_id)
    )
    debate_session = session_row.scalar_one_or_none()

    await db.commit()

    # Clean up the in-memory mastery counter for this session.
    _voice_strong_arg_counts.pop(voice_session_id, None)

    # Write voice session summary + coaching note to Cognee so future sessions
    # on the same topic can recall voice-mode performance and coaching insights.
    if debate_session:
        strong = sum(1 for n in notes if n.note_type == "strong_argument")
        fallacies = sum(1 for n in notes if n.note_type == "fallacy")
        total_scored = strong + fallacies
        voice_win_rate = (strong / total_scored) if total_scored else 0.5
        weak_patterns = [n.content[:80] for n in notes if n.note_type in ("fallacy", "concession")][
            :3
        ]

        # Ordered: write the summary before re-indexing, in one dispatched
        # task, so the summary is captured by the same consolidating cognify
        # pass (previously these were two independent, unordered tasks).
        _dispatch(
            finalize_voice_session_fingerprint_task,
            user_id=user_id,
            session_id=debate_session_id,
            topic=debate_session.topic,
            difficulty=debate_session.difficulty,
            rounds_played=note_count,
            win_rate=voice_win_rate,
            weak_patterns=weak_patterns,
            coaching_note=closing_summary,
            op_name="finalize_voice_session_fingerprint",
        )
    else:
        # No debate session to summarize, but still re-index any observations
        # already written during the session.
        _dispatch(improve_fingerprint_task, user_id, op_name="improve_fingerprint")

    return {
        "ended": True,
        "voice_session_id": vs.id,
        "duration_seconds": vs.duration_seconds,
        "observations_saved": note_count,
        "closing_summary": closing_summary,
    }
