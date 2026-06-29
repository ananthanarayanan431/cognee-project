from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import cognee
from app.config import settings
from app.database import engine, Base
from app.models import user, session, mastery  # noqa: F401
from app.routers import auth, sessions, users, topics
from app.websocket.router import ws_router

app = FastAPI(title="DebateMind API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("app").warning("DB not reachable at startup: %s", exc)
    if settings.cognee_api_key:
        cognee.config.set_llm_config({
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "api_key": settings.cognee_llm_api_key or settings.anthropic_api_key,
        })


app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(topics.router, prefix="/api/topics", tags=["topics"])
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
