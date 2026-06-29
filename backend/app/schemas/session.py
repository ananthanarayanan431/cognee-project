from pydantic import BaseModel
from typing import Optional


class SessionStartIn(BaseModel):
    topic: str
    difficulty: str = "targeted"
    user_position: str = "against"


class SessionOut(BaseModel):
    session_id: str
    topic: str
    difficulty: str


class MessageIn(BaseModel):
    text: str


class JudgeScores(BaseModel):
    logic: float
    evidence: float
    rhetoric: float
    fallacy: Optional[str]
    outcome: str
