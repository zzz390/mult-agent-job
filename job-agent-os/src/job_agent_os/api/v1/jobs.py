"""Jobs endpoints."""

from uuid import UUID

from fastapi import APIRouter, Query, status

from job_agent_os.api.deps import CurrentUser, DBSession, Pagination
from job_agent_os.api.response import paginated_response, success_response
from job_agent_os.schemas.job import (
    JobResponse,
    JobSearchRequest,
    ManualJobCreate,
)
from job_agent_os.services.job_service import JobService

router = APIRouter()


@router.post("/search", status_code=status.HTTP_202_ACCEPTED)
async def trigger_job_search(
    request: JobSearchRequest,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Trigger an async job search. Returns session_id for polling."""
    service = JobService(db)
    structured = request.structured_query.model_dump() if request.structured_query else None
    session_id = await service.trigger_search(
        user=user,
        query_text=request.query_text,
        structured_query=structured,
        platforms=request.platforms,
    )
    return success_response(
        data={"session_id": str(session_id)},
        message="Search task accepted",
    )


@router.get("")
async def list_jobs(
    db: DBSession,
    user: CurrentUser,
    pagination: Pagination,
    platform: str | None = Query(default=None),
    location: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    job_status: str | None = Query(default=None, alias="status"),
) -> dict:
    """List jobs with pagination and filters."""
    service = JobService(db)
    jobs, total = await service.list_jobs(
        pagination=pagination,
        platform=platform,
        location=location,
        keyword=keyword,
        status=job_status,
    )
    items = [JobResponse.model_validate(j).model_dump(mode="json") for j in jobs]
    return paginated_response(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{job_id}")
async def get_job(
    job_id: UUID,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Get job details by ID."""
    service = JobService(db)
    job = await service.get_job(job_id)
    return success_response(data=JobResponse.model_validate(job).model_dump(mode="json"))


@router.post("/manual", status_code=status.HTTP_201_CREATED)
async def create_manual_job(
    request: ManualJobCreate,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Manually create a job entry."""
    service = JobService(db)
    job = await service.create_manual_job(request)
    return success_response(data=JobResponse.model_validate(job).model_dump(mode="json"))

