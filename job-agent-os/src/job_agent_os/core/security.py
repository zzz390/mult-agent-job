"""Security utilities (JWT, password hashing)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import bcrypt
from jose import JWTError, jwt

from job_agent_os.core.exceptions import UnauthorizedException
from job_agent_os.settings import get_settings

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        raise ValueError("Password too long (max 72 bytes)")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > 72:
        raise ValueError("Password too long (max 72 bytes)")
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    settings = get_settings()
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    to_encode.update(
        {"exp": expire, "iat": datetime.now(UTC), "jti": str(uuid4()), "type": "access"}
    )
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(data: dict[str, Any]) -> str:
    """Create a JWT refresh token."""
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode.update(
        {"exp": expire, "iat": datetime.now(UTC), "jti": str(uuid4()), "type": "refresh"}
    )
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as e:
        raise UnauthorizedException(message="Invalid or expired token") from e


async def revoke_token(token: str) -> None:
    """Revoke a JWT until its natural expiration."""
    from job_agent_os.db.redis import get_redis

    payload = decode_token(token)
    jti = payload.get("jti")
    expires_at = payload.get("exp")
    if not jti or not expires_at:
        raise UnauthorizedException(message="Token cannot be revoked")
    ttl = max(1, int(expires_at) - int(datetime.now(UTC).timestamp()))
    await get_redis().setex(f"jwt:revoked:{jti}", ttl, "1")


async def is_token_revoked(payload: dict[str, Any]) -> bool:
    """Check a decoded token against the Redis revocation set."""
    from job_agent_os.db.redis import get_redis

    jti = payload.get("jti")
    if not jti:
        # Tokens issued before rotation support are intentionally invalidated.
        return True
    try:
        return bool(await get_redis().get(f"jwt:revoked:{jti}"))
    except Exception:
        if get_settings().env == "prod":
            raise
        logger.exception("Token revocation check unavailable in non-production")
        return False
