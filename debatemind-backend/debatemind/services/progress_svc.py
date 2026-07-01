from datetime import date, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.models.mastery import MasteryLog
from debatemind.models.session import DebateSession, Exchange
from debatemind.services.weight_calc import compute_weight


async def get_progress_stats(db: AsyncSession, user_id: str) -> dict:
    stmt = (
        select(
            func.count(func.distinct(DebateSession.id)).label("sessions"),
            func.avg(Exchange.judge_logic).label("avg_logic"),
            func.avg(Exchange.judge_evidence).label("avg_evidence"),
            func.avg(Exchange.judge_rhetoric).label("avg_rhetoric"),
            func.count(case((Exchange.outcome == "Won", 1))).label("won"),
            func.count(case((Exchange.outcome.in_(["Won", "Lost"]), 1))).label("decided"),
        )
        .select_from(DebateSession)
        .outerjoin(Exchange, Exchange.session_id == DebateSession.id)
        .where(DebateSession.user_id == user_id)
    )
    row = (await db.execute(stmt)).one()
    win_rate = (row.won / row.decided) if row.decided else 0.0

    return {
        "sessions": row.sessions or 0,
        "win_rate": round(win_rate, 3),
        "thinking_style": {
            "logic": round(row.avg_logic, 2) if row.avg_logic is not None else 0.0,
            "evidence": round(row.avg_evidence, 2) if row.avg_evidence is not None else 0.0,
            "rhetoric": round(row.avg_rhetoric, 2) if row.avg_rhetoric is not None else 0.0,
        },
    }


async def get_streak(db: AsyncSession, user_id: str) -> int:
    rows = (
        (
            await db.execute(
                select(func.date(DebateSession.started_at))
                .where(DebateSession.user_id == user_id)
                .distinct()
            )
        )
        .scalars()
        .all()
    )

    days: set[date] = set()
    for r in rows:
        days.add(r if isinstance(r, date) else date.fromisoformat(r))

    if not days:
        return 0

    today = date.today()
    cursor = today if today in days else today - timedelta(days=1)
    if cursor not in days:
        return 0

    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def get_win_rate_by_topic(db: AsyncSession, user_id: str) -> list[dict]:
    stmt = (
        select(
            DebateSession.topic,
            func.count(case((Exchange.outcome == "Won", 1))).label("won"),
            func.count(case((Exchange.outcome.in_(["Won", "Lost"]), 1))).label("decided"),
        )
        .select_from(DebateSession)
        .outerjoin(Exchange, Exchange.session_id == DebateSession.id)
        .where(DebateSession.user_id == user_id)
        .group_by(DebateSession.topic)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"topic": r.topic, "win_rate": round(r.won / r.decided, 3) if r.decided else 0.0}
        for r in rows
    ]


async def get_mastered_patterns(db: AsyncSession, user_id: str) -> list[dict]:
    rows = (
        (
            await db.execute(
                select(MasteryLog)
                .where(MasteryLog.user_id == user_id)
                .order_by(MasteryLog.mastered_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "pattern": r.pattern_type,
            "mastered_at": r.mastered_at,
            "rounds_to_mastery": r.rounds_to_mastery,
            "reactivated": r.reactivated_at is not None,
        }
        for r in rows
    ]


async def get_weakness_trend(db: AsyncSession, user_id: str, limit: int = 6) -> list[dict]:
    mastered_active = (
        (
            await db.execute(
                select(MasteryLog.pattern_type).where(
                    MasteryLog.user_id == user_id, MasteryLog.reactivated_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    excluded = set(mastered_active)

    rows = (
        await db.execute(
            select(
                Exchange.detected_pattern,
                Exchange.judge_logic,
                Exchange.judge_evidence,
                Exchange.judge_rhetoric,
            )
            .join(DebateSession, DebateSession.id == Exchange.session_id)
            .where(
                DebateSession.user_id == user_id,
                Exchange.detected_pattern.is_not(None),
            )
        )
    ).all()

    by_pattern: dict[str, list[float]] = {}
    for pattern, logic, evidence, rhetoric in rows:
        if pattern in excluded:
            continue
        by_pattern.setdefault(pattern, []).append(compute_weight(logic, evidence, rhetoric))

    trend = [{"pattern": p, "weight": round(sum(ws) / len(ws), 2)} for p, ws in by_pattern.items()]
    trend.sort(key=lambda t: t["weight"], reverse=True)
    return trend[:limit]
