from fastapi import APIRouter

router = APIRouter()

TOPICS = [
    {"label": "POLICY", "chips": ["EU AI Act", "Platform regulation", "Carbon tax"]},
    {"label": "TECHNOLOGY", "chips": ["AI safety", "Open source AI", "Algorithmic bias"]},
    {"label": "SOCIETY", "chips": ["Social media bans", "UBI", "Education reform"]},
]


@router.get("/suggest")
async def suggest():
    return TOPICS
