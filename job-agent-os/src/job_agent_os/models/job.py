"""Job ORM model."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_agent_os.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from job_agent_os.models.application import Application


class Job(Base, UUIDMixin, TimestampMixin):
    """Job table."""

    __tablename__ = "jobs"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    company: Mapped[str] = mapped_column(String(300), nullable=False)
    company_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_platform: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    raw_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_jd: Mapped[dict] = mapped_column(JSONB, default=dict)
    salary_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    education_required: Mapped[str | None] = mapped_column(String(50), nullable=True)
    experience_required: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skills_required: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    skills_preferred: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    headcount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    job_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    embedding: Mapped[list | None] = mapped_column(Vector(1024), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_location", "location"),
        Index("ix_jobs_created_at", "created_at"),
        Index("ix_jobs_source_platform", "source_platform"),
    )

    # Relationships
    applications: Mapped[list["Application"]] = relationship(back_populates="job", lazy="noload")
