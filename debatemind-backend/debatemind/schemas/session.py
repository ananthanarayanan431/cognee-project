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
    has_source: bool = False
    source_status: str = "none"


class SourceUploadOut(BaseModel):
    status: str
    source_filename: str


class SourceStatusOut(BaseModel):
    source_status: str


class SourceUrlOut(BaseModel):
    url: str


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
