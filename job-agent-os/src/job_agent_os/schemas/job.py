"""Job schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobQuery(BaseModel):
    """Structured job search query."""

    region: list[str] = Field(default_factory=list)
    industry: list[str] = Field(default_factory=list)
    company_type: list[str] = Field(default_factory=list)
    direction: str | None = None
    skills: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    education: str | None = None
    keywords: list[str] = Field(default_factory=list)
    deadline_after: date | None = None


class JobSearchRequest(BaseModel):
    """Job search request."""

    query_text: str | None = None
    structured_query: JobQuery | None = None
    platforms: list[str] | None = None
    use_saved_intention: str | None = None


class ParsedJD(BaseModel):
    """Structured job description."""

    title: str
    company: str
    location: str | None = None
    salary: str | None = None
    requirements: list[str] = Field(default_factory=list)
    skills_required: list[str] = Field(default_factory=list)
    skills_preferred: list[str] = Field(default_factory=list)
    education: str | None = None
    experience: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    deadline: date | None = None
    source_url: str | None = None
    source_platform: str | None = None
    parse_confidence: float = 0.0


class JobResponse(BaseModel):
    """Job response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    company: str
    company_type: str | None = None
    location: str | None = None
    salary_range: str | None = None
    education_required: str | None = None
    skills_required: list[str] = Field(default_factory=list)
    structured_jd: dict = Field(default_factory=dict)
    deadline: date | None = None
    source_platform: str
    source_url: str
    status: str
    created_at: datetime


class ManualJobCreate(BaseModel):
    """Manual job creation request."""

    title: str
    company: str
    company_type: str | None = None
    location: str | None = None
    salary_range: str | None = None
    education_required: str | None = None
    skills_required: list[str] = Field(default_factory=list)
    raw_description: str | None = None
    structured_jd: dict = Field(default_factory=dict)
    deadline: date | None = None
    source_url: str | None = None


class JobListItem(BaseModel):
    """Job list item (lightweight)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    company: str
    location: str | None = None
    salary_range: str | None = None
    deadline: date | None = None
