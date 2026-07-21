"""Match schemas."""

from uuid import UUID

from pydantic import BaseModel, Field

from job_agent_os.schemas.job import JobResponse


class MatchScore(BaseModel):
    """Match score details."""

    overall_score: float = Field(ge=0, le=100)
    skill_match: float = Field(ge=0, le=100)
    education_match: float = Field(ge=0, le=100)
    experience_match: float = Field(ge=0, le=100)
    location_match: float = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)


class RecommendationItem(BaseModel):
    """Recommendation item."""

    job: JobResponse
    match_score: float
    skill_match: float
    education_match: float
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    recommendation_reason: str
    risk_factors: list[str] = Field(default_factory=list)


class RecommendationFeedback(BaseModel):
    """Recommendation feedback request."""

    job_id: UUID
    action: str = Field(pattern="^(accept|reject|interested)$")
    reason: str | None = None
    adjust_weights: dict | None = None
