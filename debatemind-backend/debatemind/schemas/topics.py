from pydantic import BaseModel, Field


class DebatableQuestion(BaseModel):
    id: str
    domain: str
    title: str
    description: str


class GenerateTopicsIn(BaseModel):
    domain: str
    count: int = Field(default=5, ge=1)
