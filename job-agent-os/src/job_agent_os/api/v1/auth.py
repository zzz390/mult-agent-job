"""Authentication endpoints."""

from fastapi import APIRouter, status

from job_agent_os.api.deps import DBSession
from job_agent_os.api.response import success_response
from job_agent_os.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
)
from job_agent_os.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: DBSession) -> dict:
    """Register a new user."""
    service = AuthService(db)
    user, tokens = await service.register(
        username=request.username,
        email=request.email,
        password=request.password,
        phone=request.phone,
    )
    return success_response(data=tokens.model_dump())


@router.post("/login")
async def login(request: LoginRequest, db: DBSession) -> dict:
    """Login user."""
    service = AuthService(db)
    user, tokens = await service.login(request.email, request.password)
    return success_response(data=tokens.model_dump())


@router.post("/refresh")
async def refresh_token(request: RefreshTokenRequest, db: DBSession) -> dict:
    """Refresh access token."""
    service = AuthService(db)
    tokens = await service.refresh_token(request.refresh_token)
    return success_response(data=tokens.model_dump())


@router.post("/logout")
async def logout() -> dict:
    """Logout user (client should discard tokens)."""
    return success_response(message="Logged out successfully")

