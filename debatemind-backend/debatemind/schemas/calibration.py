from typing import Optional

from pydantic import BaseModel


class CalibrationStatusOut(BaseModel):
    needed: bool
    topic: Optional[str] = None
    index: int = 0
    total: int = 3


class CalibrationAnswerIn(BaseModel):
    text: str


class CalibrationAnswerOut(BaseModel):
    done: bool
    next_topic: Optional[str] = None
    index: int
    total: int
