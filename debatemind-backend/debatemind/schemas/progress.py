from pydantic import BaseModel


class ThinkingStyle(BaseModel):
    logic: float
    evidence: float
    rhetoric: float


class ProgressOut(BaseModel):
    weaknesses: list[dict]
    sessions: int
    win_rate: float
    thinking_style: ThinkingStyle
