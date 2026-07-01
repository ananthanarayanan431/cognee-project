from cachetools import TTLCache

from debatemind.agents.client import openrouter
from debatemind.agents.prompts.opponent import opponent_system_prompt, opponent_user_message
from debatemind.agents.state import DebateState
from debatemind.cognee import recall_weaknesses
from debatemind.config import settings

# Bounded TTL cache: max 1024 users, entries expire after 1 hour.
_weakness_cache: TTLCache = TTLCache(maxsize=1024, ttl=3600)


async def generate_opponent(state: DebateState) -> DebateState:
    user_id = state["user_id"]

    if user_id not in _weakness_cache:
        _weakness_cache[user_id] = await recall_weaknesses(user_id)

    state["weakness_context"] = _weakness_cache[user_id]

    weakness_text = (
        "\n".join(r.get("text", "") for r in state["weakness_context"][:5])
        or "No prior weaknesses recorded — probe broadly."
    )

    difficulty = state.get("difficulty", "targeted")

    user_position = state.get("user_position", "")

    msg = await openrouter.chat.completions.create(
        model=settings.main_model,
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
                ),
            },
        ],
    )
    state["opponent_response"] = msg.choices[0].message.content or ""
    return state
