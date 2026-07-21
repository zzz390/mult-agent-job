"""Authentication service."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.core.error_codes import ErrorCode
from job_agent_os.core.exceptions import ConflictException, UnauthorizedException
from job_agent_os.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from job_agent_os.models.user import User
from job_agent_os.schemas.auth import TokenResponse
from job_agent_os.settings import get_settings


class AuthService:
    """Authentication service."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(
        self,
        username: str,
        email: str,
        password: str,
        phone: str | None = None,
    ) -> User:
        """Register a new user."""
        # Check if email already exists
        result = await self.db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise ConflictException(
                message="Email already registered",
                code=ErrorCode.USER_ALREADY_EXISTS,
            )

        # Check if username already exists
        result = await self.db.execute(select(User).where(User.username == username))
        if result.scalar_one_or_none():
            raise ConflictException(
                message="Username already taken",
                code=ErrorCode.USER_ALREADY_EXISTS,
            )

        # Create new user
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            phone=phone,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def login(self, email: str, password: str) -> tuple[User, TokenResponse]:
        """Login user and return tokens."""
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.password_hash):
            raise UnauthorizedException(
                message="Invalid email or password",
                code=ErrorCode.INVALID_CREDENTIALS,
            )

        if user.status != "active":
            raise UnauthorizedException(
                message="Account is not active",
                code=ErrorCode.PERMISSION_DENIED,
            )

        # Update last login
        user.last_login_at = datetime.now(UTC)

        # Generate tokens
        token_response = self._generate_tokens(user)
        return user, token_response

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Refresh access token using refresh token."""
        payload = decode_token(refresh_token)

        if payload.get("type") != "refresh":
            raise UnauthorizedException(
                message="Invalid refresh token",
                code=ErrorCode.TOKEN_INVALID,
            )

        user_id = payload.get("sub")
        if not user_id:
            raise UnauthorizedException(
                message="Invalid token",
                code=ErrorCode.TOKEN_INVALID,
            )

        result = await self.db.execute(select(User).where(User.id == UUID(user_id)))
        user = result.scalar_one_or_none()

        if not user:
            raise UnauthorizedException(
                message="User not found",
                code=ErrorCode.TOKEN_INVALID,
            )

        return self._generate_tokens(user)

    def _generate_tokens(self, user: User) -> TokenResponse:
        """Generate access and refresh tokens for user."""
        settings = get_settings()
        token_data = {"sub": str(user.id)}

        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        return TokenResponse(
            user_id=str(user.id),
            username=user.username,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )
