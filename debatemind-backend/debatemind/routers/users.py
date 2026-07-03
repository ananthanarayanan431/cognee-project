import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func as sqlfunc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.agents.client import openrouter
from debatemind.cognee import forget_personal_fact, recall_weaknesses
from debatemind.cognee.brain_view import user_brain_graph
from debatemind.cognee.graph_view import user_graph_view
from debatemind.config import settings
from debatemind.database import get_db
from debatemind.deps import current_user_id
from debatemind.models.session import DebateSession
from debatemind.schemas.graph import GraphOut
from debatemind.schemas.knowledge_graph import KnowledgeGraphOut
from debatemind.schemas.progress import ProgressOut
from debatemind.services.graph_svc import build_graph
from debatemind.services.mastery_svc import get_active_mastered_patterns, reactivate_pattern
from debatemind.services.progress_svc import (
    get_mastered_patterns,
    get_progress_stats,
    get_streak,
    get_weakness_trend,
    get_win_rate_by_topic,
)
from debatemind.types import NotFoundError, SuccessResponse, UnauthorizedError

logger = logging.getLogger(__name__)


class DescribeOut(BaseModel):
    description: str


router = APIRouter()


@router.get(
    "/me/topic-session-counts",
    response_model=SuccessResponse[dict[str, int]],
    summary="Get session count per debate topic",
    description="Returns a mapping of topic title → number of sessions the user has debated it.",
    responses={401: {"model": UnauthorizedError, "description": "Invalid or missing token"}},
)
async def topic_session_counts(
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(DebateSession.topic, sqlfunc.count(DebateSession.id).label("cnt"))
        .where(DebateSession.user_id == user_id)
        .group_by(DebateSession.topic)
    )
    return SuccessResponse(data={topic: cnt for topic, cnt in rows.all()})


@router.get(
    "/me/fingerprint",
    response_model=SuccessResponse[GraphOut],
    summary="Get user learning fingerprint",
    description=(
        "Retrieve the knowledge graph representing the user's argument pattern "
        "strengths and weaknesses across all debate topics."
    ),
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
    },
)
async def get_fingerprint(user_id: str = Depends(current_user_id)):
    return SuccessResponse(data=await build_graph(user_id, "All topics"))


@router.get(
    "/me/brain",
    response_model=SuccessResponse[GraphOut],
    summary="Get hierarchical brain graph",
    description=(
        "Retrieve a per-topic hierarchical knowledge graph: "
        "root → topics → argument patterns, for the brain map visualisation. "
        "Sourced from the user's Cognee/Neo4j ArgumentRecord nodes; "
        "strength/weakness reflects win-rate over each record's outcome."
    ),
    responses={401: {"model": UnauthorizedError, "description": "Invalid or missing token"}},
)
async def get_brain_graph(user_id: str = Depends(current_user_id)):
    view = await user_brain_graph(user_id)
    if view.get("error"):
        logger.warning("user_brain_graph returned an error for user %s: %s", user_id, view["error"])
    return SuccessResponse(data=GraphOut(nodes=view["nodes"], edges=view["edges"]))


@router.get(
    "/me/knowledge-graph",
    response_model=SuccessResponse[KnowledgeGraphOut],
    summary="Get raw Cognee knowledge graph",
    description=(
        "Retrieve the user's typed Cognee graph (arguments, topics, personal facts, "
        "session summaries) plus any entities cognify's LLM pass linked to them — "
        "distinct from /me/brain, which is a curated root→topic→pattern mastery view."
    ),
    responses={401: {"model": UnauthorizedError, "description": "Invalid or missing token"}},
)
async def get_knowledge_graph(user_id: str = Depends(current_user_id)):
    view = await user_graph_view(user_id)
    if view.get("error"):
        logger.warning("user_graph_view returned an error for user %s: %s", user_id, view["error"])
    return SuccessResponse(data=KnowledgeGraphOut(nodes=view["nodes"], edges=view["edges"]))


class ForgetFactOut(BaseModel):
    node_id: str
    status: str


