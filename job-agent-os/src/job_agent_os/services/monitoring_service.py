"""Monitoring service."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.models.agent_log import AgentLog
from job_agent_os.models.user import User


class MonitoringService:
    """Monitoring service for system health and token usage."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_token_usage(self, user: User, days: int = 7) -> dict:
        """Get token usage statistics with date filtering.

        Args:
            user: Current user.
            days: Number of days to look back.

        Returns:
            Token usage statistics dictionary.
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)

        # Get total token usage from agent_logs
        result = await self.db.execute(
            select(
                func.sum(AgentLog.total_tokens).label("total_tokens"),
                func.sum(AgentLog.cost_usd).label("total_cost"),
            )
            .where(AgentLog.user_id == user.id)
            .where(AgentLog.created_at >= cutoff)
        )
        row = result.one_or_none()

        total_tokens = int(row.total_tokens) if row and row.total_tokens else 0
        total_cost = float(row.total_cost) if row and row.total_cost else 0.0

        # Get by agent breakdown
        agent_result = await self.db.execute(
            select(
                AgentLog.agent_name,
                func.sum(AgentLog.total_tokens).label("tokens"),
                func.sum(AgentLog.cost_usd).label("cost"),
            )
            .where(AgentLog.user_id == user.id)
            .where(AgentLog.created_at >= cutoff)
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

        return {
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "by_day": [],
            "by_agent": by_agent,
            "budget_remaining": max(budget_remaining, 0),
        }
