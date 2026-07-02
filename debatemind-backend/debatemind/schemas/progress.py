from datetime import datetime

from pydantic import BaseModel


class ThinkingStyle(BaseModel):
    logic: float
    evidence: float
    rhetoric: float


class MasteredPattern(BaseModel):
    pattern: str
    mastered_at: datetime
    rounds_to_mastery: int
    reactivated: bool


class TopicWinRate(BaseModel):
    topic: str
    win_rate: float


class WeaknessTrendItem(BaseModel):
    pattern: str
    weight: float


class ProgressOut(BaseModel):
    weaknesses: list[dict]
    sessions: int
    win_rate: float
    streak: int
    thinking_style: ThinkingStyle
    mastered: list[MasteredPattern]
    win_rate_by_topic: list[TopicWinRate]
    weakness_trend: list[WeaknessTrendItem]
