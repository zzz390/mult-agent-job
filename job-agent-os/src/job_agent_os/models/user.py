"""User ORM model."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_agent_os.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from job_agent_os.models.application import Application
    from job_agent_os.models.resume import Resume


class User(Base, UUIDMixin, TimestampMixin):
    """User table."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    job_intentions: Mapped[list] = mapped_column(JSONB, default=list)
    subscription_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    token_budget_daily: Mapped[int] = mapped_column(Integer, default=100000)
    token_used_today: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    resumes: Mapped[list["Resume"]] = relationship(back_populates="user", lazy="selectin")
    applications: Mapped[list["Application"]] = relationship(back_populates="user", lazy="selectin")
