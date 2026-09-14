"""Human-in-the-Loop gateway.

Manages approval requests for LangGraph interrupt mechanism:
- create_approval_request()
- process_approval_response()
- check_timeout()
- Integration with LangGraph interrupt_before
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.models.human_approval import HumanApproval


class HITLGateway:
    """Human-in-the-Loop Gateway.

    Manages the lifecycle of approval requests:
    1. Create approval request (triggers LangGraph interrupt)
    2. Wait for user response
    3. Process response and resume graph
    4. Handle timeouts with auto-action
    """

    DEFAULT_TIMEOUT_SECONDS = 3600  # 1 hour

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db

    async def create_approval_request(
        self,
        user_id: UUID,
        session_id: UUID,
        approval_type: str,
        title: str,
        payload: dict,
        description: str | None = None,
        options: list[str] | None = None,
        timeout_seconds: int | None = None,
        auto_action_on_timeout: str = "skip",
    ) -> HumanApproval:
        """Create a new approval request.

        This is called when the graph hits an interrupt_before node.

        Args:
            user_id: User who needs to approve
            session_id: Session this approval belongs to
            approval_type: Type (e.g., 'recommendation_review', 'resume_approval')
            title: Human-readable title
            payload: Data for the user to review
            description: Optional description
            options: Available actions (e.g., ['approve', 'reject', 'modify'])
            timeout_seconds: Timeout before auto-action
            auto_action_on_timeout: What to do on timeout

        Returns:
            Created HumanApproval record
        """
        timeout = timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS
        now = datetime.now(UTC)

        approval = HumanApproval(
            user_id=user_id,
            session_id=session_id,
            approval_type=approval_type,
            title=title,
            description=description,
            payload=payload,
            options=options or ["approve", "reject"],
            status="pending",
            timeout_seconds=timeout,
            auto_action_on_timeout=auto_action_on_timeout,
            requested_at=now,
            expired_at=now + timedelta(seconds=timeout),
        )

        if self.db:
            self.db.add(approval)
            await self.db.flush()
            await self.db.refresh(approval)

        return approval

    async def process_approval_response(
        self,
        approval_id: UUID,
        action: str,
        feedback: str | None = None,
        modified_payload: dict | None = None,
    ) -> HumanApproval | None:
        """Process a user's approval response.

        Args:
            approval_id: ID of the approval request
            action: User's action (approve/reject/modify/skip)
            feedback: Optional feedback text
            modified_payload: Modified data if action is 'modify'

        Returns:
            Updated HumanApproval record
        """
        if not self.db:
            return None

        result = await self.db.execute(
            select(HumanApproval).where(HumanApproval.id == approval_id)
        )
        approval = result.scalar_one_or_none()

        if not approval:
            return None

        if approval.status != "pending":
            return approval  # Already processed

        approval.status = "responded"
        approval.action = action
        approval.feedback = feedback
        approval.modified_payload = modified_payload
        approval.responded_at = datetime.now(UTC)

        await self.db.flush()
        await self.db.refresh(approval)
        return approval

    async def check_timeout(self, approval_id: UUID) -> bool:
        """Check if an approval has timed out and apply auto-action.

        Returns:
            True if timeout was applied
        """
        if not self.db:
            return False

        result = await self.db.execute(
            select(HumanApproval).where(
                HumanApproval.id == approval_id,
                HumanApproval.status == "pending",
            )
        )
        approval = result.scalar_one_or_none()

        if not approval:
            return False

        now = datetime.now(UTC)
        if approval.expired_at and now > approval.expired_at:
            approval.status = "expired"
            approval.action = approval.auto_action_on_timeout
            approval.responded_at = now
            await self.db.flush()
            return True

        return False

    async def get_pending_approvals(
        self, user_id: UUID, session_id: UUID | None = None
    ) -> list[HumanApproval]:
        """Get all pending approvals for a user."""
        if not self.db:
            return []

        query = select(HumanApproval).where(
            HumanApproval.user_id == user_id,
            HumanApproval.status == "pending",
        )
        if session_id:
            query = query.where(HumanApproval.session_id == session_id)

        query = query.order_by(HumanApproval.requested_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    def build_interrupt_state(self, approval: HumanApproval) -> dict:
        """Build the state payload for LangGraph interrupt.

        This dict is stored in the graph's pending_approval field.
        """
        return {
            "approval_id": str(approval.id),
            "approval_type": approval.approval_type,
            "title": approval.title,
            "description": approval.description,
            "payload": approval.payload,
            "options": approval.options,
            "timeout_seconds": approval.timeout_seconds,
            "requested_at": approval.requested_at.isoformat(),
        }

    def parse_approval_result(self, approval: HumanApproval) -> dict:
        """Parse approval result for graph state update.

        Returns dict to merge into graph state after interrupt resolves.
        """
        return {
            "human_feedback": approval.action or "skip",
            "resume_approved": approval.action == "approve",
            "pending_approval": None,
        }
