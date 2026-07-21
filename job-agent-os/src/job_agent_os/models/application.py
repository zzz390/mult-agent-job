"""Application ORM model."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_agent_os.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from job_agent_os.models.job import Job
    from job_agent_os.models.resume import Resume
    from job_agent_os.models.user import User


class Application(Base, UUIDMixin, TimestampMixin):
    """Application table."""

    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_applications_user_job"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    resume_id: Mapped[UUID] = mapped_column(ForeignKey("resumes.id"), nullable=False)
    optimized_resume_id: Mapped[UUID | None] = mapped_column(ForeignKey("resumes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    stage: Mapped[str] = mapped_column(String(30), default="none")
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_follow_up: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_change: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_history: Mapped[list] = mapped_column(JSONB, default=list)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="applications")
    job: Mapped["Job"] = relationship(back_populates="applications")
    resume: Mapped["Resume"] = relationship(foreign_keys=[resume_id])
    optimized_resume: Mapped["Resume | None"] = relationship(foreign_keys=[optimized_resume_id])
