import logging

from debatemind.agents.client import openrouter
from debatemind.config import settings

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a concise debate-session title generator. "
    "Given a debate topic and optional description, reply with ONLY a punchy, "
    "4–6 word title that captures the essence of the debate — no punctuation at "
    "the end, no quotes, no explanation. Examples: "
    "'AI Job Displacement Debate', 'Climate Policy Showdown', 'Free Speech vs Safety'."
)


async def generate_session_title(topic: str, description: str = "") -> str:
    """Return a short LLM-generated title for a debate session."""
    user_content = f"Topic: {topic}"
    if description:
        user_content += f"\nDescription: {description}"

    try:
        resp = await openrouter.chat.completions.create(
            model=settings.fast_model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_content},
            ],
            max_tokens=20,
            temperature=0.7,
        )
        title = (resp.choices[0].message.content or "").strip().strip('"').strip("'")
        return title or topic[:60]
    except Exception:
        logger.exception("title generation failed for topic %r", topic)
        return topic[:60]  # graceful fallback
