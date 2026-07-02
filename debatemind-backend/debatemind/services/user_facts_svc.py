from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.models.user_fact import UserFact


async def record_user_facts(
    db: AsyncSession, user_id: str, session_id: str, facts: list[str]
) -> list[str]:
    """Persist newly revealed personal facts, skipping ones already on file.

    Returns only the facts that were actually new — a fact mentioned again in
    a later turn (e.g. the user restating their name) shouldn't keep
    re-writing the same row or re-triggering a Cognee write.
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
        db.add(UserFact(user_id=user_id, session_id=session_id, fact_text=fact))
        seen.add(fact.lower())
        new_facts.append(fact)

    if new_facts:
        await db.commit()
    return new_facts
