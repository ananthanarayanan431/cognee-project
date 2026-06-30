import json

from debatemind.agents.client import openrouter
from debatemind.agents.prompts.extractor import extractor_prompt
from debatemind.agents.state import DebateState
from debatemind.config import settings


async def extract_argument(state: DebateState) -> DebateState:
    prompt = extractor_prompt(state["topic"], state["user_message"], state.get("description") or "")
    msg = await openrouter.chat.completions.create(
        model=settings.fast_model,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = json.loads(msg.choices[0].message.content or "")
        state["extracted_pattern"] = data.get("pattern_type", "EvidenceBased")
        state["extracted_fallacy"] = data.get("fallacy")
        state["evidence_quality"] = data.get("evidence_quality", "Moderate")
    except Exception:
        state["extracted_pattern"] = "EvidenceBased"
        state["extracted_fallacy"] = None
        state["evidence_quality"] = "Moderate"
    return state
