import json
from anthropic import AsyncAnthropic
from app.config import settings
from app.agents.state import DebateState

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)


async def judge_exchange(state: DebateState) -> DebateState:
    prompt = f"""Score this debate exchange. Return JSON only.

Topic: {state['topic']}
User: {state['user_message']}
Opponent: {state['opponent_response']}

Return exactly:
{{
  "logic": <1-10>,
  "evidence": <1-10>,
  "rhetoric": <1-10>,
  "fallacy": "<fallacy name or null>",
  "outcome": "<Won|Lost|Neutral>"
}}

Outcome = Won if user's argument is stronger, Lost if opponent's is stronger."""

    msg = await _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = json.loads(msg.content[0].text)
        state["judge_logic"] = float(data.get("logic", 5))
        state["judge_evidence"] = float(data.get("evidence", 5))
        state["judge_rhetoric"] = float(data.get("rhetoric", 5))
        state["judge_fallacy"] = data.get("fallacy")
        state["outcome"] = data.get("outcome", "Neutral")
    except Exception:
        state["judge_logic"] = 5.0
        state["judge_evidence"] = 5.0
        state["judge_rhetoric"] = 5.0
        state["judge_fallacy"] = None
        state["outcome"] = "Neutral"
    return state
