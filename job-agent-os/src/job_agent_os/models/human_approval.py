"""HumanApproval ORM model."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from job_agent_os.models.base import Base, TimestampMixin, UUIDMixin


class HumanApproval(Base, UUIDMixin, TimestampMixin):
    """Human approval table."""

    __tablename__ = "human_approvals"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    agent_log_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_logs.id"), nullable=True)
    session_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    approval_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, default=list)
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    modified_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_action_on_timeout: Mapped[str] = mapped_column(String(20), default="skip")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
