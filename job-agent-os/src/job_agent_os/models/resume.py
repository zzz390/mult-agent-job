"""Resume ORM model."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from job_agent_os.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from job_agent_os.models.user import User


class Resume(Base, UUIDMixin, TimestampMixin):
    """Resume table."""

    __tablename__ = "resumes"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(20), default="v1")
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list | None] = mapped_column(Vector(1024), nullable=True)
    chunks: Mapped[list] = mapped_column(JSONB, default=list)
    target_direction: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="resumes")