@router.delete(
    "/me/facts/{node_id}",
    response_model=SuccessResponse[ForgetFactOut],
    summary="Forget a personal fact",
    description=(
        "Permanently delete one personal fact the user shared, from both the "
        "graph and its embedding."
    ),
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Fact not found"},
    },
)
async def delete_fact(node_id: str, user_id: str = Depends(current_user_id)):
    result = await forget_personal_fact(user_id, node_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Fact not found")
    return SuccessResponse(data=ForgetFactOut(**result))


@router.get(
    "/me/progress",
    response_model=SuccessResponse[ProgressOut],
    summary="Get user progress stats",
    description=(
        "Retrieve the user's overall debate statistics including win rate, streak, "
        "session count, thinking style, mastered patterns, win rate by topic, and "
        "weakness trend."
    ),
    responses={401: {"model": UnauthorizedError, "description": "Invalid or missing token"}},
)
async def get_progress(
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    excluded = await get_active_mastered_patterns(db, user_id)
    weaknesses = await recall_weaknesses(user_id, exclude_patterns=excluded)
    stats = await get_progress_stats(db, user_id)
    streak = await get_streak(db, user_id)
    mastered = await get_mastered_patterns(db, user_id)
    win_rate_by_topic = await get_win_rate_by_topic(db, user_id)
    weakness_trend = await get_weakness_trend(db, user_id)
    return SuccessResponse(
        data=ProgressOut(
            weaknesses=weaknesses[:5],
            streak=streak,
            mastered=mastered,
            win_rate_by_topic=win_rate_by_topic,
            weakness_trend=weakness_trend,
            **stats,
        )
    )


@router.get(
    "/me/describe",
    response_model=SuccessResponse[DescribeOut],
    summary="Get AI-generated cognitive profile",
    description=(
        "Generate a natural-language description of the user's debate style, "
        "strengths, weaknesses, and thinking patterns across all sessions."
    ),
    responses={401: {"model": UnauthorizedError, "description": "Invalid or missing token"}},
)
async def describe_user(
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    excluded = await get_active_mastered_patterns(db, user_id)
    weaknesses = await recall_weaknesses(user_id, exclude_patterns=excluded)
    stats = await get_progress_stats(db, user_id)
    mastered = await get_mastered_patterns(db, user_id)
    win_rate_by_topic = await get_win_rate_by_topic(db, user_id)

    ts = stats["thinking_style"]
    mastered_list = ", ".join(m["pattern"] for m in mastered) if mastered else "none yet"
    weakness_list = (
        ", ".join(w["text"] for w in weaknesses[:5]) if weaknesses else "none identified yet"
    )
    topic_lines = (
        "\n".join(
            f"  - {t['topic']}: {round(t['win_rate'] * 100)}% win rate"
            for t in win_rate_by_topic[:5]
        )
        if win_rate_by_topic
        else "  no topic data yet"
    )

    thinking_line = (
        f"- Thinking style scores (0–10):"
        f" Logic {ts['logic']}, Evidence {ts['evidence']},"
        f" Rhetoric {ts['rhetoric']}"
    )
    prompt = (
        "You are analyzing a DebateMind user's cognitive debate profile."
        ' Write a concise 3-paragraph profile in second person ("You...")'
        " that describes their debate style, strengths, and what they"
        " should work on.\n\nUser stats:\n"
        f"- Sessions completed: {stats['sessions']}\n"
        f"- Overall win rate: {round(stats['win_rate'] * 100)}%\n"
        f"{thinking_line}\n"
        f"- Mastered argument patterns: {mastered_list}\n"
        f"- Current weaknesses: {weakness_list}\n"
        f"- Win rate by topic:\n{topic_lines}\n\n"
        "Ground every claim in the stats above — cite the actual numbers and"
        " pattern names, and never invent figures, sessions, or trends not shown"
        " (if a stat is empty or zero, say so plainly rather than guessing)."
        " Write in a direct, insightful, and encouraging tone, and end with one"
        " concrete thing they should practise next. Keep it under 200 words total."
    )

    response = await openrouter.chat.completions.create(
        model=settings.fast_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
    )
    description = response.choices[0].message.content or ""
    return SuccessResponse(data=DescribeOut(description=description))


@router.get(
    "/me/export",
    summary="Export user profile",
    description="Download the user's full cognitive profile and session history as JSON.",
    responses={401: {"model": UnauthorizedError, "description": "Invalid or missing token"}},
)
async def export_profile(
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    excluded = await get_active_mastered_patterns(db, user_id)
    weaknesses = await recall_weaknesses(user_id, exclude_patterns=excluded)
    stats = await get_progress_stats(db, user_id)
    streak = await get_streak(db, user_id)
    mastered = await get_mastered_patterns(db, user_id)
    win_rate_by_topic = await get_win_rate_by_topic(db, user_id)
    weakness_trend = await get_weakness_trend(db, user_id)

    payload = {
        "sessions": stats["sessions"],
        "win_rate": stats["win_rate"],
        "streak": streak,
        "thinking_style": stats["thinking_style"],
        "weaknesses": [w["text"] for w in weaknesses],
        "mastered_patterns": [
            {
                "pattern": m["pattern"],
                "mastered_at": m["mastered_at"].isoformat() if m["mastered_at"] else None,
                "rounds_to_mastery": m["rounds_to_mastery"],
            }
            for m in mastered
        ],
        "win_rate_by_topic": [
            {"topic": t["topic"], "win_rate": t["win_rate"]} for t in win_rate_by_topic
        ],
        "weakness_trend": [
            {"pattern": w["pattern"], "weight": w["weight"]} for w in weakness_trend
        ],
    }

    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="debatemind_profile_{user_id[:8]}.json"'
        },
    )


@router.post(
    "/me/mastery/{pattern_type}/reactivate",
    response_model=SuccessResponse[dict],
    summary="Reactivate a mastered pattern",
    description=(
        "Un-masters a previously mastered argument pattern so the opponent resumes targeting it."
    ),
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Pattern was never mastered for this user"},
    },
)
async def reactivate_mastery(
    pattern_type: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    ok = await reactivate_pattern(db, user_id, pattern_type)
    if not ok:
        raise HTTPException(status_code=404, detail="Pattern was never mastered")
    return SuccessResponse(data={"reactivated": True})


_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_models_cache: list[dict] | None = None


def _provider_from_id(model_id: str) -> str:
    prefix = model_id.split("/")[0].lower()
    return {
        "anthropic": "Anthropic",
        "openai": "OpenAI",
        "google": "Google",
        "meta-llama": "Meta",
        "deepseek": "DeepSeek",
        "x-ai": "xAI",
        "mistralai": "Mistral",
        "cohere": "Cohere",
        "qwen": "Alibaba",
        "nvidia": "NVIDIA",
        "microsoft": "Microsoft",
        "01-ai": "01.AI",
    }.get(prefix, prefix.title())


async def _fetch_openrouter_models() -> list[dict]:
    global _models_cache
    if _models_cache is not None:
        return _models_cache

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_OPENROUTER_MODELS_URL)
        resp.raise_for_status()
        raw = resp.json().get("data", [])

    models = []
    for m in raw:
        arch = m.get("architecture", {})
        modality = arch.get("modality", "")
        # Keep only text-in / text-out models (exclude image-gen, audio, etc.)
        if "text" not in modality or "->text" not in modality:
            continue
        prompt_price = float(m.get("pricing", {}).get("prompt", 0) or 0)
        models.append(
            {
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "provider": _provider_from_id(m["id"]),
                "context_length": m.get("context_length"),
                "prompt_price_per_m": round(prompt_price * 1_000_000, 4),
            }
        )

    # Sort: by provider then name
    models.sort(key=lambda x: (x["provider"].lower(), x["name"].lower()))
    _models_cache = models
    return models


@router.get(
    "/models",
    summary="List available opponent models",
    description="Proxies OpenRouter /models, filtered to text-in/text-out models.",
)
async def list_models(_: str = Depends(current_user_id)):
    try:
        models = await _fetch_openrouter_models()
    except Exception:
        models = []
    return SuccessResponse(
        data={
            "models": models,
            "default_opponent": settings.main_model,
            "default_judge": settings.fast_model,
        }
    )
