"""Approval service."""

import asyncio
import logging
from typing import Any
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
_background_tasks: set[asyncio.Task[None]] = set()


def _recommendation_key(item: object) -> tuple[str, str, str] | None:
    """Build a stable key without trusting client-modified recommendation data."""
    if not isinstance(item, dict):
        return None
    job = item.get("job", item)
    if not isinstance(job, dict):
        return None
    job_id = str(job.get("id") or item.get("job_id") or "").strip()
    title = str(job.get("title") or item.get("job_title") or "").strip()
    company = str(job.get("company") or item.get("company") or "").strip()
    if not job_id and not title and not company:
        return None
    return job_id, title, company


def _select_reviewed_recommendations(
    original: object, requested: object | None = None
) -> list[dict[str, Any]]:
    """Select/reorder only recommendations that were present in the review."""
    source = [item for item in original if isinstance(item, dict)] if isinstance(original, list) else []
    if requested is None:
        return source
    if not isinstance(requested, list):
        return []

    by_key = {
        key: item
        for item in source
        if (key := _recommendation_key(item)) is not None
    }
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in requested:
        key = _recommendation_key(candidate)
        if key is None or key in seen or key not in by_key:
            continue
        selected.append(by_key[key])
        seen.add(key)
    return selected


async def _resume_session_background(session_id: str) -> None:
    """Resume session execution in background with independent DB session.

    Creates its own session via get_session_factory() so the background
    task is not tied to the request-scoped session.
    """
    from job_agent_os.services.session_service import SessionService

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            service = SessionService(session)
            await service.resume_session(session_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


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
        # Serialize competing responses so an approval can resume the graph
        # only once even when requests arrive on different workers.
        result = await self.db.execute(
            select(HumanApproval)
            .where(
                HumanApproval.id == approval_id,
                HumanApproval.user_id == user.id,
            )
            .with_for_update()
        )
        approval = result.scalar_one_or_none()
        if not approval:
            raise NotFoundException(
                message="Approval not found",
                code=ErrorCode.APPROVAL_NOT_FOUND,
            )

        if approval.status != "pending":
            raise ValidationException(
                message="Approval has already been processed",
                code=ErrorCode.APPROVAL_ALREADY_PROCESSED,
            )

        if data.action == "modify" and not data.modified_payload:
            raise ValidationException(
                message="modified_payload is required when action is modify",
                code=ErrorCode.VALIDATION_FAILED,
            )

        if approval.approval_type == "recommendation_review" and data.action == "modify":
            payload = getattr(approval, "payload", None)
            original = payload.get("recommendations", []) if isinstance(payload, dict) else []
            requested = (data.modified_payload or {}).get("recommendations", [])
            if not _select_reviewed_recommendations(original, requested):
                raise ValidationException(
                    message="At least one reviewed recommendation must be selected",
                    code=ErrorCode.VALIDATION_FAILED,
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

        graph = get_main_graph()
        config = {"configurable": {"thread_id": session_id}}

        # Build state update based on approval type and user action
        state_update: dict[str, Any] = {"pending_approval": None}

        if approval.approval_type == "resume_approval":
            state_update["resume_approved"] = data.action in ("approve", "modify")
            state_update["human_feedback"] = data.feedback or data.action
            if data.action == "modify" and data.modified_payload:
                state_update["optimized_resume"] = data.modified_payload.get(
                    "optimized_resume", data.modified_payload
                )
        elif approval.approval_type == "recommendation_review":
            state_update["human_feedback"] = data.feedback or data.action
            payload = getattr(approval, "payload", None)
            original = payload.get("recommendations", []) if isinstance(payload, dict) else []
            if data.action == "modify" and data.modified_payload:
                recommendations = data.modified_payload.get("recommendations", [])
                state_update["approved_recommendations"] = (
                    _select_reviewed_recommendations(original, recommendations)
                )
            elif data.action in ("approve", "skip"):
                state_update["approved_recommendations"] = (
                    _select_reviewed_recommendations(original)
                )
        else:
            state_update["human_feedback"] = data.feedback or data.action

        reroute_agent: str | None = None
        if data.action == "reject":
            # Rejection means "revise this stage", not "silently finish".
            # Resume from the Supervisor routing edge so the interrupted next
            # node is replaced by the stage that produced the rejected result.
            state_update["is_finished"] = False
            if approval.approval_type == "recommendation_review":
                reroute_agent = "match"
                state_update.update(
                    {
                        "match_results": [],
                        "approved_recommendations": None,
                        "optimized_resume": None,
                        "resume_diff": [],
                        "interview_questions": [],
                        "applications": [],
                        "kanban_state": {},
                    }
                )
            elif approval.approval_type == "resume_approval":
                reroute_agent = "resume"
                state_update.update(
                    {
                        "optimized_resume": None,
                        "resume_diff": [],
                        "resume_approved": False,
                        "interview_questions": [],
                        "applications": [],
                        "kanban_state": {},
                    }
                )

            if reroute_agent:
                feedback = data.feedback or "用户拒绝了当前结果，请生成不同的版本"
                state_update.update(
                    {
                        "next_agent": reroute_agent,
                        "task_instruction": feedback,
                        "human_feedback": feedback,
                    }
                )

        # Only rejected stage results need an explicit routing override;
        # approve/modify/skip naturally continue from the interrupt point.
        if reroute_agent:
            await graph.aupdate_state(config, state_update, as_node="supervisor")
        else:
            await graph.aupdate_state(config, state_update)

        from job_agent_os.services.session_store import get_session_store

        store = get_session_store()
        await store.update(
            session_id,
            status="running",
            current_phase=reroute_agent or approval.approval_type,
            pending_approval=None,
            updated_at=utc_now().isoformat(),
        )

        # Resume execution in background with independent DB session.
        task = asyncio.create_task(_resume_session_background(session_id))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    async def batch_respond(
        self, user: User, data: BatchApprovalRequest
    ) -> list[dict[str, Any]]:
        """Batch respond to multiple approvals."""
        results: list[dict[str, Any]] = []
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
