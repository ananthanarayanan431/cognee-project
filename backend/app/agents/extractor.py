import json
from anthropic import AsyncAnthropic
from app.config import settings
from app.agents.state import DebateState

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

PATTERN_TYPES = [
    "EvidenceBased", "AppealToAuthority", "StrawMan", "AdHominem",
    "SlipperySlope", "FalseEquivalence", "EmotionalAppeal",
    "AnecdotalEvidence", "Concession",
]


async def extract_argument(state: DebateState) -> DebateState:
    prompt = f"""Analyze this debate argument and return JSON only.

Topic: {state['topic']}
Argument: {state['user_message']}

Return exactly:
{{
  "pattern_type": "<one of: {', '.join(PATTERN_TYPES)}>",
  "fallacy": "<fallacy name or null>",
  "evidence_quality": "<Strong|Moderate|Weak|Absent>"
}}"""

    msg = await _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = json.loads(msg.content[0].text)
        state["extracted_pattern"] = data.get("pattern_type", "EvidenceBased")
        state["extracted_fallacy"] = data.get("fallacy")
        state["evidence_quality"] = data.get("evidence_quality", "Moderate")
    except Exception:
        state["extracted_pattern"] = "EvidenceBased"
        state["extracted_fallacy"] = None
        state["evidence_quality"] = "Moderate"
    return state
