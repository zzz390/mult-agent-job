"""Redis connection pool."""

import redis.asyncio as aioredis

from job_agent_os.settings import get_settings

# Global Redis connection pool
_redis_pool: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Get or create Redis connection."""
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            decode_responses=True,
        )
    return _redis_pool


async def init_redis() -> None:
    """Initialize Redis connection."""
    redis = get_redis()
    await redis.ping()


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
