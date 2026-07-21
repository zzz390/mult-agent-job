"""Unified response models."""

import math
from typing import Any

from fastapi.responses import JSONResponse

from job_agent_os.core.utils import generate_uuid, utc_now


def success_response(data: Any = None, message: str = "success", code: int = 0) -> dict:
    """Create a success response."""
    return {
        "code": code,
        "message": message,
        "data": data,
        "meta": {
            "request_id": generate_uuid(),
            "timestamp": utc_now().isoformat(),
        },
    }


def paginated_response(
    items: list,
    total: int,
    page: int,
    page_size: int,
    message: str = "success",
) -> dict:
    """Create a paginated response."""
    total_pages = math.ceil(total / page_size) if page_size > 0 else 0
    return {
        "code": 0,
        "message": message,
        "data": {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        },
        "meta": {
            "request_id": generate_uuid(),
            "timestamp": utc_now().isoformat(),
        },
    }


def error_response(
    code: int,
    message: str,
    status_code: int = 400,
    errors: list[dict] | None = None,
) -> JSONResponse:
    """Create an error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "errors": errors or [],
            "meta": {
                "request_id": generate_uuid(),
                "timestamp": utc_now().isoformat(),
            },
        },
    )
