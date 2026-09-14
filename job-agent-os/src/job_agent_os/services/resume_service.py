"""Resume service (issue #10).

Previously a 22-byte stub — ResumeAgent/match/interview had no access to
the user's real resume. This implements:
- get_user_resume: load the active resume as a UserProfile dict
- create_resume / update_resume: persist new resume versions
- index_resume_to_rag: vectorize the resume for semantic retrieval
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.models.resume import Resume

logger = logging.getLogger(__name__)


class ResumeService:
    """Service for resume persistence and retrieval."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_user_resume(
        self, user_id: UUID, resume_id: UUID | None = None
    ) -> dict | None:
        """Get the user's latest active resume as a UserProfile dict.

        Returns None when the user has no resume yet.
        """
        query = select(Resume).where(Resume.user_id == user_id)
        if resume_id is not None:  # noqa: SIM108 - clearer query construction
            query = query.where(Resume.id == resume_id)
        else:
            query = query.where(Resume.is_active == True)  # noqa: E712
        result = await self.db.execute(query.order_by(Resume.updated_at.desc()).limit(1))
        resume = result.scalar_one_or_none()
        if not resume:
            return None

        structured = resume.structured_data or {}
        return {
            "resume_id": str(resume.id),
            "title": resume.title,
            "target_direction": resume.target_direction,
            # Structured sections (best-effort, may be empty)
            "skills": structured.get("skills", []),
            "education": structured.get("education"),
            "experience_years": structured.get("experience_years"),
            "experience": structured.get("experience", []),
            "projects": structured.get("projects", []),
            "internships": structured.get("internships", []),
            "preferred_locations": structured.get("preferred_locations", []),
            "preferred_company_types": structured.get("preferred_company_types", []),
            "raw_text": resume.raw_content or "",
        }

    async def create_resume(
        self,
        user_id: UUID,
        title: str,
        raw_content: str = "",
        structured_data: dict | None = None,
        target_direction: str | None = None,
        file_type: str | None = None,
        file_size_bytes: int | None = None,
    ) -> Resume:
        """Create a new resume version (deactivates previous versions)."""
        # Deactivate older versions so get_user_resume always sees one row
        existing = await self.db.execute(
            select(Resume).where(
                Resume.user_id == user_id,
                Resume.is_active == True,  # noqa: E712
            )
        )
        for old in existing.scalars().all():
            old.is_active = False

        resume = Resume(
            user_id=user_id,
            title=title,
            raw_content=raw_content,
            structured_data=structured_data or {},
            target_direction=target_direction,
            file_type=file_type,
            file_size_bytes=file_size_bytes,
            is_active=True,
            is_encrypted=False,
        )
        self.db.add(resume)
        await self.db.flush()
        await self.db.refresh(resume)
        return resume

    async def get_resume_by_id(self, user_id: UUID, resume_id: UUID) -> Resume | None:
        """Get a specific resume owned by the user."""
        result = await self.db.execute(
            select(Resume).where(
                Resume.id == resume_id,
                Resume.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def index_resume_to_rag(self, user_id: UUID, profile: dict) -> list[str]:
        """Vectorize the resume into the RAG store for semantic retrieval.

        Best-effort: embedding failures return [] instead of raising.
        """
        try:
            from job_agent_os.memory.rag import RAGPipeline

            pipeline = RAGPipeline(self.db)
            doc_ids = await pipeline.index_resume(profile, user_id)
            await self.db.flush()
            return doc_ids
        except Exception as e:  # noqa: BLE001
            logger.warning("Resume RAG indexing failed for user %s: %s", user_id, e)
            return []
