"""Resume schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EducationInfo(BaseModel):
    """Education information."""

    school: str | None = None
    degree: str | None = None
    major: str | None = None
    graduation: str | None = None


class ProjectExp(BaseModel):
    """Project experience."""

    name: str
    description: str | None = None
    tech_stack: list[str] = Field(default_factory=list)


class InternExp(BaseModel):
    """Internship experience."""

    company: str
    role: str | None = None
    duration: str | None = None
    description: str | None = None


class StructuredResumeData(BaseModel):
    """Structured resume data."""

    name: str | None = None
    education: EducationInfo | None = None
    skills: list[str] = Field(default_factory=list)
    projects: list[ProjectExp] = Field(default_factory=list)
    internships: list[InternExp] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class ResumeCreate(BaseModel):
    """Resume creation metadata."""

    title: str = Field(max_length=200)
    target_direction: str | None = None


class ResumeResponse(BaseModel):
    """Resume response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    version: str
    file_type: str | None = None
    file_path: str | None = None
    file_size_bytes: int | None = None
    is_encrypted: bool = False
    structured_data: dict = Field(default_factory=dict)
    target_direction: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ResumeUpdate(BaseModel):
    """Resume update request."""

    title: str | None = None
    structured_data: dict | None = None
    is_active: bool | None = None
