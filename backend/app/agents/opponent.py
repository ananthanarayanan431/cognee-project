from anthropic import AsyncAnthropic
from app.config import settings
from app.agents.state import DebateState
from app.services.cognee_svc import recall_weaknesses

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

_DIFFICULTY_INSTRUCTIONS = {
    "balanced": "Explore multiple angles; target a known weakness ~60% of the time.",
    "targeted": "Every response MUST target one of the user's listed weakness patterns.",
    "ruthless": "Hammer the same weakness from different angles until they find a true counter.",
}


async def generate_opponent(state: DebateState) -> DebateState:
    # Load fingerprint if not already loaded (session start)
    if not state.get("weakness_context"):
        state["weakness_context"] = await recall_weaknesses(state["user_id"])

    weakness_text = "\n".join(
        r.get("text", "") for r in state["weakness_context"][:5]
    ) or "No prior weaknesses recorded — probe broadly."

    difficulty = state.get("difficulty", "targeted")

    system = f"""You are a world-class debate opponent.

User's cognitive fingerprint (known weaknesses):
{weakness_text}

Difficulty: {difficulty}
Instruction: {_DIFFICULTY_INSTRUCTIONS.get(difficulty, _DIFFICULTY_INSTRUCTIONS['targeted'])}

Rules:
- Respond with a sharp, substantive counter-argument. No softening.
- Never concede unless the user's argument is genuinely irrefutable.
- Do NOT repeat an argument pattern you already used this session.
- Keep response under 120 words."""

    msg = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=system,
        messages=[
            {"role": "user", "content": f"Topic: {state['topic']}\n\nUser argues: {state['user_message']}"}
        ],
    )
    state["opponent_response"] = msg.content[0].text
    return state
