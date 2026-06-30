from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.database import get_db
from debatemind.deps import current_user_id
from debatemind.schemas.progress import ProgressOut
from debatemind.services.cognee_svc import recall_weaknesses
from debatemind.services.graph_svc import build_graph
from debatemind.services.progress_svc import get_progress_stats

router = APIRouter()


@router.get("/me/fingerprint")
async def get_fingerprint(user_id: str = Depends(current_user_id)):
    return await build_graph(user_id, "All topics")


@router.get("/me/progress", response_model=ProgressOut)
async def get_progress(
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    weaknesses = await recall_weaknesses(user_id)
    stats = await get_progress_stats(db, user_id)
    return {"weaknesses": weaknesses[:5], **stats}
