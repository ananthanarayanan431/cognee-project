import httpx
from openai import AsyncOpenAI

from debatemind.config import settings

# 30 s total timeout, 5 s connect timeout — prevents hanging workers on LLM slowdowns
openrouter: AsyncOpenAI = AsyncOpenAI(
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,
    timeout=httpx.Timeout(30.0, connect=5.0),
)
