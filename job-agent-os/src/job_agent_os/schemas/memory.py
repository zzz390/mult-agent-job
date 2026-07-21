"""Memory schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MemoryCreate(BaseModel):
    """Memory creation request."""

    category: str
    content: dict
    importance_score: float = Field(default=0.5, ge=0, le=1)


class MemoryResponse(BaseModel):
    """Memory response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    memory_type: str
    category: str
    key: str
    content: dict
    importance_score: float
    access_count: int
    created_at: datetime


class MemorySearchRequest(BaseModel):
    """Memory search request."""

    query: str
    category: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)
