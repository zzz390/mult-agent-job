"""Approval service."""

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.core.error_codes import ErrorCode
from job_agent_os.core.exceptions import NotFoundException, ValidationException
from job_agent_os.core.utils import utc_now
from job_agent_os.db.session import get_session_factory
from job_agent_os.models.human_approval import HumanApproval
from job_agent_os.models.user import User
from job_agent_os.schemas.approval import (
    ApprovalRespondRequest,
    BatchApprovalRequest,
)

logger = logging.getLogger(__name__)

# Keep references to background tasks to prevent garbage collection
_background_tasks: set[asyncio.Task] = set()


async def _resume_session_background(session_id: str) -> None:
    """Resume session execution in background with independent DB session.

    Creates its own session via get_session_factory() so the background
    task is not tied to the request-scoped session.
    """
    from job_agent_os.services.session_service import SessionService

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = SessionService(session)
        await service.resume_session(session_id)


class ApprovalService:
    """Approval service for managing human-in-the-loop approvals."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_approvals(
        self,
        user: User,
        status: str | None = None,
        session_id: UUID | None = None,
    ) -> list[HumanApproval]:
        """List approvals for a user."""
        query = select(HumanApproval).where(HumanApproval.user_id == user.id)

        if status:
            query = query.where(HumanApproval.status == status)
        else:
            # Default: show pending first
            query = query.order_by(HumanApproval.requested_at.desc())

        if session_id:
            query = query.where(HumanApproval.session_id == session_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_approval(self, user: User, approval_id: UUID) -> HumanApproval:
        """Get approval by ID."""
        result = await self.db.execute(
            select(HumanApproval).where(
                HumanApproval.id == approval_id,
                HumanApproval.user_id == user.id,
            )
        )
        approval = result.scalar_one_or_none()
        if not approval:
            raise NotFoundException(
                message="Approval not found",
                code=ErrorCode.APPROVAL_NOT_FOUND,
            )
        return approval

    async def respond_to_approval(
        self, user: User, approval_id: UUID, data: ApprovalRespondRequest
    ) -> HumanApproval:
        """Respond to an approval request."""
        approval = await self.get_approval(user, approval_id)

        if approval.status != "pending":
            raise ValidationException(
                message="Approval has already been processed",
                code=ErrorCode.APPROVAL_ALREADY_PROCESSED,
            )

        # Update approval
        approval.status = "responded"
        approval.action = data.action
        approval.feedback = data.feedback
        approval.modified_payload = data.modified_payload
        approval.responded_at = utc_now()

        await self.db.flush()
        await self.db.refresh(approval)

        # Resume the LangGraph execution with the user's decision
        await self._resume_graph(approval, data)

        return approval

    async def _resume_graph(
        self, approval: HumanApproval, data: ApprovalRespondRequest
    ) -> None:
        """Inject user decision into graph state and resume execution."""
        from job_agent_os.graph.main_graph import get_main_graph

        session_id = str(approval.session_id)

        try:
            graph = get_main_graph()
            config = {"configurable": {"thread_id": session_id}}

            # Build state update based on approval type and user action
            state_update: dict = {"pending_approval": None}

            if approval.approval_type == "resume_approval":
                state_update["resume_approved"] = data.action == "approve"
                state_update["human_feedback"] = data.action
            elif approval.approval_type == "recommendation_review":
                state_update["human_feedback"] = data.action
                if data.action == "reject":
                    state_update["human_feedback"] = "reject - re-match"
            else:
                state_update["human_feedback"] = data.action

            # Update graph checkpoint state with user's decision
            await graph.aupdate_state(config, state_update)

            # Resume execution in background with independent DB session
            task = asyncio.create_task(_resume_session_background(session_id))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
        except Exception:
            logger.exception("Failed to resume session after approval")

    async def batch_respond(
        self, user: User, data: BatchApprovalRequest
    ) -> list[dict]:
        """Batch respond to multiple approvals."""
        results = []
        for item in data.approvals:
            try:
                approval = await self.respond_to_approval(
                    user,
                    item.approval_id,
                    ApprovalRespondRequest(
                        action=item.action,
                        feedback=item.feedback,
                    ),
                )
                results.append(
                    {
                        "approval_id": str(approval.id),
                        "status": "success",
                        "action": approval.action,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "approval_id": str(item.approval_id),
                        "status": "error",
                        "error": str(e),
                    }
                )
        return results
