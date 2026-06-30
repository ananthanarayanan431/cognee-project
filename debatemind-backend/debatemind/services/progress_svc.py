from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.models.session import DebateSession, Exchange


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
