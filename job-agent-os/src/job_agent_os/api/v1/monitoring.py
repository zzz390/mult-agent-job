"""Monitoring endpoints."""

from fastapi import APIRouter, Query
from sqlalchemy import text

from job_agent_os.api.deps import CurrentUser, DBSession
from job_agent_os.api.response import success_response
from job_agent_os.core.utils import utc_now
from job_agent_os.db.redis import get_redis
from job_agent_os.db.session import get_engine
from job_agent_os.services.monitoring_service import MonitoringService

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint (no auth required)."""
    checks = {
        "status": "healthy",
        "timestamp": utc_now().isoformat(),
        "services": {},
    }

    # Check database
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["services"]["database"] = "healthy"
    except Exception as e:
        checks["services"]["database"] = f"unhealthy: {str(e)}"
        checks["status"] = "degraded"

    # Check Redis
    try:
        redis = get_redis()
        await redis.ping()
        checks["services"]["redis"] = "healthy"
    except Exception as e:
        checks["services"]["redis"] = f"unhealthy: {str(e)}"
        checks["status"] = "degraded"

    return success_response(data=checks)


@router.get("/token-usage")
async def get_token_usage(
    db: DBSession,
    user: CurrentUser,
    days: int = Query(default=7, ge=1, le=90),
) -> dict:
    """Get token usage statistics."""
    service = MonitoringService(db)
    data = await service.get_token_usage(user=user, days=days)
    return success_response(data=data)
