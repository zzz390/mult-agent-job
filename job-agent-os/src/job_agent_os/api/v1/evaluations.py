"""Evaluations endpoints."""

from fastapi import APIRouter, Query

from job_agent_os.api.deps import CurrentUser, DBSession
from job_agent_os.api.response import success_response

router = APIRouter()


@router.get("/report")
async def get_eval_report(
    db: DBSession,
    user: CurrentUser,
    days: int = Query(default=30, ge=1, le=365),
    agent: str | None = Query(default=None),
) -> dict:
    """Get evaluation report."""
    from sqlalchemy import func, select

    from job_agent_os.models.evaluation import Evaluation

    # Build query
    query = select(
        Evaluation.agent_name,
        Evaluation.metric_name,
        func.avg(Evaluation.score).label("avg_score"),
        func.count(Evaluation.id).label("count"),
    )

    if agent:
        query = query.where(Evaluation.agent_name == agent)

    query = query.group_by(Evaluation.agent_name, Evaluation.metric_name)

    result = await db.execute(query)
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

    return success_response(
        data={
            "period": {"days": days},
            "summary": {
                "total_evaluations": total_evals,
                "overall_avg_score": round(overall_avg, 4),
            },
            "by_agent": by_agent,
        }
    )

