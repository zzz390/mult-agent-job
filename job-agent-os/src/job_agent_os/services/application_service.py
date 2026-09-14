"""Application service."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.core.error_codes import ErrorCode
from job_agent_os.core.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from job_agent_os.core.utils import utc_now
from job_agent_os.models.application import Application
from job_agent_os.models.job import Job
from job_agent_os.models.resume import Resume
from job_agent_os.models.user import User
from job_agent_os.schemas.application import (
    ApplicationCreate,
    ApplicationStatistics,
    ApplicationStatusUpdate,
    KanbanView,
)
from job_agent_os.schemas.common import PaginationParams

# Allowed sort fields for safe dynamic sorting
ALLOWED_SORT_FIELDS = {"created_at", "updated_at", "status", "priority", "applied_at", "match_score"}

# Valid user-driven state transitions. Besides normal forward progress, allow
# one-step corrections and explicit reactivation of a rejected application.
# Arbitrary jumps (for example pending -> offer) remain invalid.
VALID_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["applied", "rejected"],
    "applied": ["pending", "written_test", "round1", "rejected"],
    "written_test": ["applied", "round1", "rejected"],
    "round1": ["applied", "written_test", "round2", "hr_interview", "offer", "rejected"],
    "round2": ["round1", "hr_interview", "offer", "rejected"],
    "hr_interview": ["round1", "round2", "offer", "rejected"],
    "offer": ["hr_interview", "rejected"],
    "rejected": ["pending"],
}

# All valid statuses
ALL_STATUSES = list(VALID_TRANSITIONS.keys())


class ApplicationService:
    """Application service for managing job applications."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_application(
        self, user: User, data: ApplicationCreate
    ) -> Application:
        """Create a new application."""
        resume_result = await self.db.execute(
            select(Resume.id).where(
                Resume.id == data.resume_id,
                Resume.user_id == user.id,
            )
        )
        if resume_result.scalar_one_or_none() is None:
            raise NotFoundException(
                message="Resume not found", code=ErrorCode.RESUME_NOT_FOUND
            )

        job_result = await self.db.execute(select(Job.id).where(Job.id == data.job_id))
        if job_result.scalar_one_or_none() is None:
            raise NotFoundException(message="Job not found", code=ErrorCode.JOB_NOT_FOUND)

        # Check for duplicate
        existing = await self.db.execute(
            select(Application).where(
                Application.user_id == user.id,
                Application.job_id == data.job_id,
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictException(
                message="Application already exists for this job",
                code=ErrorCode.DUPLICATE_APPLICATION,
            )

        application = Application(
            user_id=user.id,
            job_id=data.job_id,
            resume_id=data.resume_id,
            priority=data.priority,
            notes=data.notes,
            status="pending",
            stage="none",
            status_history=[
                {"status": "pending", "timestamp": utc_now().isoformat()}
            ],
        )
        self.db.add(application)
        await self.db.flush()
        await self.db.refresh(application)
        return application

    async def list_applications(
        self,
        user: User,
        pagination: PaginationParams,
        status: str | None = None,
    ) -> tuple[list[Application], int]:
        """List applications with pagination."""
        query = select(Application).where(Application.user_id == user.id)
        count_query = select(func.count(Application.id)).where(
            Application.user_id == user.id
        )

        if status:
            query = query.where(Application.status == status)
            count_query = count_query.where(Application.status == status)

        # Get total
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Sorting (whitelist check for security)
        sort_field = pagination.sort_by if pagination.sort_by in ALLOWED_SORT_FIELDS else "created_at"
        sort_column = getattr(Application, sort_field, Application.created_at)
        if pagination.sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Pagination
        offset = (pagination.page - 1) * pagination.page_size
        query = query.offset(offset).limit(pagination.page_size)

        result = await self.db.execute(query)
        applications = list(result.scalars().all())

        return applications, total

    async def get_application(self, user: User, application_id: UUID) -> Application:
        """Get application by ID."""
        result = await self.db.execute(
            select(Application).where(
                Application.id == application_id,
                Application.user_id == user.id,
            )
        )
        application = result.scalar_one_or_none()
        if not application:
            raise NotFoundException(
                message="Application not found",
                code=ErrorCode.APPLICATION_NOT_FOUND,
            )
        return application

    async def update_status(
        self, user: User, application_id: UUID, data: ApplicationStatusUpdate
    ) -> Application:
        """Update application status with state machine validation."""
        application = await self.get_application(user, application_id)

        current_status = application.status
        new_status = data.status

        # Validate state transition
        valid_next = VALID_TRANSITIONS.get(current_status, [])
        if new_status not in valid_next:
            raise ValidationException(
                message=f"Invalid status transition: {current_status} -> {new_status}. "
                f"Valid transitions: {valid_next}",
                code=ErrorCode.INVALID_STATUS_TRANSITION,
            )

        # Update status
        application.status = new_status
        if data.stage:
            application.stage = data.stage
        if data.notes:
            application.notes = data.notes
        if data.next_follow_up:
            application.next_follow_up = data.next_follow_up

        application.last_status_change = utc_now()

        # Append to status history
        history = list(application.status_history or [])
        history.append(
            {
                "from_status": current_status,
                "status": new_status,
                "timestamp": utc_now().isoformat(),
                "notes": data.notes,
                "source": "manual",
            }
        )
        application.status_history = history

        await self.db.flush()
        await self.db.refresh(application)
        return application

    async def get_kanban(self, user: User) -> KanbanView:
        """Get kanban board view of applications."""
        result = await self.db.execute(
            select(Application).where(Application.user_id == user.id)
        )
        applications = list(result.scalars().all())

        kanban = KanbanView()
        status_map = {
            "pending": kanban.pending,
            "applied": kanban.applied,
            "written_test": kanban.written_test,
            "round1": kanban.round1,
            "round2": kanban.round2,
            "hr_interview": kanban.hr_interview,
            "offer": kanban.offer,
            "rejected": kanban.rejected,
        }

        for app in applications:
            bucket = status_map.get(app.status)
            if bucket is not None:
                from job_agent_os.schemas.application import ApplicationResponse

                bucket.append(ApplicationResponse.model_validate(app))

        # Statistics
        total = len(applications)
        kanban.statistics = {
            "total": total,
            "offer_count": len(kanban.offer),
            "in_progress": total - len(kanban.rejected) - len(kanban.offer),
            "rejected_count": len(kanban.rejected),
        }

        return kanban

    async def get_statistics(self, user: User) -> ApplicationStatistics:
        """Get application statistics."""
        result = await self.db.execute(
            select(Application).where(Application.user_id == user.id)
        )
        applications = list(result.scalars().all())

        total = len(applications)
        by_status: dict[str, int] = {}
        scores: list[float] = []

        for app in applications:
            by_status[app.status] = by_status.get(app.status, 0) + 1
            if app.match_score is not None:
                scores.append(app.match_score)

        offer_count = by_status.get("offer", 0)
        finished = offer_count + by_status.get("rejected", 0)
        pass_rate = (offer_count / finished * 100) if finished > 0 else 0.0
        avg_score = sum(scores) / len(scores) if scores else 0.0

        return ApplicationStatistics(
            total_applications=total,
            by_status=by_status,
            by_platform={},
            pass_rate=round(pass_rate, 2),
            avg_match_score=round(avg_score, 2),
            stage_conversion={},
        )
