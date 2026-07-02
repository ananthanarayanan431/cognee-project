import json

from debatemind.agents.client import openrouter
from debatemind.agents.prompts.judge import JUDGE_RESPONSE_SCHEMA, judge_prompt
from debatemind.agents.state import DebateState
from debatemind.config import settings


async def judge_exchange(state: DebateState) -> DebateState:
    prompt = judge_prompt(state["topic"], state["user_message"], state["opponent_response"])
    msg = await openrouter.chat.completions.create(
        model=state.get("judge_model") or settings.fast_model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_schema", "json_schema": JUDGE_RESPONSE_SCHEMA},
    )
    try:
        data = json.loads(msg.choices[0].message.content or "")
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
