"""User schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobIntentionCreate(BaseModel):
    """Job intention creation request."""

    name: str = Field(max_length=100)
    region: list[str] = Field(default_factory=list)
    company_type: list[str] = Field(default_factory=list)
    direction: str
    skills: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    education: str | None = None


class JobIntentionResponse(JobIntentionCreate):
    """Job intention response."""

    id: str
    created_at: datetime


class UserResponse(BaseModel):
    """User response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: str
    phone: str | None = None
    preferences: dict = Field(default_factory=dict)
    job_intentions: list = Field(default_factory=list)
    token_budget_daily: int
    token_used_today: int
    created_at: datetime


class UserUpdateRequest(BaseModel):
    """User update request."""

    username: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=20)
    preferences: dict | None = None
    job_intentions: list | None = None
