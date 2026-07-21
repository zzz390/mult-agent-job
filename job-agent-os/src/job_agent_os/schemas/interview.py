"""Interview schemas."""

from uuid import UUID

from pydantic import BaseModel, Field


class QuestionGenerateRequest(BaseModel):
    """Interview question generation request."""

    job_id: UUID
    resume_id: UUID | None = None
    question_types: list[str] = Field(default_factory=lambda: ["technical", "behavioral"])
    difficulty: str = Field(default="mixed", pattern="^(easy|medium|hard|mixed)$")
    count: int = Field(default=10, ge=1, le=50)


class InterviewQuestion(BaseModel):
    """Interview question."""

    id: int
    type: str
    category: str
    difficulty: str
    question: str
    reference_answer: str
    scoring_criteria: list[str] = Field(default_factory=list)
    follow_up: str | None = None


class InterviewQuestionSet(BaseModel):
    """Interview question set response."""

    status: str
    job_title: str | None = None
    questions: list[InterviewQuestion] = Field(default_factory=list)
