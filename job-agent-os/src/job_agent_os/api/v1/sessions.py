"""Sessions endpoints."""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from job_agent_os.api.deps import CurrentUser, DBSession
from job_agent_os.api.response import success_response
from job_agent_os.schemas.match import RecommendationFeedback
from job_agent_os.schemas.session import SessionCreate, SessionMessage
from job_agent_os.services.session_service import SessionService
from job_agent_os.services.session_store import get_session_store

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


@router.delete("/{session_id}")
async def delete_session(
    session_id: UUID,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Delete a session owned by the current user.

    If it is still running, its graph task is cancelled before the session
    record is removed.
    """
    service = SessionService(db)
    result = await service.delete_session(user, session_id)
    return success_response(data=result)


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


@router.get("/{session_id}/stream")
async def stream_session(
    session_id: UUID,
    db: DBSession,
    user: CurrentUser,
) -> StreamingResponse:
    """SSE stream of Agent execution progress (issue #4).

    Pushes an event whenever the session's phase, status, or visible progress
    changes, and a final `done` event when it reaches a terminal or waiting
    state.
    Replaces client-side polling.
    """
    service = SessionService(db)
    # Validate ownership up front (raises 404 for foreign/unknown sessions)
    await service.get_session(user, session_id)

    store = get_session_store()
    sid = str(session_id)

    async def event_generator():
        last_phase = None
        last_status = None
        last_progress = None
        terminal = ("completed", "failed", "cancelled")
        try:
            while True:
                info = await store.get(sid)
                if not info:
                    yield f"data: {json.dumps({'done': True, 'reason': 'session_gone'})}\n\n"
                    break

                current_phase = info.get("current_phase")
                current_status = info.get("status")
                progress = info.get("progress")
                progress_fingerprint = json.dumps(
                    progress, ensure_ascii=False, sort_keys=True, default=str
                )
                if (
                    current_phase != last_phase
                    or current_status != last_status
                    or progress_fingerprint != last_progress
                ):
                    payload = {
                        "phase": current_phase,
                        "status": current_status,
                        "progress": progress,
                    }
                    yield f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
                    last_phase = current_phase
                    last_status = current_status
                    last_progress = progress_fingerprint

                if current_status in terminal or current_status in {
                    "waiting_approval",
                    "waiting_input",
                }:
                    final = {"done": True, "status": current_status}
                    if current_status == "waiting_input":
                        final["clarification_question"] = info.get(
                            "results_summary", {}
                        ).get("clarification_question")
                    yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
                    break

                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            # Client disconnected — nothing to clean up
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
