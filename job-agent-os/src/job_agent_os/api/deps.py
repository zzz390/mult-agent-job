"""Common FastAPI dependencies (auth, db session, pagination)."""

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.core.exceptions import UnauthorizedException
from job_agent_os.core.security import decode_token
from job_agent_os.db.redis import get_redis
from job_agent_os.db.session import get_db_session
from job_agent_os.models.user import User
from job_agent_os.schemas.common import PaginationParams


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency."""
    async for session in get_db_session():
        yield session


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user from JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedException(message="Token not provided")

    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedException(message="Invalid token")

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedException(message="User not found")

    if user.status != "active":
        raise UnauthorizedException(message="User account is not active")

    return user


def get_pagination(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> PaginationParams:
    """Get pagination parameters."""
    return PaginationParams(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# Type aliases for dependencies
DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Pagination = Annotated[PaginationParams, Depends(get_pagination)]
RedisClient = Annotated[object, Depends(get_redis)]
