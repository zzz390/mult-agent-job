"""Evaluation service."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.models.evaluation import Evaluation
from job_agent_os.models.user import User


class EvaluationService:
    """Evaluation service for managing evaluation reports."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_report(
        self,
        user: User,
        days: int = 30,
        agent: str | None = None,
    ) -> dict:
        """Get evaluation report with date filtering.

        Args:
            user: Current user.
            days: Number of days to look back.
            agent: Optional agent name filter.

        Returns:
            Report dictionary with summary and by_agent breakdown.
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)

        # Build query
        query = select(
            Evaluation.agent_name,
            Evaluation.metric_name,
            func.avg(Evaluation.score).label("avg_score"),
            func.count(Evaluation.id).label("count"),
        ).where(Evaluation.created_at >= cutoff)

        if agent:
            query = query.where(Evaluation.agent_name == agent)

        query = query.group_by(Evaluation.agent_name, Evaluation.metric_name)

        result = await self.db.execute(query)
        rows = result.all()

        by_agent = [
            {
                "agent": row.agent_name,
                "metric": row.metric_name,
                "avg": round(float(row.avg_score), 4) if row.avg_score else 0.0,
                "trend": None,
            }
            for row in rows
        ]

        # Summary
        total_evals = sum(r.count for r in rows) if rows else 0
        overall_avg = (
            sum(float(r.avg_score) * r.count for r in rows) / total_evals
            if total_evals > 0 and rows
            else 0.0
        )

        return {
            "period": {"days": days},
            "summary": {
                "total_evaluations": total_evals,
                "overall_avg_score": round(overall_avg, 4),
            },
            "by_agent": by_agent,
        }
