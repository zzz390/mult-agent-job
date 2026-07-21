"""V1 router registration."""

from fastapi import APIRouter

from job_agent_os.api.v1 import (
    applications,
    approvals,
    auth,
    evaluations,
    interview,
    jobs,
    memory,
    monitoring,
    prompts,
    resumes,
    sessions,
    users,
)

api_router = APIRouter(prefix="/v1")

# Register all routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(resumes.router, prefix="/resumes", tags=["Resumes"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
api_router.include_router(applications.router, prefix="/applications", tags=["Applications"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["Sessions"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["Approvals"])
api_router.include_router(interview.router, prefix="/interview", tags=["Interview"])
api_router.include_router(memory.router, prefix="/memory", tags=["Memory"])
api_router.include_router(evaluations.router, prefix="/evaluations", tags=["Evaluations"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["Monitoring"])
api_router.include_router(prompts.router, prefix="/prompts", tags=["Prompts"])
"""V1 router registration."""
