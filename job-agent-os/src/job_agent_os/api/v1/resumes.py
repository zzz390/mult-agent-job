"""Resume upload and version-management endpoints."""

from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile, status
from sqlalchemy import func, select, update

from job_agent_os.api.deps import CurrentUser, DBSession, Pagination
from job_agent_os.api.response import paginated_response, success_response
from job_agent_os.core.error_codes import ErrorCode
from job_agent_os.core.exceptions import NotFoundException, ValidationException
from job_agent_os.models.resume import Resume
from job_agent_os.schemas.resume import ResumeResponse, ResumeUpdate
from job_agent_os.services.resume_service import ResumeService
from job_agent_os.settings import get_settings

router = APIRouter()

_ALLOWED_TYPES = {
    "text/plain": "text",
    "text/markdown": "text",
    "application/pdf": "pdf",
}


def _extract_resume_text(content: bytes, kind: str) -> str:
    if kind == "text":
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationException(
                message="Text resumes must use UTF-8 encoding",
                code=ErrorCode.RESUME_PARSE_FAILED,
            ) from exc

    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as exc:
        raise ValidationException(
            message="Unable to parse the uploaded PDF",
            code=ErrorCode.RESUME_PARSE_FAILED,
        ) from exc
    if not text:
        raise ValidationException(
            message="The PDF contains no extractable text",
            code=ErrorCode.RESUME_PARSE_FAILED,
        )
    return text


def _basic_structure(raw_text: str) -> dict:
    """Extract a conservative skill list without inventing resume facts."""
    skills = [
        "Python", "Java", "Go", "C++", "JavaScript", "TypeScript",
        "React", "Vue", "FastAPI", "Django", "Spring", "PostgreSQL",
        "MySQL", "Redis", "Docker", "Kubernetes", "Linux", "机器学习",
        "深度学习", "NLP",
    ]
    lowered = raw_text.lower()
    return {"skills": [skill for skill in skills if skill.lower() in lowered]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    target_direction: Annotated[str | None, Form()] = None,
    *,
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Upload a bounded UTF-8 text/Markdown or text-based PDF resume."""
    settings = get_settings()
    content_type = (file.content_type or "").lower()
    kind = _ALLOWED_TYPES.get(content_type)
    extension = Path(file.filename or "").suffix.lower()
    if kind is None or extension not in {".txt", ".md", ".pdf"}:
        raise ValidationException(
            message="Only .txt, .md, and text-based .pdf resumes are supported",
            code=ErrorCode.INVALID_FILE_FORMAT,
        )

    content = await file.read(settings.max_resume_upload_bytes + 1)
    if len(content) > settings.max_resume_upload_bytes:
        raise ValidationException(
            message="Resume file exceeds the 10 MiB upload limit",
            code=ErrorCode.FILE_SIZE_EXCEEDED,
        )

    raw_text = _extract_resume_text(content, kind)
    resume = await ResumeService(db).create_resume(
        user_id=user.id,
        title=title,
        raw_content=raw_text,
        structured_data=_basic_structure(raw_text),
        target_direction=target_direction,
        file_type=content_type,
        file_size_bytes=len(content),
    )
    return success_response(
        data=ResumeResponse.model_validate(resume).model_dump(mode="json")
    )


@router.get("")
async def list_resumes(
    user: CurrentUser,
    db: DBSession,
    pagination: Pagination,
) -> dict:
    """List the current user's resume versions."""
    count_query = select(func.count()).select_from(Resume).where(Resume.user_id == user.id)
    total = (await db.execute(count_query)).scalar() or 0
    query = (
        select(Resume)
        .where(Resume.user_id == user.id)
        .order_by(Resume.updated_at.desc())
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    )
    resumes = (await db.execute(query)).scalars().all()
    items = [
        ResumeResponse.model_validate(item).model_dump(mode="json")
        for item in resumes
    ]
    return paginated_response(items, total, pagination.page, pagination.page_size)


@router.get("/{resume_id}")
async def get_resume(resume_id: UUID, user: CurrentUser, db: DBSession) -> dict:
    """Get a resume owned by the current user."""
    resume = await ResumeService(db).get_resume_by_id(user.id, resume_id)
    if not resume:
        raise NotFoundException(
            message="Resume not found", code=ErrorCode.RESUME_NOT_FOUND
        )
    return success_response(
        data=ResumeResponse.model_validate(resume).model_dump(mode="json")
    )


@router.patch("/{resume_id}")
async def update_resume(
    resume_id: UUID,
    request: ResumeUpdate,
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Update a resume owned by the current user."""
    resume = await ResumeService(db).get_resume_by_id(user.id, resume_id)
    if not resume:
        raise NotFoundException(
            message="Resume not found", code=ErrorCode.RESUME_NOT_FOUND
        )
    update_data = request.model_dump(exclude_unset=True)
    if update_data.get("is_active"):
        await db.execute(
            update(Resume)
            .where(Resume.user_id == user.id, Resume.id != resume_id)
            .values(is_active=False)
        )
    for key, value in update_data.items():
        setattr(resume, key, value)
    await db.flush()
    await db.refresh(resume)
    return success_response(
        data=ResumeResponse.model_validate(resume).model_dump(mode="json")
    )


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(resume_id: UUID, user: CurrentUser, db: DBSession) -> None:
    """Delete a resume owned by the current user."""
    resume = await ResumeService(db).get_resume_by_id(user.id, resume_id)
    if not resume:
        raise NotFoundException(
            message="Resume not found", code=ErrorCode.RESUME_NOT_FOUND
        )
    await db.delete(resume)
