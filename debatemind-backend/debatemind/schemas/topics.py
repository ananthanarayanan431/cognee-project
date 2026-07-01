from pydantic import BaseModel


class DebatableQuestion(BaseModel):
    id: str
    domain: str
    title: str
    description: str


class GenerateTopicsIn(BaseModel):
    domain: str
    count: int = 5
