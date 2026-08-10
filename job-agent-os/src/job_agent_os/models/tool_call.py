"""ToolCall ORM model."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from job_agent_os.models.base import Base, UUIDMixin


class ToolCall(Base, UUIDMixin):
    """Tool call record table."""

    __tablename__ = "tool_calls"

    agent_log_id: Mapped[UUID] = mapped_column(ForeignKey("agent_logs.id"), nullable=False)
    # Note: session_id has no ForeignKey constraint because sessions may be
    # stored in-memory (e.g. LangGraph checkpointer) rather than in a DB table.
    session_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_category: Mapped[str] = mapped_column(String(50), nullable=False)
    call_order: Mapped[int] = mapped_column(Integer, default=1)
    input_params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    tokens_consumed: Mapped[int] = mapped_column(Integer, default=0)
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
