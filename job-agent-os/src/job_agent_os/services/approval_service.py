"""Approval service."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.core.error_codes import ErrorCode
from job_agent_os.core.exceptions import NotFoundException, ValidationException
from job_agent_os.core.utils import utc_now
from job_agent_os.models.human_approval import HumanApproval
from job_agent_os.models.user import User
from job_agent_os.schemas.approval import (
    ApprovalRespondRequest,
    BatchApprovalRequest,
)


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

        # In full implementation, this would resume the LangGraph execution
        # via the checkpointer mechanism
        return approval

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
"""Approval service."""
