from pydantic import BaseModel


class TopicSuggestion(BaseModel):
    label: str
    chips: list[str]
