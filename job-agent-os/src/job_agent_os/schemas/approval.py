"""Approval schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApprovalResponse(BaseModel):
    """Approval response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    approval_type: str
    title: str
    description: str | None = None
    payload: dict
    options: list[str] = Field(default_factory=list)
    status: str
    action: str | None = None
    feedback: str | None = None
    timeout_seconds: int | None = None
    requested_at: datetime
    responded_at: datetime | None = None


class ApprovalRespondRequest(BaseModel):
    """Approval respond request."""

    action: str = Field(pattern="^(approve|reject|modify|skip)$")
    feedback: str | None = None
    modified_payload: dict | None = None


class BatchApprovalItem(BaseModel):
    """Batch approval item."""

    approval_id: UUID
    action: str
    feedback: str | None = None


class BatchApprovalRequest(BaseModel):
    """Batch approval request."""

    approvals: list[BatchApprovalItem]
