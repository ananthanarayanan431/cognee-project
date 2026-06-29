from fastapi import APIRouter, Depends
from app.deps import current_user_id
from app.services.cognee_svc import recall_weaknesses
from app.services.graph_svc import build_graph

router = APIRouter()


@router.get("/{user_id}/fingerprint")
async def get_fingerprint(user_id: str, current: str = Depends(current_user_id)):
    graph = await build_graph(current, "All topics")
    return graph


@router.get("/{user_id}/progress")
async def get_progress(user_id: str, current: str = Depends(current_user_id)):
    weaknesses = await recall_weaknesses(current)
    return {"weaknesses": weaknesses[:5], "sessions": 0, "win_rate": 0.0}
