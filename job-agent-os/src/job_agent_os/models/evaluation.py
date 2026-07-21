"""Evaluation ORM model."""

from uuid import UUID

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from job_agent_os.models.base import Base, TimestampMixin, UUIDMixin


class Evaluation(Base, UUIDMixin, TimestampMixin):
    """Evaluation record table."""

    __tablename__ = "evaluations"

    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    agent_log_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_logs.id"), nullable=True)
    session_id: Mapped[UUID | None] = mapped_column(nullable=True)
    eval_type: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    eval_input: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    eval_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ground_truth: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    judge_method: Mapped[str] = mapped_column(String(50), nullable=False)
    judge_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    judge_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("prompt_versions.id"), nullable=True)
    dataset_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    batch_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")
