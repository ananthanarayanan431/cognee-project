import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.agents.constants import CALIBRATION_TOPICS
from debatemind.agents.extractor import extract_argument
from debatemind.cognee import remember_argument
from debatemind.database import get_db
from debatemind.deps import current_user_id
from debatemind.models.user import User
from debatemind.schemas.calibration import (
    CalibrationAnswerIn,
    CalibrationAnswerOut,
    CalibrationStatusOut,
)
from debatemind.services import calibration_svc
from debatemind.types import SuccessResponse, UnauthorizedError

router = APIRouter()

TOTAL = len(CALIBRATION_TOPICS)

logger = logging.getLogger(__name__)

# Keeps a strong reference to fire-and-forget tasks so the event loop's
# weak-referenced task set doesn't GC them mid-flight.
_background_tasks: set[asyncio.Task] = set()


def _log_remember_exc(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
    if not task.cancelled() and task.exception():
        logger.error(
            "remember_argument (calibration) background task failed", exc_info=task.exception()
        )


async def _get_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get(
    "/status",
    response_model=SuccessResponse[CalibrationStatusOut],
    summary="Get calibration status",
    description="Check whether the first-time calibration flow is needed and which topic is next.",
    responses={401: {"model": UnauthorizedError, "description": "Invalid or missing token"}},
)
async def status(
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user(db, user_id)
    if user.calibration_done:
        return SuccessResponse(data=CalibrationStatusOut(needed=False, total=TOTAL))
    idx = calibration_svc.get_index(user_id)
    return SuccessResponse(
        data=CalibrationStatusOut(
            needed=True, topic=CALIBRATION_TOPICS[idx], index=idx + 1, total=TOTAL
        )
    )


@router.post(
    "/answer",
    response_model=SuccessResponse[CalibrationAnswerOut],
    summary="Submit a calibration answer",
    description="Submit the user's response to the current calibration topic. "
    "Extracts and stores the argument pattern, then advances to the next topic "
    "or marks calibration complete.",
    responses={
        400: {"description": "Calibration already complete"},
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
    },
)
async def answer(
    body: CalibrationAnswerIn,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user(db, user_id)
    if user.calibration_done:
        raise HTTPException(status_code=400, detail="Calibration already complete")

    idx = calibration_svc.get_index(user_id)
    topic = CALIBRATION_TOPICS[idx]

    state = await extract_argument({"topic": topic, "user_message": body.text, "description": ""})

    # Fire-and-forget: remember_argument runs add()+cognify() which can take many
    # seconds. Awaiting it inline would block the calibration response (and risk a
    # request timeout); background it so the user advances immediately.
    remember_task = asyncio.create_task(
        remember_argument(
            user_id=user_id,
            session_id=f"calibration_{user_id}",
            topic=topic,
            claim_text=body.text,
            pattern_type=state.get("extracted_pattern", "EvidenceBased"),
            fallacy=state.get("extracted_fallacy"),
            evidence_quality=state.get("evidence_quality", "Moderate"),
            outcome="Neutral",
            reasoning=state.get("extracted_reasoning", "") or "",
        )
    )
    _background_tasks.add(remember_task)
    remember_task.add_done_callback(_log_remember_exc)

    new_idx = calibration_svc.advance(user_id)
    if new_idx >= TOTAL:
        await db.execute(update(User).where(User.id == user_id).values(calibration_done=True))
        await db.commit()
        calibration_svc.reset(user_id)
        return SuccessResponse(data=CalibrationAnswerOut(done=True, index=TOTAL, total=TOTAL))

    return SuccessResponse(
        data=CalibrationAnswerOut(
            done=False, next_topic=CALIBRATION_TOPICS[new_idx], index=new_idx + 1, total=TOTAL
        )
    )
