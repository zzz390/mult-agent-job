"""Custom exception hierarchy."""

from typing import Any


class AppException(Exception):  # noqa: N818 - compatibility with public API
    """Base application exception."""

    def __init__(
        self,
        code: int,
        message: str,
        status_code: int = 500,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.errors = errors or []
        super().__init__(message)


class ValidationException(AppException):
    """Validation error (400)."""

    def __init__(
        self,
        message: str = "Validation failed",
        code: int = 40000,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=400, errors=errors)


class UnauthorizedException(AppException):
    """Unauthorized error (401)."""

    def __init__(self, message: str = "Unauthorized", code: int = 40100) -> None:
        super().__init__(code=code, message=message, status_code=401)


class ForbiddenException(AppException):
    """Forbidden error (403)."""

    def __init__(self, message: str = "Forbidden", code: int = 40104) -> None:
        super().__init__(code=code, message=message, status_code=403)


class NotFoundException(AppException):
    """Resource not found error (404)."""

    def __init__(self, message: str = "Resource not found", code: int = 40400) -> None:
        super().__init__(code=code, message=message, status_code=404)


class ConflictException(AppException):
    """Conflict error (409)."""

    def __init__(self, message: str = "Resource conflict", code: int = 40900) -> None:
        super().__init__(code=code, message=message, status_code=409)


class RateLimitException(AppException):
    """Rate limit exceeded error (429)."""

    def __init__(self, message: str = "Rate limit exceeded", code: int = 42900) -> None:
        super().__init__(code=code, message=message, status_code=429)


class ApprovalTimeoutException(AppException):
    """Approval timeout error (408)."""

    def __init__(self, message: str = "Approval timeout", code: int = 40702) -> None:
        super().__init__(code=code, message=message, status_code=408)


class AgentExecutionException(AppException):
    """Agent execution error (500)."""

    def __init__(self, message: str = "Agent execution failed", code: int = 40602) -> None:
        super().__init__(code=code, message=message, status_code=500)


class ExternalServiceException(AppException):
    """External service error (502)."""

    def __init__(self, message: str = "External service error", code: int = 50001) -> None:
        super().__init__(code=code, message=message, status_code=502)
