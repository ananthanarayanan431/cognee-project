import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.database import get_db
from debatemind.schemas.health import HealthOut, ReadinessOut
from debatemind.types import ServiceUnavailableError, SuccessResponse

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get(
    "/health",
    response_model=SuccessResponse[HealthOut],
    summary="Liveness check",
    description=(
        "Check whether the API process is up and able to serve requests. "
        "Does not check downstream dependencies."
    ),
)
async def health():
    return SuccessResponse(data=HealthOut(status="ok"))


@router.get(
    "/health/ready",
    response_model=SuccessResponse[ReadinessOut],
    summary="Readiness check",
    description=(
        "Check whether the service is ready to receive traffic, including database connectivity."
    ),
    responses={
        503: {"model": ServiceUnavailableError, "description": "Database is unreachable"},
    },
)
async def ready(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("database_not_ready", exc_info=exc)
        raise HTTPException(status_code=503, detail="Database not ready") from exc
    return SuccessResponse(data=ReadinessOut(status="ready", database="ok"))
