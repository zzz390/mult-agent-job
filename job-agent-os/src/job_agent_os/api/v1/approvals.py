"""Approvals endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from job_agent_os.api.deps import CurrentUser, DBSession
from job_agent_os.api.response import success_response
from job_agent_os.schemas.approval import (
    ApprovalRespondRequest,
    ApprovalResponse,
    BatchApprovalRequest,
)
from job_agent_os.services.approval_service import ApprovalService

router = APIRouter()


@router.get("")
async def list_approvals(
    db: DBSession,
    user: CurrentUser,
    status: Annotated[str | None, Query()] = None,
    session_id: Annotated[UUID | None, Query()] = None,
) -> dict:
    """List approvals (default: pending first)."""
    service = ApprovalService(db)
    approvals = await service.list_approvals(user, status=status, session_id=session_id)
    items = [
        ApprovalResponse.model_validate(a).model_dump(mode="json") for a in approvals
    ]
    return success_response(data=items)


@router.get("/{approval_id}")
async def get_approval(
    approval_id: UUID,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Get approval details."""
    service = ApprovalService(db)
    approval = await service.get_approval(user, approval_id)
    return success_response(
        data=ApprovalResponse.model_validate(approval).model_dump(mode="json")
    )


@router.post("/{approval_id}/respond")
async def respond_to_approval(
    approval_id: UUID,
    request: ApprovalRespondRequest,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Submit approval response (approve/reject/modify/skip)."""
    service = ApprovalService(db)
    approval = await service.respond_to_approval(user, approval_id, request)
    return success_response(
        data=ApprovalResponse.model_validate(approval).model_dump(mode="json")
    )


@router.post("/batch-respond")
async def batch_respond(
    request: BatchApprovalRequest,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Batch respond to multiple approvals."""
    service = ApprovalService(db)
    results = await service.batch_respond(user, request)
    return success_response(data=results)
