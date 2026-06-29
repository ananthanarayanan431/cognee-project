from openai import AsyncOpenAI

from debatemind.config import settings

# Shared async OpenRouter client — drop-in OpenAI-compatible, routes to any model
openrouter: AsyncOpenAI = AsyncOpenAI(
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,
)
