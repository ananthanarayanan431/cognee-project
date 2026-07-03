import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.models.user_fact import UserFact


async def record_user_facts(
    db: AsyncSession, user_id: str, session_id: str, facts: list[str]
) -> list[str]:
    """Persist newly revealed personal facts, skipping ones already on file.

    Returns only the facts that were actually new — a fact mentioned again in
    a later turn (e.g. the user restating their name) shouldn't keep
    re-writing the same row or re-triggering a Cognee write. The in-memory
    `seen` check is only a fast path; the DB-level unique constraint on
    (user_id, fact_text) is what actually protects against a concurrent
    request inserting the same fact between our SELECT and INSERT.
    """
    if not facts:
        return []

    existing = await db.execute(select(UserFact.fact_text).where(UserFact.user_id == user_id))
    seen = {f.strip().lower() for f in existing.scalars().all()}

    new_facts = []
    for fact in facts:
        fact = fact.strip()
        if not fact or fact.lower() in seen:
            continue
        stmt = (
            pg_insert(UserFact)
            .values(id=str(uuid.uuid4()), user_id=user_id, session_id=session_id, fact_text=fact)
            .on_conflict_do_nothing(index_elements=["user_id", "fact_text"])
        )
        result = await db.execute(stmt)
        seen.add(fact.lower())
        if result.rowcount:
            new_facts.append(fact)

    if new_facts:
        await db.commit()
    return new_facts
