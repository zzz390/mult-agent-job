"""Common schemas (pagination, response wrapper)."""

from datetime import UTC, datetime
from typing import Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

T = TypeVar("T")


class Meta(BaseModel):
    """Response metadata."""

    request_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PaginationParams(BaseModel):
    """Pagination request parameters."""

    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    sort_by: str = Field(default="created_at", description="Sort field")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$", description="Sort order")


class PaginationMeta(BaseModel):
    """Pagination metadata in response."""

    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class ApiResponse(BaseModel, Generic[T]):
    """Unified API response wrapper."""

    code: int = 0
    message: str = "success"
    data: T | None = None
    meta: Meta = Field(default_factory=Meta)


class PaginatedData(BaseModel, Generic[T]):
    """Paginated data wrapper."""

    items: list[T]
    pagination: PaginationMeta


class ErrorResponse(BaseModel):
    """Error response."""

    code: int
    message: str
    errors: list[dict] = Field(default_factory=list)
    meta: Meta = Field(default_factory=Meta)
