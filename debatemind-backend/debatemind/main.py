import logging
import logging.config
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from debatemind.config import settings
from debatemind.middleware import RequestIDMiddleware
from debatemind.routers import auth, calibration, health, sessions, topics, users
from debatemind.services.cognee_config import configure_cognee
from debatemind.voice_agent import router as voice_router


class _CogneeNoDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "No data found in the system" not in record.getMessage()


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("cognee.shared.logging_utils").addFilter(_CogneeNoDataFilter())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


setup_logging()

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    from cognee.modules.engine.operations.setup import setup as cognee_setup

    configure_cognee(settings)
    await cognee_setup()

    yield


app = FastAPI(title="DebateMind API", lifespan=lifespan)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(topics.router, prefix="/api/topics", tags=["topics"])
app.include_router(calibration.router, prefix="/api/calibration", tags=["calibration"])
app.include_router(voice_router.router, prefix="/api/voice", tags=["voice"])
