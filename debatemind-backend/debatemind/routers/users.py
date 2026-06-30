from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.database import get_db
from debatemind.deps import current_user_id
from debatemind.schemas.graph import GraphOut
from debatemind.schemas.progress import ProgressOut
from debatemind.services.cognee_svc import recall_weaknesses
from debatemind.services.graph_svc import build_graph
from debatemind.services.progress_svc import get_progress_stats
from debatemind.types import SuccessResponse, UnauthorizedError

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
        "Retrieve the user's overall debate statistics including win rate, session "
        "count, thinking style breakdown, and top weaknesses."
    ),
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
    },
)
async def get_progress(
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    weaknesses = await recall_weaknesses(user_id)
    stats = await get_progress_stats(db, user_id)
    return SuccessResponse(data=ProgressOut(weaknesses=weaknesses[:5], **stats))
