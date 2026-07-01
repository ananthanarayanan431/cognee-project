from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.database import get_db
from debatemind.deps import current_user_id
from debatemind.schemas.graph import GraphOut
from debatemind.schemas.progress import ProgressOut
from debatemind.services.cognee_svc import recall_weaknesses
from debatemind.services.graph_svc import build_graph
from debatemind.services.mastery_svc import reactivate_pattern
from debatemind.services.progress_svc import (
    get_mastered_patterns,
    get_progress_stats,
    get_streak,
    get_weakness_trend,
    get_win_rate_by_topic,
)
from debatemind.types import NotFoundError, SuccessResponse, UnauthorizedError

router = APIRouter()


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
    weaknesses = await recall_weaknesses(user_id)
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
