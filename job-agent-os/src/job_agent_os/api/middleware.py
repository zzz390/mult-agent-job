"""Middleware (CORS, request logging, exception handling)."""

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from job_agent_os.core.exceptions import AppException
from job_agent_os.core.utils import generate_uuid, utc_now

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all requests."""

    async def dispatch(self, request: Request, call_next):  # type: ignore
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time

        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} - {duration:.3f}s"
        )
        return response


def setup_exception_handlers(app: FastAPI) -> None:
    """Setup global exception handlers."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "errors": exc.errors,
                "meta": {
                    "request_id": generate_uuid(),
                    "timestamp": utc_now().isoformat(),
                },
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "code": 50000,
                "message": "Internal server error",
                "errors": [],
                "meta": {
                    "request_id": generate_uuid(),
                    "timestamp": utc_now().isoformat(),
                },
            },
        )


def setup_cors(app: FastAPI) -> None:
    """Setup CORS middleware."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def setup_middleware(app: FastAPI) -> None:
    """Setup all middleware."""
    app.add_middleware(RequestLoggingMiddleware)
    setup_cors(app)
    setup_exception_handlers(app)
"""Middleware (CORS, request logging, exception handling)."""
