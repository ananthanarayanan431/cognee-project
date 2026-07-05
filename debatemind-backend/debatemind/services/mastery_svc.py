from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.agents.mastery import MASTERY_THRESHOLD
from debatemind.models.mastery import MasteryLog


async def get_active_mastered_patterns(db: AsyncSession, user_id: str) -> set[str]:
    """Patterns the user has currently mastered (and not since reactivated).

    Used to exclude these from opponent recall so the AI stops targeting a
    weakness once it's been beaten — the behavioural half of forget().
    """
    rows = await db.execute(
        select(MasteryLog.pattern_type).where(
            MasteryLog.user_id == user_id,
            MasteryLog.status == "MASTERED",
            MasteryLog.reactivated_at.is_(None),
        )
    )
    return set(rows.scalars().all())


async def record_mastery_events(db: AsyncSession, user_id: str, patterns: list[str]) -> None:
    if not patterns:
        return
    for pattern in patterns:
        db.add(
            MasteryLog(user_id=user_id, pattern_type=pattern, rounds_to_mastery=MASTERY_THRESHOLD)
        )


async def reactivate_pattern(db: AsyncSession, user_id: str, pattern_type: str) -> bool:
    result = await db.execute(
        select(MasteryLog)
        .where(
            MasteryLog.user_id == user_id,
            MasteryLog.pattern_type == pattern_type,
            MasteryLog.reactivated_at.is_(None),
        )
        .order_by(MasteryLog.mastered_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False

    # Only clears the Postgres gate — the deleted Cognee evidence is not restored.
    row.reactivated_at = datetime.now(timezone.utc)
    await db.commit()
    return True
