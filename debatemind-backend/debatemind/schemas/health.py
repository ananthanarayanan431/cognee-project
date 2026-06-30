from pydantic import BaseModel


class HealthOut(BaseModel):
    status: str


class ReadinessOut(BaseModel):
    status: str
    database: str
