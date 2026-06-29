import logging
from contextlib import asynccontextmanager

import cognee
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from debatemind.config import settings
from debatemind.database import Base, engine
from debatemind.models import mastery, session, user  # noqa: F401
from debatemind.routers import auth, sessions, topics, users

logger = logging.getLogger("debatemind")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB not reachable at startup: %s", exc)

    if settings.cognee_api_key and settings.cognee_llm_api_key:
        cognee.config.set_llm_config(
            {
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "api_key": settings.cognee_llm_api_key,
            }
        )

    yield


app = FastAPI(title="DebateMind API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(topics.router, prefix="/api/topics", tags=["topics"])


@app.get("/health")
async def health():
    return {"status": "ok"}
