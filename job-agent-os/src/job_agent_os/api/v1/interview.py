"""Interview question generation endpoints."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, status
from sqlalchemy import select

from job_agent_os.api.deps import CurrentUser, DBSession
from job_agent_os.api.response import success_response
from job_agent_os.core.error_codes import ErrorCode
from job_agent_os.core.exceptions import NotFoundException
from job_agent_os.core.privacy import redact_pii
from job_agent_os.core.utils import generate_uuid_obj, utc_now
from job_agent_os.models.job import Job
from job_agent_os.models.resume import Resume
from job_agent_os.schemas.interview import QuestionGenerateRequest
from job_agent_os.tools.interview.behavior_question_gen import (
    generate_behavior_questions,
)
from job_agent_os.tools.interview.tech_question_gen import generate_tech_questions

router = APIRouter()

_generation_tasks: dict[str, dict] = {}
_background_tasks: set[asyncio.Task] = set()
_TASK_TTL_MINUTES = 30


def _cleanup_expired_tasks() -> None:
    now = datetime.now(UTC)
    for task_id, task in list(_generation_tasks.items()):
        if task.get("status") not in ("completed", "failed"):
            continue
        try:
            created_at = datetime.fromisoformat(task["created_at"])
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            if now - created_at > timedelta(minutes=_TASK_TTL_MINUTES):
                _generation_tasks.pop(task_id, None)
        except (KeyError, TypeError, ValueError):
            _generation_tasks.pop(task_id, None)


@router.post("/questions", status_code=status.HTTP_202_ACCEPTED)
async def generate_questions(
    request: QuestionGenerateRequest,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Generate questions from an existing job and an owned resume."""
    job = (
        await db.execute(select(Job).where(Job.id == request.job_id))
    ).scalar_one_or_none()
    if not job:
        raise NotFoundException(message="Job not found", code=ErrorCode.JOB_NOT_FOUND)

    resume_text = ""
    if request.resume_id:
        resume = (
            await db.execute(
                select(Resume).where(
                    Resume.id == request.resume_id,
                    Resume.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if not resume:
            raise NotFoundException(
                message="Resume not found", code=ErrorCode.RESUME_NOT_FOUND
            )
        resume_text = redact_pii(resume.raw_content or json.dumps(
            resume.structured_data or {}, ensure_ascii=False
        ))

    task_id = str(generate_uuid_obj())
    _generation_tasks[task_id] = {
        "task_id": task_id,
        "user_id": str(user.id),
        "status": "processing",
        "created_at": utc_now().isoformat(),
        "result": None,
        "error": None,
    }
    task = asyncio.create_task(
        _generate_questions_background(
            task_id=task_id,
            request=request,
            job_title=job.title,
            skills=job.skills_required or [],
            resume_text=resume_text,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return success_response(
        data={"task_id": task_id, "status": "processing"},
        message="Question generation started",
    )


@router.get("/questions/{task_id}")
async def get_generation_result(
    task_id: str,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Get a question task owned by the current user."""
    _cleanup_expired_tasks()
    task = _generation_tasks.get(task_id)
    if not task or task.get("user_id") != str(user.id):
        raise NotFoundException(
            message="Task not found", code=ErrorCode.RESOURCE_NOT_FOUND
        )
    return success_response(
        data={
            "task_id": task_id,
            "status": task["status"],
            "result": task["result"],
            "error": task["error"],
        }
    )


async def _generate_questions_background(
    task_id: str,
    request: QuestionGenerateRequest,
    job_title: str,
    skills: list[str],
    resume_text: str,
) -> None:
    """Run the real generators and retain a bounded asynchronous result."""
    try:
        wants_technical = "technical" in request.question_types
        wants_behavioral = "behavioral" in request.question_types
        if wants_technical and wants_behavioral:
            technical_count = (request.count + 1) // 2
            behavioral_count = request.count - technical_count
        elif wants_technical:
            technical_count, behavioral_count = request.count, 0
        elif wants_behavioral:
            technical_count, behavioral_count = 0, request.count
        else:
            technical_count, behavioral_count = 0, 0
        calls = []
        if "technical" in request.question_types and technical_count:
            calls.append(
                generate_tech_questions(
                    job_title, skills, request.difficulty, technical_count
                )
            )
        if "behavioral" in request.question_types and behavioral_count:
            calls.append(
                generate_behavior_questions(resume_text, job_title, behavioral_count)
            )

        generated = await asyncio.gather(*calls) if calls else []
        questions = [item for group in generated for item in group]
        questions = [{**question, "id": index} for index, question in enumerate(questions[: request.count], 1)]
        _generation_tasks[task_id]["status"] = "completed"
        _generation_tasks[task_id]["result"] = {
            "status": "completed",
            "job_title": job_title,
            "questions": questions,
        }
    except Exception as exc:  # noqa: BLE001
        _generation_tasks[task_id]["status"] = "failed"
        _generation_tasks[task_id]["error"] = str(exc)
