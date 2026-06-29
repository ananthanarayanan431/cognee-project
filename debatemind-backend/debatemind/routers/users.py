from fastapi import APIRouter, Depends

from debatemind.deps import current_user_id
from debatemind.services.cognee_svc import recall_weaknesses
from debatemind.services.graph_svc import build_graph

router = APIRouter()


@router.get("/me/fingerprint")
async def get_fingerprint(user_id: str = Depends(current_user_id)):
    return await build_graph(user_id, "All topics")


@router.get("/me/progress")
async def get_progress(user_id: str = Depends(current_user_id)):
    weaknesses = await recall_weaknesses(user_id)
    return {"weaknesses": weaknesses[:5], "sessions": 0, "win_rate": 0.0}
