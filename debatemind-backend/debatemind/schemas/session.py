from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SessionStartIn(BaseModel):
    topic: str
    description: str = ""
    difficulty: str = "targeted"
    user_position: str = "against"


class SessionOut(BaseModel):
    session_id: str
    topic: str
    description: str
    difficulty: str


class MessageIn(BaseModel):
    text: str


class JudgeScores(BaseModel):
    logic: float
    evidence: float
    rhetoric: float
    fallacy: Optional[str]
    outcome: str


class EndSessionOut(BaseModel):
    status: str


class WeaknessChange(BaseModel):
    pattern: str
    before: float
    after: float
    mastered: bool
    rounds_to_mastery: Optional[int] = None


class SessionSummaryOut(BaseModel):
    topic: str
    difficulty: str
    score: float
    exchanges: int
    weaknesses_exposed: int
    mastered_count: int
    rounds_won: int
    patterns: list[WeaknessChange]


class TranscriptExchange(BaseModel):
    turn_number: int
    user_message: str
    opponent_response: str
    judge_logic: Optional[float] = None
    judge_evidence: Optional[float] = None
    judge_rhetoric: Optional[float] = None
    fallacy: Optional[str] = None
    outcome: Optional[str] = None
    created_at: datetime


class TranscriptOut(BaseModel):
    session_id: str
    topic: str
    difficulty: str
    started_at: datetime
    exchanges: list[TranscriptExchange]


class SessionListItemOut(BaseModel):
    session_id: str
    topic: str
    difficulty: str
    status: str
    overall_score: float
    exchanges: int
    started_at: datetime
    ended_at: Optional[datetime] = None
