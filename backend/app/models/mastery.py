from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
import uuid
from app.database import Base


class MasteryLog(Base):
    __tablename__ = "mastery_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    pattern_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="MASTERED")
    rounds_to_mastery: Mapped[int] = mapped_column(Integer, default=0)
    mastered_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reactivated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)
