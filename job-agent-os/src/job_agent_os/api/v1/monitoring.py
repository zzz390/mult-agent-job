"""Monitoring endpoints."""

from fastapi import APIRouter, Query
from sqlalchemy import text

from job_agent_os.api.deps import CurrentUser, DBSession
from job_agent_os.api.response import success_response
from job_agent_os.core.utils import utc_now
from job_agent_os.db.redis import get_redis
from job_agent_os.db.session import get_engine

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
    from sqlalchemy import func, select

    from job_agent_os.models.agent_log import AgentLog

    # Get total token usage from agent_logs
    result = await db.execute(
        select(
            func.sum(AgentLog.total_tokens).label("total_tokens"),
            func.sum(AgentLog.cost_usd).label("total_cost"),
        ).where(AgentLog.user_id == user.id)
    )
    row = result.one_or_none()

    total_tokens = int(row.total_tokens) if row and row.total_tokens else 0
    total_cost = float(row.total_cost) if row and row.total_cost else 0.0

    # Get by agent breakdown
    agent_result = await db.execute(
        select(
            AgentLog.agent_name,
            func.sum(AgentLog.total_tokens).label("tokens"),
            func.sum(AgentLog.cost_usd).label("cost"),
        )
        .where(AgentLog.user_id == user.id)
        .group_by(AgentLog.agent_name)
    )
    by_agent = [
        {
            "agent": row.agent_name,
            "tokens": int(row.tokens or 0),
            "cost_usd": float(row.cost or 0.0),
        }
        for row in agent_result.all()
    ]

    budget_remaining = user.token_budget_daily - user.token_used_today

    return success_response(
        data={
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "by_day": [],
            "by_agent": by_agent,
            "budget_remaining": max(budget_remaining, 0),
        }
    )

