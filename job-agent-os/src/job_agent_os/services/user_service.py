"""User service (issue #10).

Previously a 20-byte stub. Provides user profile assembly for agents:
preferences + job intentions from the users table, merged with the
active resume profile.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.models.user import User

logger = logging.getLogger(__name__)


class UserService:
    """Service for user data access."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_user(self, user_id: UUID) -> User | None:
        """Get a user by ID."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> User | None:
        """Get a user by username."""
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_user_profile(self, user_id: UUID) -> dict | None:
        """Assemble the full user profile used by agents.

        Merges:
        - user.preferences / job_intentions (users table)
        - the active resume profile (resumes table)

        Returns None when the user does not exist.
        """
        user = await self.get_user(user_id)
        if not user:
            return None

        profile: dict = {
            "user_id": str(user.id),
            "username": user.username,
            "preferences": user.preferences or {},
            "job_intentions": user.job_intentions or [],
        }

        try:
            from job_agent_os.services.resume_service import ResumeService

            resume_profile = await ResumeService(self.db).get_user_resume(user_id)
            if resume_profile:
                profile.update(resume_profile)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to attach resume profile for %s: %s", user_id, e)

        return profile
