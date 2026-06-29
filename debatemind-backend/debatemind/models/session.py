import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from debatemind.database import Base


class DebateSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    topic: Mapped[str] = mapped_column(String)
    difficulty: Mapped[str] = mapped_column(String, default="targeted")
    user_position: Mapped[str] = mapped_column(String, default="against")
    status: Mapped[str] = mapped_column(String, default="active")
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)


class Exchange(Base):
    __tablename__ = "exchanges"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"))
    turn_number: Mapped[int] = mapped_column(Integer)
    user_message: Mapped[str] = mapped_column(Text)
    opponent_response: Mapped[str] = mapped_column(Text, nullable=True)
    detected_pattern: Mapped[str] = mapped_column(String, nullable=True)
    fallacy: Mapped[str] = mapped_column(String, nullable=True)
    judge_logic: Mapped[float] = mapped_column(Float, nullable=True)
    judge_evidence: Mapped[float] = mapped_column(Float, nullable=True)
    judge_rhetoric: Mapped[float] = mapped_column(Float, nullable=True)
    outcome: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
