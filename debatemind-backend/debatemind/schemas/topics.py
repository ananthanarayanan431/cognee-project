from typing import Literal

from pydantic import BaseModel, Field

Domain = Literal["POLICY", "TECHNOLOGY", "SOCIETY", "LIFE"]


class DebatableQuestion(BaseModel):
    id: str
    domain: Domain
    title: str
    description: str


class GenerateTopicsIn(BaseModel):
    domain: Domain
    count: int = Field(default=5, ge=1)
    focus: str = Field(default="", max_length=200)
