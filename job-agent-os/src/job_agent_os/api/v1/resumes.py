"""Resume endpoints."""

from fastapi import APIRouter, UploadFile, File, Form, status
from uuid import UUID

from job_agent_os.api.deps import CurrentUser, DBSession, Pagination
from job_agent_os.api.response import success_response, paginated_response
from job_agent_os.schemas.resume import ResumeResponse, ResumeUpdate

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    title: str = Form(...),
    target_direction: str | None = Form(None),
    *,
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Upload a new resume."""
    from job_agent_os.models.resume import Resume

    # Read file content
    content = await file.read()

    # Create resume record
    resume = Resume(
        user_id=user.id,
        title=title,
        target_direction=target_direction,
        file_type=file.content_type,
        file_size_bytes=len(content),
        raw_content=content.decode("utf-8", errors="ignore") if file.content_type in ["text/markdown", "text/plain"] else None,
    )
    db.add(resume)
    await db.flush()
    await db.refresh(resume)

    return success_response(data=ResumeResponse.model_validate(resume).model_dump())


@router.get("")
async def list_resumes(
    user: CurrentUser,
    db: DBSession,
    pagination: Pagination,
) -> dict:
    """List user's resumes."""
    from sqlalchemy import select, func
    from job_agent_os.models.resume import Resume

    # Count total
    count_query = select(func.count()).select_from(Resume).where(Resume.user_id == user.id)
    total = (await db.execute(count_query)).scalar() or 0

    # Get items
    query = (
        select(Resume)
        .where(Resume.user_id == user.id)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    )
    result = await db.execute(query)
    resumes = result.scalars().all()

    items = [ResumeResponse.model_validate(r).model_dump() for r in resumes]
    return paginated_response(items, total, pagination.page, pagination.page_size)


@router.get("/{resume_id}")
async def get_resume(
    resume_id: UUID,
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Get resume details."""
    from sqlalchemy import select
    from job_agent_os.models.resume import Resume
    from job_agent_os.core.exceptions import NotFoundException

    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise NotFoundException(message="Resume not found")

    return success_response(data=ResumeResponse.model_validate(resume).model_dump())


@router.patch("/{resume_id}")
async def update_resume(
    resume_id: UUID,
    request: ResumeUpdate,
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Update resume."""
    from sqlalchemy import select
    from job_agent_os.models.resume import Resume
    from job_agent_os.core.exceptions import NotFoundException

    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise NotFoundException(message="Resume not found")

    update_data = request.model_dump(exclude_unset=True)

    # Handle is_active - deactivate other resumes
    if update_data.get("is_active"):
        # Deactivate all other resumes for this user
        from sqlalchemy import update
        await db.execute(
            update(Resume)
            .where(Resume.user_id == user.id, Resume.id != resume_id)
            .values(is_active=False)
        )

    for key, value in update_data.items():
        setattr(resume, key, value)

    await db.flush()
    await db.refresh(resume)
    return success_response(data=ResumeResponse.model_validate(resume).model_dump())


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(
    resume_id: UUID,
    user: CurrentUser,
    db: DBSession,
) -> None:
    """Delete resume."""
    from sqlalchemy import select
    from job_agent_os.models.resume import Resume
    from job_agent_os.core.exceptions import NotFoundException

    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise NotFoundException(message="Resume not found")

    await db.delete(resume)

