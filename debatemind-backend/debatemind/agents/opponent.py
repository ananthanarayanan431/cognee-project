from debatemind.agents.client import openrouter
from debatemind.agents.prompts.opponent import opponent_system_prompt, opponent_user_message
from debatemind.agents.state import DebateState
from debatemind.config import settings
from debatemind.services.cognee_svc import recall_weaknesses

# module-level cache so recall_weaknesses is only called once per user
# across all pipeline invocations, not re-fetched on every turn.
_weakness_cache: dict[str, list] = {}


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

    msg = await openrouter.chat.completions.create(
        model=settings.main_model,
        max_tokens=300,
        messages=[
            {
                "role": "system",
                "content": opponent_system_prompt(weakness_text, difficulty),
            },
            {
                "role": "user",
                "content": opponent_user_message(state["topic"], state["user_message"]),
            },
        ],
    )
    state["opponent_response"] = msg.choices[0].message.content or ""
    return state
