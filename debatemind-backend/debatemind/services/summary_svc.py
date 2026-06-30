from sqlalchemy import select

from debatemind.models.mastery import MasteryLog
from debatemind.models.session import DebateSession, Exchange
from debatemind.schemas.session import SessionSummaryOut, WeaknessChange
from debatemind.services.weight_calc import compute_weight


async def get_session_summary(db, user_id: str, session_id: str) -> SessionSummaryOut | None:
    session_row = (
        await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    ).scalar_one_or_none()
    if not session_row or session_row.user_id != user_id:
        return None

    exchanges = (
        (
            await db.execute(
                select(Exchange)
                .where(Exchange.session_id == session_id)
                .order_by(Exchange.turn_number)
            )
        )
        .scalars()
        .all()
    )

    won = sum(1 for e in exchanges if e.outcome == "Won")
    weakness_patterns = {
        e.detected_pattern for e in exchanges if e.detected_pattern and e.outcome != "Won"
    }

    raw_scores = [
        s
        for e in exchanges
        for s in (e.judge_logic, e.judge_evidence, e.judge_rhetoric)
        if s is not None
    ]
    overall_score = round(sum(raw_scores) / len(raw_scores), 2) if raw_scores else 0.0

    mastery_rows = (
        (
            await db.execute(
                select(MasteryLog).where(
                    MasteryLog.user_id == user_id,
                    MasteryLog.reactivated_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    # Filter mastery logs to only those created at or after the session started
    mastered_in_session = {
        m.pattern_type: m
        for m in mastery_rows
        if m.mastered_at and m.mastered_at >= session_row.started_at
    }

    patterns_seen = {e.detected_pattern for e in exchanges if e.detected_pattern}
    pattern_changes: list[WeaknessChange] = []
    for pattern in patterns_seen:
        this_session_weights = [
            compute_weight(e.judge_logic, e.judge_evidence, e.judge_rhetoric)
            for e in exchanges
            if e.detected_pattern == pattern
        ]
        after = round(sum(this_session_weights) / len(this_session_weights), 2)

        prior_rows = (
            await db.execute(
                select(Exchange.judge_logic, Exchange.judge_evidence, Exchange.judge_rhetoric)
                .join(DebateSession, DebateSession.id == Exchange.session_id)
                .where(
                    DebateSession.user_id == user_id,
                    Exchange.detected_pattern == pattern,
                    DebateSession.started_at < session_row.started_at,
                    DebateSession.id != session_id,
                )
            )
        ).all()
        before = (
            round(sum(compute_weight(*row) for row in prior_rows) / len(prior_rows), 2)
            if prior_rows
            else after
        )

        mastered = pattern in mastered_in_session
        pattern_changes.append(
            WeaknessChange(
                pattern=pattern,
                before=before,
                after=after,
                mastered=mastered,
                rounds_to_mastery=(
                    mastered_in_session[pattern].rounds_to_mastery if mastered else None
                ),
            )
        )

    return SessionSummaryOut(
        topic=session_row.topic,
        difficulty=session_row.difficulty,
        score=overall_score,
        exchanges=len(exchanges),
        weaknesses_exposed=len(weakness_patterns),
        mastered_count=len(mastered_in_session),
        rounds_won=won,
        patterns=pattern_changes,
    )
