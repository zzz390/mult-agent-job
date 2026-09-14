"""Database tools for LLM function-calling.

Provides query and storage tools that agents can call via ReAct tool-calling
to interact with the jobs database.

Note: These tool functions use their own independent database sessions
(via get_session_factory()) rather than the request-scoped session from
FastAPI dependency injection. This is because tool functions are called
from agent execution contexts that do not have access to the request
context. Each tool function manages its own transaction lifecycle.
"""

import hashlib
import logging
from contextlib import suppress
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from job_agent_os.core.utils import utc_now
from job_agent_os.db.session import get_session_factory
from job_agent_os.models.job import Job
from job_agent_os.tools.registry import ToolEntry, _tool_registry

logger = logging.getLogger(__name__)


def _sanitize_input(value: str, max_length: int = 200) -> str:
    """Sanitize LLM tool-call parameters to prevent injection."""
    if not isinstance(value, str):
        return ""
    # Truncate
    value = value[:max_length].strip()
    # Escape LIKE wildcards
    value = value.replace("%", "\\%").replace("_", "\\_")
    return value


# --- Pydantic Schemas ---


class QueryJobsInput(BaseModel):
    """数据库岗位查询工具输入"""

    keyword: str = Field(default="", description="搜索关键词（岗位方向/技能）")
    region: str = Field(default="", description="地区筛选")
    company_type: str = Field(default="", description="企业类型筛选（国企/央企/民企等）")
    limit: int = Field(default=20, description="最大返回数量")


class SaveJobsInput(BaseModel):
    """岗位存储工具输入"""

    jobs: list[dict] = Field(description="要存储的岗位列表，每项需含 title、company 字段")


# --- Tool Functions ---


async def query_jobs_db(
    keyword: str = "", region: str = "", company_type: str = "", limit: int = 20
) -> list[dict]:
    """从数据库查询匹配的岗位。

    根据关键词、地区、企业类型组合条件查询 jobs 表，
    返回符合条件的岗位列表。

    Note: This function uses an independent database session, not the
    request-scoped session. The session is read-only and auto-closed.
    """
    session_factory = get_session_factory()
    async with session_factory() as db:
        conditions = []

        keyword = _sanitize_input(keyword)
        region = _sanitize_input(region)
        company_type = _sanitize_input(company_type)

        if keyword:
            conditions.append(
                or_(
                    Job.title.ilike(f"%{keyword}%"),
                    Job.skills_required.any(keyword),
                )
            )

        if region:
            conditions.append(Job.location.ilike(f"%{region}%"))

        if company_type:
            conditions.append(Job.company_type.ilike(f"%{company_type}%"))

        stmt = select(Job).where(Job.status == "active")
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(Job.created_at.desc()).limit(limit)

        result = await db.execute(stmt)
        jobs = result.scalars().all()

        return [
            {
                "id": str(job.id),
                "title": job.title,
                "company": job.company,
                "company_type": job.company_type,
                "location": job.location,
                "salary": job.salary_range,
                "skills_required": job.skills_required or [],
                "education": job.education_required,
                "source_url": job.source_url,
                "source_platform": job.source_platform,
                "raw_description": job.raw_description or "",
            }
            for job in jobs
        ]


def _has_verifiable_source(job_data: dict) -> bool:
    """Only persist externally-discovered listings with a real HTTP source."""
    parsed = urlparse(str(job_data.get("source_url", "")))
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _job_payload(job: Job) -> dict:
    return {
        "id": str(job.id),
        "title": job.title,
        "company": job.company,
        "company_type": job.company_type,
        "location": job.location,
        "salary": job.salary_range,
        "skills_required": job.skills_required or [],
        "education": job.education_required,
        "source_url": job.source_url,
        "source_platform": job.source_platform,
        "raw_description": job.raw_description or "",
        "content_hash": job.content_hash,
    }


async def _persist_jobs_db(jobs: list[dict]) -> tuple[list[dict], int]:
    """Persist jobs and return ``(canonical records, newly saved count)``."""
    session_factory = get_session_factory()

    # Pre-compute hashes, reject unsourced external records, and de-duplicate
    # within this batch before touching the unique database index.
    candidates: dict[str, dict] = {}
    referenced_ids: set[UUID] = set()
    for job_data in jobs:
        if job_data.get("id"):
            with suppress(TypeError, ValueError):
                referenced_ids.add(UUID(str(job_data["id"])))
            continue
        title = job_data.get("title", "")
        company = job_data.get("company", "")
        if not title or not company or not _has_verifiable_source(job_data):
            continue
        content = f"{title}:{company}:{job_data.get('raw_description', '')}"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        candidates.setdefault(content_hash, job_data)

    if not candidates and not referenced_ids:
        return [], 0

    async with session_factory() as db:
        try:
            # Batch check existing hashes (single query instead of N queries)
            lookup_conditions = []
            if candidates:
                lookup_conditions.append(Job.content_hash.in_(candidates))
            if referenced_ids:
                lookup_conditions.append(Job.id.in_(referenced_ids))
            result = await db.execute(select(Job).where(or_(*lookup_conditions)))
            stored_jobs = list(result.scalars().all())
            existing = {job.content_hash: job for job in stored_jobs}
            canonical = [
                _job_payload(job) for job in stored_jobs if job.id in referenced_ids
            ]
            saved_count = 0

            for content_hash, job_data in candidates.items():
                if content_hash in existing:
                    canonical.append(_job_payload(existing[content_hash]))
                    continue

                job = Job(
                    title=job_data.get("title", ""),
                    company=job_data.get("company", ""),
                    company_type=job_data.get("company_type"),
                    location=job_data.get("location"),
                    salary_range=job_data.get("salary"),
                    education_required=job_data.get("education"),
                    skills_required=job_data.get("skills_required") or [],
                    raw_description=job_data.get("raw_description", ""),
                    source_platform=job_data.get("source_platform") or "web",
                    source_url=job_data["source_url"],
                    content_hash=content_hash,
                    status="active",
                    crawled_at=utc_now(),
                )
                db.add(job)
                await db.flush()
                canonical.append(_job_payload(job))
                saved_count += 1

            await db.commit()
        except Exception:
            await db.rollback()
            raise

    logger.info("persist_jobs_db: returned %s canonical jobs", len(canonical))
    return canonical, saved_count


async def persist_jobs_db(jobs: list[dict]) -> list[dict]:
    """Persist verifiable jobs and return canonical records including UUIDs."""
    canonical, _ = await _persist_jobs_db(jobs)
    return canonical


async def persist_jobs_db_with_count(jobs: list[dict]) -> tuple[list[dict], int]:
    """Persist verifiable jobs and also return the number newly inserted."""
    return await _persist_jobs_db(jobs)


async def save_jobs_db(jobs: list[dict]) -> int:
    """将岗位数据批量存入数据库，自动去重，返回新增数量。"""
    _, saved_count = await _persist_jobs_db(jobs)
    return saved_count


# --- Register tools ---

_tool_registry["query_jobs_db"] = ToolEntry(
    name="query_jobs_db",
    description="从数据库查询匹配的岗位。支持按关键词、地区、企业类型组合筛选。",
    func=query_jobs_db,
    agent_group="common",
    is_async=True,
    args_schema=QueryJobsInput,
)

_tool_registry["save_jobs_db"] = ToolEntry(
    name="save_jobs_db",
    description="将岗位数据批量存入数据库（自动按内容哈希去重），返回新增数量。",
    func=save_jobs_db,
    agent_group="common",
    is_async=True,
    args_schema=SaveJobsInput,
)
