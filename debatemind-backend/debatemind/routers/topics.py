from fastapi import APIRouter

from debatemind.schemas.topics import TopicSuggestion
from debatemind.types import SuccessResponse

router = APIRouter()

TOPICS = [
    TopicSuggestion(label="POLICY", chips=["EU AI Act", "Platform regulation", "Carbon tax"]),
    TopicSuggestion(label="TECHNOLOGY", chips=["AI safety", "Open source AI", "Algorithmic bias"]),
    TopicSuggestion(label="SOCIETY", chips=["Social media bans", "UBI", "Education reform"]),
]


@router.get(
    "/suggest",
    response_model=SuccessResponse[list[TopicSuggestion]],
    summary="Get topic suggestions",
    description="Retrieve a curated list of debate topic suggestions grouped by category.",
)
async def suggest():
    return SuccessResponse(data=TOPICS)
