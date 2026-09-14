"""Session schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    """Session creation request."""

    intent: str
    mode: str = Field(default="full", pattern="^(full|search_only|match_only|resume_only|interview_only)$")
    resume_id: UUID | None = None
    options: dict = Field(default_factory=dict)


class SessionProgress(BaseModel):
    """Session progress info."""

    completed_steps: list[str] = Field(default_factory=list)
    current_step: str | None = None
    pending_steps: list[str] = Field(default_factory=list)
    # Updated by HarnessRuntime when a graph node starts/finishes.  Keeping
    # this separate from ``current_step`` lets clients state plainly which
    # Agent is working without having to infer it from a pipeline position.
    active_agent: str | None = None
    active_agent_status: str | None = None
    # Fine-grained, user-safe activity published by long-running search work.
    # These are intentionally aggregate values; source URLs and raw crawler
    # output never belong in an SSE/session progress payload.
    activity_message: str | None = None
    items_found: int = 0
    items_saved: int = 0
    last_activity_at: str | None = None


class PendingApprovalInfo(BaseModel):
    """Pending approval info."""

    id: UUID
    type: str
    title: str


class SessionResponse(BaseModel):
    """Session response."""

    session_id: UUID
    status: str
    intent: str | None = None
    current_phase: str | None = None
    progress: SessionProgress | None = None
    pending_approval: PendingApprovalInfo | None = None
    results_summary: dict = Field(default_factory=dict)
    token_usage: dict = Field(default_factory=dict)
    started_at: datetime | None = None
    updated_at: datetime | None = None


class SessionMessage(BaseModel):
    """Session message request."""

    content: str
    message_type: str = Field(default="text", pattern="^(text|clarification|feedback)$")


class SessionMessageResponse(BaseModel):
    """Session message response."""

    message_id: UUID
    response: str
    session_status: str
