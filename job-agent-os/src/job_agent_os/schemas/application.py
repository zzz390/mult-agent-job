"""Application schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApplicationCreate(BaseModel):
    """Application creation request."""

    job_id: UUID
    resume_id: UUID
    priority: str = Field(default="medium", pattern="^(high|medium|low)$")
    notes: str | None = None


class ApplicationStatusUpdate(BaseModel):
    """Application status update request."""

    status: str
    stage: str | None = None
    notes: str | None = None
    next_follow_up: datetime | None = None


class ApplicationResponse(BaseModel):
    """Application response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    resume_id: UUID
    status: str
    stage: str
    match_score: float | None = None
    match_report: dict | None = None
    priority: str
    notes: str | None = None
    applied_at: datetime | None = None
    next_follow_up: datetime | None = None
    created_at: datetime


class KanbanView(BaseModel):
    """Kanban board view."""

    pending: list[ApplicationResponse] = Field(default_factory=list)
    applied: list[ApplicationResponse] = Field(default_factory=list)
    written_test: list[ApplicationResponse] = Field(default_factory=list)
    round1: list[ApplicationResponse] = Field(default_factory=list)
    round2: list[ApplicationResponse] = Field(default_factory=list)
    hr_interview: list[ApplicationResponse] = Field(default_factory=list)
    offer: list[ApplicationResponse] = Field(default_factory=list)
    rejected: list[ApplicationResponse] = Field(default_factory=list)
    statistics: dict = Field(default_factory=dict)


class ApplicationStatistics(BaseModel):
    """Application statistics."""

    total_applications: int = 0
    by_status: dict = Field(default_factory=dict)
    by_platform: dict = Field(default_factory=dict)
    pass_rate: float = 0.0
    avg_match_score: float = 0.0
    stage_conversion: dict = Field(default_factory=dict)
