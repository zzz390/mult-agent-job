"""Sessions endpoints."""

from uuid import UUID

from fastapi import APIRouter, status

from job_agent_os.api.deps import CurrentUser, DBSession
from job_agent_os.api.response import success_response
from job_agent_os.schemas.match import RecommendationFeedback
from job_agent_os.schemas.session import SessionCreate, SessionMessage
from job_agent_os.services.session_service import SessionService

router = APIRouter()


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_session(
    request: SessionCreate,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Create a new agent session (async execution)."""
    service = SessionService(db)
    session = await service.create_session(user, request)
    return success_response(data=session.model_dump(mode="json"))


@router.get("")
async def list_sessions(
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """List all sessions for the current user."""
    service = SessionService(db)
    sessions = await service.list_sessions(user)
    return success_response(data=[s.model_dump(mode="json") for s in sessions])


@router.get("/{session_id}")
async def get_session(
    session_id: UUID,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Get session status."""
    service = SessionService(db)
    session = await service.get_session(user, session_id)
    return success_response(data=session.model_dump(mode="json"))


@router.post("/{session_id}/messages")
async def send_message(
    session_id: UUID,
    request: SessionMessage,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Send a message to an active session."""
    service = SessionService(db)
    result = await service.send_message(user, session_id, request)
    return success_response(data=result)


@router.post("/{session_id}/cancel")
async def cancel_session(
    session_id: UUID,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Cancel an active session."""
    service = SessionService(db)
    result = await service.cancel_session(user, session_id)
    return success_response(data=result)


@router.get("/{session_id}/logs")
async def get_session_logs(
    session_id: UUID,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Get execution logs for a session."""
    service = SessionService(db)
    logs = await service.get_session_logs(user, session_id)
    return success_response(data=logs)


@router.get("/{session_id}/timeline")
async def get_session_timeline(
    session_id: UUID,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Get session timeline."""
    service = SessionService(db)
    timeline = await service.get_session_timeline(user, session_id)
    return success_response(data=timeline)


@router.get("/{session_id}/recommendations")
async def get_recommendations(
    session_id: UUID,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Get recommendations from a session."""
    service = SessionService(db)
    recommendations = await service.get_recommendations(user, session_id)
    return success_response(data=recommendations)


@router.post("/{session_id}/recommendations/feedback")
async def submit_feedback(
    session_id: UUID,
    request: RecommendationFeedback,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Submit feedback on recommendations."""
    service = SessionService(db)
    result = await service.submit_recommendation_feedback(
        user, session_id, request.model_dump()
    )
    return success_response(data=result)

