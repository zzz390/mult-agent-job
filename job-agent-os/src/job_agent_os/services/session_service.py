"""Session service (Agent session management)."""

import asyncio
import logging
from uuid import UUID

from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.core.error_codes import ErrorCode
from job_agent_os.core.exceptions import NotFoundException, ValidationException
from job_agent_os.core.utils import generate_uuid_obj, utc_now
from job_agent_os.graph.state import JobAgentState
from job_agent_os.harness.runtime import get_harness_runtime
from job_agent_os.models.agent_log import AgentLog
from job_agent_os.models.user import User
from job_agent_os.schemas.session import (
    SessionCreate,
    SessionMessage,
    SessionResponse,
)

logger = logging.getLogger(__name__)

# In-memory session store (would be Redis in production)
_sessions: dict[str, dict] = {}

# Keep references to background tasks to prevent garbage collection
_background_tasks: set[asyncio.Task] = set()


class SessionService:
    """Session service for managing agent execution sessions."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_session(self, user: User, data: SessionCreate) -> SessionResponse:
        """Create a new agent session and start execution."""
        session_id = generate_uuid_obj()

        # Build initial state — inject user's intent as the first message
        initial_state: JobAgentState = {
            "session_id": str(session_id),
            "user_id": str(user.id),
            "current_phase": "supervisor",
            "messages": [HumanMessage(content=data.intent)],
            "job_query": None,
            "clarification_needed": False,
            "clarification_question": None,
            "search_results": [],
            "search_errors": [],
            "platforms_searched": [],
            "parsed_jobs": [],
            "parse_failures": [],
            "match_results": [],
            "user_profile": None,
            "match_threshold": 60.0,
            "optimized_resume": None,
            "resume_diff": [],
            "resume_approved": False,
            "interview_questions": [],
            "applications": [],
            "kanban_state": {},
            # Supervisor fields
            "next_agent": "",
            "task_instruction": "",
            "supervisor_reasoning": "",
            "is_finished": False,
            "agent_execution_order": [],
            # HITL
            "pending_approval": None,
            "human_feedback": None,
            # Harness
            "execution_log": [],
            "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
            "error_state": None,
            "retry_count": 0,
        }

        # Store session info
        session_info = {
            "session_id": str(session_id),
            "user_id": str(user.id),
            "status": "running",
            "mode": data.mode,
            "intent": data.intent,
            "current_phase": "supervisor",
            "progress": {
                "completed_steps": [],
                "current_step": "supervisor",
                "pending_steps": [],
            },
            "pending_approval": None,
            "results_summary": {},
            "token_usage": {},
            "started_at": utc_now().isoformat(),
            "updated_at": utc_now().isoformat(),
        }
        _sessions[str(session_id)] = session_info

        # Start execution in background
        task = asyncio.create_task(self._execute_session(str(session_id), initial_state, data))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        return SessionResponse(
            session_id=session_id,
            status="running",
            current_phase="intent",
            progress=session_info["progress"],
            started_at=utc_now(),
            updated_at=utc_now(),
        )

    async def _execute_session(
        self, session_id: str, initial_state: JobAgentState, data: SessionCreate
    ) -> None:
        """Execute the Supervisor-loop graph in background."""
        from job_agent_os.graph.main_graph import get_main_graph

        runtime = get_harness_runtime()
        try:
            graph = get_main_graph()
            config = {"configurable": {"thread_id": session_id}}
            result = await runtime.execute(graph, initial_state, config)

            # Graph completed (Supervisor set is_finished=true)
            if session_id in _sessions:
                execution_order = result.get("agent_execution_order", [])
                _sessions[session_id]["status"] = "completed"
                _sessions[session_id]["current_phase"] = "done"
                _sessions[session_id]["updated_at"] = utc_now().isoformat()
                _sessions[session_id]["results_summary"] = {
                    "match_results_count": len(result.get("match_results", [])),
                    "applications_count": len(result.get("applications", [])),
                    "recommendations": result.get("match_results", []),
                    "agent_execution_order": execution_order,
                }
                _sessions[session_id]["token_usage"] = dict(result.get("token_usage", {}))
                _sessions[session_id]["progress"] = {
                    "completed_steps": execution_order,
                    "current_step": None,
                    "pending_steps": [],
                }
        except Exception as e:
            logger.exception("Session execution failed")
            if session_id in _sessions:
                _sessions[session_id]["status"] = "failed"
                _sessions[session_id]["updated_at"] = utc_now().isoformat()
                _sessions[session_id]["results_summary"] = {"error": str(e)}

    async def resume_session(self, session_id: str) -> None:
        """Resume session execution after human approval.

        Uses the graph's checkpoint to continue from where it paused.
        Creates an independent DB session so the background task is not
        tied to the request-scoped session.
        """
        from job_agent_os.graph.main_graph import get_main_graph

        try:
            graph = get_main_graph()
            config = {
                "configurable": {"thread_id": session_id},
                "recursion_limit": 100,
            }

            # Resume from checkpoint with no new input
            result = await graph.ainvoke(None, config)

            if session_id in _sessions:
                execution_order = result.get("agent_execution_order", [])
                _sessions[session_id]["status"] = "completed"
                _sessions[session_id]["current_phase"] = "done"
                _sessions[session_id]["updated_at"] = utc_now().isoformat()
                _sessions[session_id]["results_summary"] = {
                    "match_results_count": len(result.get("match_results", [])),
                    "applications_count": len(result.get("applications", [])),
                    "recommendations": result.get("match_results", []),
                    "agent_execution_order": execution_order,
                }
                _sessions[session_id]["token_usage"] = dict(result.get("token_usage", {}))
                _sessions[session_id]["progress"] = {
                    "completed_steps": execution_order,
                    "current_step": None,
                    "pending_steps": [],
                }
        except Exception as e:
            logger.exception("Session resume failed")
            if session_id in _sessions:
                _sessions[session_id]["status"] = "failed"
                _sessions[session_id]["updated_at"] = utc_now().isoformat()
                _sessions[session_id]["results_summary"] = {"error": str(e)}

    async def list_sessions(self, user: User) -> list[SessionResponse]:
        """List all sessions for a user."""
        sessions = []
        for sid, info in _sessions.items():
            if info["user_id"] == str(user.id):
                sessions.append(
                    SessionResponse(
                        session_id=UUID(sid),
                        status=info["status"],
                        intent=info.get("intent"),
                        current_phase=info.get("current_phase"),
                        progress=info.get("progress"),
                        pending_approval=info.get("pending_approval"),
                        results_summary=info.get("results_summary", {}),
                        token_usage=info.get("token_usage", {}),
                        started_at=info.get("started_at"),
                        updated_at=info.get("updated_at"),
                    )
                )
        # Sort by started_at desc
        sessions.sort(key=lambda s: s.started_at or "", reverse=True)
        return sessions

    async def get_session(self, user: User, session_id: UUID) -> SessionResponse:
        """Get session status."""
        info = _sessions.get(str(session_id))
        if not info or info["user_id"] != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )
        return SessionResponse(
            session_id=session_id,
            status=info["status"],
            intent=info.get("intent"),
            current_phase=info.get("current_phase"),
            progress=info.get("progress"),
            pending_approval=info.get("pending_approval"),
            results_summary=info.get("results_summary", {}),
            token_usage=info.get("token_usage", {}),
            started_at=info.get("started_at"),
            updated_at=info.get("updated_at"),
        )

    async def send_message(
        self, user: User, session_id: UUID, message: SessionMessage
    ) -> dict:
        """Send a message to an active session (e.g., clarification response)."""
        info = _sessions.get(str(session_id))
        if not info or info["user_id"] != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )
        if info["status"] not in ("running", "waiting_approval"):
            raise ValidationException(
                message="Session is not active",
                code=ErrorCode.SESSION_ENDED,
            )

        return {
            "message_id": str(generate_uuid_obj()),
            "response": "Message received. Processing...",
            "session_status": info["status"],
        }

    async def cancel_session(self, user: User, session_id: UUID) -> dict:
        """Cancel an active session."""
        info = _sessions.get(str(session_id))
        if not info or info["user_id"] != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )
        if info["status"] not in ("running", "waiting_approval"):
            raise ValidationException(
                message="Session is not active",
                code=ErrorCode.SESSION_ENDED,
            )

        runtime = get_harness_runtime()
        runtime.cancel_session(str(session_id))
        info["status"] = "cancelled"
        info["updated_at"] = utc_now().isoformat()

        return {"session_id": str(session_id), "status": "cancelled"}

    async def get_session_logs(self, user: User, session_id: UUID) -> list[dict]:
        """Get execution logs for a session."""
        info = _sessions.get(str(session_id))
        if not info or info["user_id"] != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )

        result = await self.db.execute(
            select(AgentLog)
            .where(AgentLog.session_id == session_id)
            .order_by(AgentLog.step_order.asc())
        )
        logs = result.scalars().all()
        return [
            {
                "id": str(log.id),
                "agent_name": log.agent_name,
                "node_name": log.node_name,
                "step_order": log.step_order,
                "status": log.status,
                "duration_ms": log.duration_ms,
                "total_tokens": log.total_tokens,
                "error_message": log.error_message,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "finished_at": log.finished_at.isoformat() if log.finished_at else None,
            }
            for log in logs
        ]

    async def get_session_timeline(self, user: User, session_id: UUID) -> list[dict]:
        """Get session timeline (events)."""
        info = _sessions.get(str(session_id))
        if not info or info["user_id"] != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )

        timeline = [
            {"event": "session_created", "timestamp": info.get("started_at"), "data": {"mode": info.get("mode")}},
        ]
        progress = info.get("progress", {})
        for step in progress.get("completed_steps", []):
            timeline.append({"event": f"step_completed:{step}", "timestamp": info.get("updated_at"), "data": {}})

        if info["status"] == "completed":
            timeline.append({"event": "session_completed", "timestamp": info.get("updated_at"), "data": info.get("results_summary", {})})
        elif info["status"] == "failed":
            timeline.append({"event": "session_error", "timestamp": info.get("updated_at"), "data": info.get("results_summary", {})})

        return timeline

    async def get_recommendations(self, user: User, session_id: UUID) -> list[dict]:
        """Get recommendations from a session."""
        info = _sessions.get(str(session_id))
        if not info or info["user_id"] != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )
        return info.get("results_summary", {}).get("recommendations", [])

    async def submit_recommendation_feedback(
        self, user: User, session_id: UUID, feedback: dict
    ) -> dict:
        """Submit feedback on recommendations."""
        info = _sessions.get(str(session_id))
        if not info or info["user_id"] != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )
        # Store feedback (in full implementation, would update graph state)
        return {"status": "feedback_received", "session_id": str(session_id)}
