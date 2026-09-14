"""Job service."""

import hashlib
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.core.error_codes import ErrorCode
from job_agent_os.core.exceptions import ConflictException, NotFoundException
from job_agent_os.core.utils import utc_now
from job_agent_os.models.job import Job
from job_agent_os.models.user import User
from job_agent_os.schemas.common import PaginationParams
from job_agent_os.schemas.job import ManualJobCreate

# Allowed sort fields for safe dynamic sorting
ALLOWED_SORT_FIELDS = {"created_at", "updated_at", "title", "company", "location", "status", "source_platform", "salary_min", "salary_max", "crawled_at"}


class JobService:
    """Job service for managing job listings."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_jobs(
        self,
        pagination: PaginationParams,
        platform: str | None = None,
        location: str | None = None,
        keyword: str | None = None,
        status: str | None = None,
    ) -> tuple[list[Job], int]:
        """List jobs with pagination and filters."""
        query = select(Job)
        count_query = select(func.count(Job.id))

        # Apply filters
        if platform:
            query = query.where(Job.source_platform == platform)
            count_query = count_query.where(Job.source_platform == platform)
        if location:
            query = query.where(Job.location.ilike(f"%{location}%"))
            count_query = count_query.where(Job.location.ilike(f"%{location}%"))
        if keyword:
            query = query.where(
                Job.title.ilike(f"%{keyword}%") | Job.company.ilike(f"%{keyword}%")
            )
            count_query = count_query.where(
                Job.title.ilike(f"%{keyword}%") | Job.company.ilike(f"%{keyword}%")
            )
        if status:
            query = query.where(Job.status == status)
            count_query = count_query.where(Job.status == status)

        # Get total count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting (whitelist check for security)
        sort_field = pagination.sort_by if pagination.sort_by in ALLOWED_SORT_FIELDS else "created_at"
        sort_column = getattr(Job, sort_field, Job.created_at)
        if pagination.sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        offset = (pagination.page - 1) * pagination.page_size
        query = query.offset(offset).limit(pagination.page_size)

        result = await self.db.execute(query)
        jobs = list(result.scalars().all())

        return jobs, total

    async def get_job(self, job_id: UUID) -> Job:
        """Get job by ID."""
        result = await self.db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise NotFoundException(
                message="Job not found",
                code=ErrorCode.JOB_NOT_FOUND,
            )
        return job

    async def create_manual_job(self, data: ManualJobCreate) -> Job:
        """Create a manually entered job."""
        # Generate content hash for dedup
        content = f"{data.title}:{data.company}:{data.raw_description or ''}"
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Check duplicate
        existing = await self.db.execute(
            select(Job).where(Job.content_hash == content_hash)
        )
        if existing.scalar_one_or_none():
            raise ConflictException(
                message="Duplicate job entry",
            )

        job = Job(
            title=data.title,
            company=data.company,
            company_type=data.company_type,
            location=data.location,
            salary_range=data.salary_range,
            education_required=data.education_required,
            skills_required=data.skills_required,
            raw_description=data.raw_description,
            structured_jd=data.structured_jd,
            deadline=data.deadline,
            source_platform="manual",
            source_url=data.source_url or "",
            content_hash=content_hash,
            status="active",
            crawled_at=utc_now(),
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def trigger_search(
        self, user: User, query_text: str | None, structured_query: dict | None, platforms: list[str] | None
    ) -> UUID:
        """Trigger an async job search via the session/graph system."""
        from job_agent_os.schemas.session import SessionCreate
        from job_agent_os.services.session_service import SessionService

        # Build intent text from structured query if no free-text provided
        intent = query_text or ""
        if not intent and structured_query:
            parts = []
            if structured_query.get("region"):
                parts.extend(structured_query["region"])
            if structured_query.get("company_type"):
                parts.extend(structured_query["company_type"])
            if structured_query.get("direction"):
                parts.append(structured_query["direction"])
            if structured_query.get("skills"):
                parts.extend(structured_query["skills"])
            intent = " ".join(parts) if parts else "搜索岗位"

        session_service = SessionService(self.db)
        session = await session_service.create_session(
            user,
            SessionCreate(
                intent=intent,
                mode="search_only",
                options={
                    "structured_query": structured_query,
                    "platforms": platforms or [],
                },
            ),
        )
        return session.session_id
