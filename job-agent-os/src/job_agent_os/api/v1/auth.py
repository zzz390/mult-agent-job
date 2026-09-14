"""Authentication endpoints with rotating HttpOnly refresh cookies."""

from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Cookie, Header, Response, status

from job_agent_os.api.deps import DBSession
from job_agent_os.api.response import success_response
from job_agent_os.core.security import revoke_token
from job_agent_os.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from job_agent_os.services.auth_service import AuthService
from job_agent_os.settings import get_settings

router = APIRouter()
_REFRESH_COOKIE = "job_agent_refresh"


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=settings.env == "prod",
        samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/v1/auth",
    )


def _browser_payload(tokens: TokenResponse) -> dict:
    payload = tokens.model_dump()
    # The refresh credential lives only in the HttpOnly cookie.
    payload["refresh_token"] = ""
    return payload


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest, response: Response, db: DBSession
) -> dict:
    service = AuthService(db)
    _, tokens = await service.register(
        username=request.username,
        email=request.email,
        password=request.password,
        phone=request.phone,
    )
    _set_refresh_cookie(response, tokens.refresh_token)
    return success_response(data=_browser_payload(tokens))


@router.post("/login")
async def login(request: LoginRequest, response: Response, db: DBSession) -> dict:
    service = AuthService(db)
    _, tokens = await service.login(request.email, request.password)
    _set_refresh_cookie(response, tokens.refresh_token)
    return success_response(data=_browser_payload(tokens))


@router.post("/refresh")
async def refresh_token(
    response: Response,
    db: DBSession,
    request: RefreshTokenRequest | None = None,
    cookie_token: Annotated[str | None, Cookie(alias=_REFRESH_COOKIE)] = None,
) -> dict:
    # An explicit non-empty body token takes precedence (API clients/tests);
    # browsers normally send an empty body and use the HttpOnly cookie.
    token = (request.refresh_token if request and request.refresh_token else None) or cookie_token
    if not token:
        from job_agent_os.core.exceptions import UnauthorizedException

        raise UnauthorizedException(message="Refresh token not provided")
    tokens = await AuthService(db).refresh_token(token)
    _set_refresh_cookie(response, tokens.refresh_token)
    return success_response(data=_browser_payload(tokens))


@router.post("/logout")
async def logout(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
    cookie_token: Annotated[str | None, Cookie(alias=_REFRESH_COOKIE)] = None,
) -> dict:
    """Revoke presented tokens and remove the browser refresh cookie."""
    tokens = []
    if authorization and authorization.startswith("Bearer "):
        tokens.append(authorization.removeprefix("Bearer ").strip())
    if cookie_token:
        tokens.append(cookie_token)
    for token in tokens:
        # Logout remains idempotent even for expired/invalid credentials.
        with suppress(Exception):
            await revoke_token(token)
    response.delete_cookie(key=_REFRESH_COOKIE, path="/v1/auth")
    return success_response(message="Logged out successfully")
