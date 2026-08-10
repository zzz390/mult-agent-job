"""Evaluations endpoints."""

from fastapi import APIRouter, Query

from job_agent_os.api.deps import CurrentUser, DBSession
from job_agent_os.api.response import success_response
from job_agent_os.services.evaluation_service import EvaluationService

router = APIRouter()


@router.get("/report")
async def get_eval_report(
    db: DBSession,
    user: CurrentUser,
    days: int = Query(default=30, ge=1, le=365),
    agent: str | None = Query(default=None),
) -> dict:
    """Get evaluation report."""
    service = EvaluationService(db)
    data = await service.get_report(user=user, days=days, agent=agent)
    return success_response(data=data)
