from cachetools import TTLCache

from debatemind.agents.client import openrouter
from debatemind.agents.prompts.opponent import (
    continuation_system_prompt,
    continuation_user_message,
    opening_system_prompt,
    opening_user_message,
    opponent_system_prompt,
    opponent_user_message,
)
from debatemind.agents.state import DebateState
from debatemind.cognee import recall_weaknesses
from debatemind.cognee._base import filter_out_patterns
from debatemind.config import settings
from debatemind.database import AsyncSessionLocal
from debatemind.services.mastery_svc import get_active_mastered_patterns

# Bounded TTL cache: max 1024 users, entries expire after 1 hour.
# Holds the *raw* (unfiltered) recall so mastered-pattern exclusion can be
# re-applied per turn against the live mastery state instead of being frozen
# into the cache — mastering a pattern takes effect on the very next turn.
# The 1-hour TTL is just a safety net for idle users; freshness within an
# active session comes from invalidate_weakness_cache(), called once each
# background remember_argument() write completes (see pipeline.py).
_weakness_cache: TTLCache = TTLCache(maxsize=1024, ttl=3600)


def invalidate_weakness_cache(user_id: str) -> None:
    """Force the next recall_weaknesses() call for this user to hit Cognee live.

    Called after a new argument is written to the knowledge graph so a fallacy
    or weak pattern surfaced this session is available to the opponent on the
    very next turn, instead of waiting up to an hour for the TTL to lapse.
    """
    _weakness_cache.pop(user_id, None)


async def generate_opponent(state: DebateState) -> DebateState:
    user_id = state["user_id"]

    if user_id not in _weakness_cache:
        _weakness_cache[user_id] = await recall_weaknesses(user_id)

    # Exclude patterns the user has already mastered so the opponent stops
    # exploiting beaten weaknesses (the behavioural payoff of forget()). This
    # DB read is best-effort — a transient failure shouldn't abort the turn,
    # it just means mastered patterns aren't filtered out this time.
    try:
        async with AsyncSessionLocal() as db:
            mastered = await get_active_mastered_patterns(db, user_id)
    except Exception:
        mastered = set()
    state["weakness_context"] = filter_out_patterns(_weakness_cache[user_id], mastered)

    weakness_text = (
        "\n".join(r.get("text", "") for r in state["weakness_context"][:5])
        or "No prior weaknesses recorded — probe broadly."
    )

    difficulty = state.get("difficulty", "targeted")

    user_position = state.get("user_position", "")

    msg = await openrouter.chat.completions.create(
        model=state.get("model") or settings.main_model,
        max_tokens=300,
        messages=[
            {
                "role": "system",
                "content": opponent_system_prompt(weakness_text, difficulty, user_position),
            },
            {
                "role": "user",
                "content": opponent_user_message(
                    state["topic"],
                    state["user_message"],
                    state.get("description") or "",
                    user_position,
                    state.get("recent_exchanges") or [],
                ),
            },
        ],
    )
    state["opponent_response"] = msg.choices[0].message.content or ""
    return state


async def generate_opening(
    topic: str,
    description: str,
    difficulty: str,
    user_position: str,
    model: str | None = None,
) -> str:
    """Generate the opponent's opening message for a fresh session.

    Frames the motion and invites the user to argue — no rebuttal, no prior
    turns. Kept separate from the graph pipeline since nothing is persisted or
    scored for the opening.
    """
    msg = await openrouter.chat.completions.create(
        model=model or settings.main_model,
        max_tokens=200,
        messages=[
            {
                "role": "system",
                "content": opening_system_prompt(difficulty, user_position),
            },
            {
                "role": "user",
                "content": opening_user_message(topic, description, user_position),
            },
        ],
    )
    return msg.choices[0].message.content or ""


async def generate_continuation(
    topic: str,
    description: str,
    difficulty: str,
    user_position: str,
    last_exchanges: list[dict],
    model: str | None = None,
) -> str:
    """Generate a re-engagement message when the user returns to a paused session.

    Uses the last few exchanges as context so the opponent picks up the thread
    rather than restarting. Nothing is persisted — this is ephemeral framing.
    """
    msg = await openrouter.chat.completions.create(
        model=model or settings.main_model,
        max_tokens=200,
        messages=[
            {
                "role": "system",
                "content": continuation_system_prompt(difficulty, user_position),
            },
            {
                "role": "user",
                "content": continuation_user_message(
                    topic, description, last_exchanges, user_position
                ),
            },
        ],
    )
    return msg.choices[0].message.content or ""
