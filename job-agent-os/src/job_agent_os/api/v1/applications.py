"""Applications endpoints."""

from uuid import UUID

from fastapi import APIRouter, Query, status

from job_agent_os.api.deps import CurrentUser, DBSession, Pagination
from job_agent_os.api.response import paginated_response, success_response
from job_agent_os.schemas.application import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationStatusUpdate,
)
from job_agent_os.services.application_service import ApplicationService

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_application(
    request: ApplicationCreate,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Create a new job application."""
    service = ApplicationService(db)
    application = await service.create_application(user, request)
    return success_response(
        data=ApplicationResponse.model_validate(application).model_dump(mode="json")
    )


@router.get("")
async def list_applications(
    db: DBSession,
    user: CurrentUser,
    pagination: Pagination,
    app_status: str | None = Query(default=None, alias="status"),
) -> dict:
    """List applications with pagination."""
    service = ApplicationService(db)
    applications, total = await service.list_applications(
        user=user,
        pagination=pagination,
        status=app_status,
    )
    items = [
        ApplicationResponse.model_validate(a).model_dump(mode="json")
        for a in applications
    ]
    return paginated_response(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/kanban")
async def get_kanban(
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Get kanban board view of applications."""
    service = ApplicationService(db)
    kanban = await service.get_kanban(user)
    return success_response(data=kanban.model_dump(mode="json"))


@router.get("/statistics")
async def get_statistics(
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Get application statistics."""
    service = ApplicationService(db)
    stats = await service.get_statistics(user)
    return success_response(data=stats.model_dump(mode="json"))


@router.get("/{application_id}")
async def get_application(
    application_id: UUID,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Get application details."""
    service = ApplicationService(db)
    application = await service.get_application(user, application_id)
    return success_response(
        data=ApplicationResponse.model_validate(application).model_dump(mode="json")
    )


@router.patch("/{application_id}/status")
async def update_application_status(
    application_id: UUID,
    request: ApplicationStatusUpdate,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Update application status (with state machine validation)."""
    service = ApplicationService(db)
    application = await service.update_status(user, application_id, request)
    return success_response(
        data=ApplicationResponse.model_validate(application).model_dump(mode="json")
    )

