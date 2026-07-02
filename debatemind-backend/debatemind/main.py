import logging
import logging.config
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from debatemind.config import settings
from debatemind.middleware import (
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from debatemind.routers import auth, calibration, health, sessions, topics, users
from debatemind.services.cognee_config import configure_cognee
from debatemind.voice_agent import router as voice_router


class _CogneeNoDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "No data found in the system" not in record.getMessage()


def setup_logging() -> None:
    # Most modules (cognee/fingerprint.py, routers, agents, voice_agent, worker) log
    # via plain `logging.getLogger(__name__).info(msg, extra={...})`, not
    # `structlog.get_logger()`. A bare `basicConfig(format="%(message)s")` handler
    # renders only the message and silently drops every `extra` field — including
    # the results_raw/results_owned/elapsed_ms fields cognee's search/add/cognify
    # logging relies on to show whether memory recall actually found anything.
    # Route stdlib records through the same structlog processor chain so `extra`
    # fields make it into the rendered output for both logger types.
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    formatter = structlog.stdlib.ProcessorFormatter(
        # ExtraAdder pulls `extra={...}` kwargs off the stdlib LogRecord into the
        # event dict — without it, ProcessorFormatter only keeps `record.getMessage()`
        # and every extra field (results_raw, elapsed_ms, ...) is silently dropped.
        foreign_pre_chain=[*shared_processors, structlog.stdlib.ExtraAdder()],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)

    logging.getLogger("cognee.shared.logging_utils").addFilter(_CogneeNoDataFilter())
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
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
app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
# Added after RateLimitMiddleware so it wraps it (Starlette's last-added
# middleware is outermost) — a 429 short-circuit still gets security headers.
app.add_middleware(SecurityHeadersMiddleware, enable_hsts=settings.enable_hsts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Model", "X-Judge-Model"],
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(topics.router, prefix="/api/topics", tags=["topics"])
app.include_router(calibration.router, prefix="/api/calibration", tags=["calibration"])
app.include_router(voice_router.router, prefix="/api/voice", tags=["voice"])
