"""Session service (Agent session management).

Fixes wired in here:
- Issue #4: `send_message` now injects the user reply into the LangGraph
  checkpoint and resumes execution (multi-turn loop closed)
- Issue #5: session results are distilled into long-term memory on finish
- Issue #6: session info lives in Redis (via SessionStore), not a dict
- Issue #7: recommendation feedback is persisted and shapes preferences
- Issue #10: the user's resume profile is loaded into the initial state
"""

import asyncio
import logging
from uuid import UUID

from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.core.error_codes import ErrorCode
from job_agent_os.core.exceptions import NotFoundException, ValidationException
from job_agent_os.core.utils import generate_uuid_obj, utc_now
from job_agent_os.db.session import get_session_factory
from job_agent_os.graph.state import JobAgentState
from job_agent_os.harness.runtime import get_harness_runtime
from job_agent_os.models.agent_log import AgentLog
from job_agent_os.models.user import User
from job_agent_os.schemas.session import (
    SessionCreate,
    SessionMessage,
    SessionResponse,
)
from job_agent_os.services.session_store import SessionStore, get_session_store

logger = logging.getLogger(__name__)

# Keep references to background tasks to prevent garbage collection
_background_tasks: set[asyncio.Task] = set()

# Statuses in which the session accepts new user messages
ACTIVE_STATUSES = ("running", "waiting_approval", "waiting_input")


def _spawn_background(coro) -> None:
    """Run a coroutine as a tracked background task."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _resume_session_background(session_id: str) -> None:
    """Resume session execution in background with an independent DB session.

    Creates its own DB session so the background task is not tied to the
    request-scoped session (which may be committed/closed already).
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            service = SessionService(session)
            await service.resume_session(session_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _execute_session_background(
    session_id: str, initial_state: JobAgentState, data: SessionCreate
) -> None:
    """Execute a new workflow using a DB session owned by the task."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            service = SessionService(session)
            await service._execute_session(session_id, initial_state, data)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class SessionService:
    """Session service for managing agent execution sessions."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.store: SessionStore = get_session_store()

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def create_session(self, user: User, data: SessionCreate) -> SessionResponse:
        """Create a new agent session and start execution."""
        session_id = generate_uuid_obj()

        # Issue #10: load the user's resume profile so match/resume/interview
        # agents operate on real data instead of an empty profile.
        user_profile: dict | None = None
        try:
            from job_agent_os.services.resume_service import ResumeService

            user_profile = await ResumeService(self.db).get_user_resume(
                user.id, data.resume_id
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to load resume profile for user %s: %s", user.id, e)

        structured_query = data.options.get("structured_query")
        requested_platforms = data.options.get("platforms", [])
        if not isinstance(structured_query, dict):
            structured_query = None
        if not isinstance(requested_platforms, list):
            requested_platforms = []

        # Build initial state — inject user's intent as the first message
        initial_state: JobAgentState = {
            "session_id": str(session_id),
            "user_id": str(user.id),
            "current_phase": "supervisor",
            "messages": [HumanMessage(content=data.intent)],
            "mode": data.mode,
            "requested_platforms": [str(item) for item in requested_platforms],
            "resume_id": str(data.resume_id) if data.resume_id else None,
            "job_query": structured_query,
            "clarification_needed": False,
            "clarification_question": None,
            "search_results": [],
            "search_errors": [],
            "platforms_searched": [],
            "parsed_jobs": [],
            "parse_failures": [],
            "match_results": [],
            "approved_recommendations": None,
            "user_profile": user_profile,
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
            "use_fallback_model": False,
        }

        # Store session info (Redis-backed with TTL, issue #6)
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
                "active_agent": "supervisor",
                "active_agent_status": "running",
                "activity_message": "正在准备处理求职请求",
                "items_found": 0,
                "items_saved": 0,
                "last_activity_at": utc_now().isoformat(),
            },
            "pending_approval": None,
            "results_summary": {},
            "token_usage": {},
            "started_at": utc_now().isoformat(),
            "updated_at": utc_now().isoformat(),
        }
        await self.store.set(str(session_id), session_info)

        # Start execution in background
        _spawn_background(
            _execute_session_background(str(session_id), initial_state, data)
        )

        return SessionResponse(
            session_id=session_id,
            status="running",
            current_phase="supervisor",
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

            await self._finalize_session(session_id, result)

            # Issue #5: distill this session into long-term memory
            await self._save_session_memories(
                str(initial_state.get("user_id", "")), result, session_id
            )
        except Exception as e:
            logger.exception("Session execution failed")
            await self._mark_session_failed(session_id, str(e))

    async def _mark_session_failed(self, session_id: str, error: str) -> None:
        """Persist a failed terminal state without leaving a stale spinner."""
        info = await self.store.get(session_id)
        progress = dict((info or {}).get("progress") or {})
        progress.update(
            {
                "current_step": None,
                "active_agent": None,
                "active_agent_status": "failed",
            }
        )
        await self.store.update(
            session_id,
            status="failed",
            updated_at=utc_now().isoformat(),
            results_summary={"error": error},
            progress=progress,
        )

    async def resume_session(self, session_id: str) -> None:
        """Resume session execution from its checkpoint.

        Used both after human approval (HITL) and after the user answers a
        clarification question via send_message. Creates an independent DB
        session so the background task is not tied to the request scope.
        """
        from job_agent_os.graph.main_graph import get_main_graph

        try:
            graph = get_main_graph()
            config = {
                "configurable": {"thread_id": session_id},
                "recursion_limit": 100,
            }

            # Resume from checkpoint with no new input, through the same guard
            # and tracing runtime as an initial invocation.
            result = await get_harness_runtime().execute(graph, None, config)

            await self._finalize_session(session_id, result)

            # Issue #5: also persist memories after resumed runs
            if isinstance(result, dict):
                await self._save_session_memories(
                    str(result.get("user_id", "")), result, session_id
                )
        except Exception as e:
            logger.exception("Session resume failed")
            await self._mark_session_failed(session_id, str(e))

    async def _finalize_session(self, session_id: str, result) -> None:
        """Persist final session state, distinguishing paused vs completed.

        A run can end in three ways:
        - clarification needed  -> waiting_input (user must reply)
        - interrupted (HITL)    -> waiting_approval
        - supervisor finished   -> completed
        """
        if not isinstance(result, dict):
            result = {}

        execution_order = result.get("agent_execution_order", [])
        clarification_needed = bool(result.get("clarification_needed"))

        # Detect whether the graph is paused at an interrupt point
        paused_nodes: tuple[str, ...] = ()
        try:
            from job_agent_os.graph.main_graph import get_main_graph

            snapshot = await get_main_graph().aget_state(
                {"configurable": {"thread_id": session_id}}
            )
            paused_nodes = tuple(snapshot.next) if snapshot else ()
        except Exception:  # noqa: BLE001
            pass

        pending_approval: dict | None = None
        if clarification_needed:
            status = "waiting_input"
            current_phase = "intent"
        elif paused_nodes:
            status = "waiting_approval"
            current_phase = paused_nodes[0]
            pending_approval = await self._ensure_approval(
                session_id, current_phase, result
            )
        else:
            status = "completed"
            current_phase = "done"

        if status == "completed":
            await self._persist_applications(result)

        results_summary = {
            "match_results_count": len(result.get("match_results", [])),
            "applications_count": len(result.get("applications", [])),
            "recommendations": result.get("match_results", []),
            "optimized_resume": result.get("optimized_resume"),
            "resume_diff": result.get("resume_diff", []),
            "interview_questions": result.get("interview_questions", []),
            "agent_execution_order": execution_order,
        }
        if clarification_needed:
            results_summary["clarification_question"] = result.get(
                "clarification_question"
            ) or "请补充您的求职意向信息。"

        existing_progress = dict(
            ((await self.store.get(session_id)) or {}).get("progress") or {}
        )
        await self.store.update(
            session_id,
            status=status,
            current_phase=current_phase,
            pending_approval=pending_approval,
            updated_at=utc_now().isoformat(),
            results_summary=results_summary,
            token_usage=dict(result.get("token_usage", {})),
            progress={
                "completed_steps": list(
                    dict.fromkeys(["supervisor", *execution_order])
                ),
                # Waiting states are pauses for human input/approval, not an
                # Agent actively executing.  Do not leave the UI spinner on.
                "current_step": None,
                "pending_steps": [],
                "active_agent": None,
                "active_agent_status": "completed"
                if status == "completed"
                else "waiting",
                # Keep the final crawl counters/message visible after the
                # graph finishes instead of replacing them with node state.
                "activity_message": existing_progress.get("activity_message"),
                "items_found": existing_progress.get("items_found", 0),
                "items_saved": existing_progress.get("items_saved", 0),
                "last_activity_at": existing_progress.get("last_activity_at"),
            },
        )

    async def _ensure_approval(
        self, session_id: str, paused_node: str, result: dict
    ) -> dict:
        """Create (or reuse) the approval represented by a graph interrupt."""
        from job_agent_os.harness.hitl_gateway import HITLGateway

        user_id = UUID(str(result["user_id"]))
        sid = UUID(session_id)
        if paused_node == "resume":
            approval_type = "recommendation_review"
            title = "确认岗位推荐结果"
            description = "请确认推荐岗位后再生成针对性简历。"
            payload = {"recommendations": result.get("match_results", [])}
        elif paused_node == "interview":
            approval_type = "resume_approval"
            title = "确认优化后的简历"
            description = "请确认简历内容后再生成面试准备材料。"
            payload = {
                "optimized_resume": result.get("optimized_resume"),
                "resume_diff": result.get("resume_diff", []),
            }
        else:
            approval_type = f"{paused_node}_approval"
            title = f"确认 {paused_node} 阶段结果"
            description = None
            payload = {}

        gateway = HITLGateway(self.db)
        existing = await gateway.get_pending_approvals(user_id, sid)
        approval = next(
            (item for item in existing if item.approval_type == approval_type), None
        )
        if approval is None:
            approval = await gateway.create_approval_request(
                user_id=user_id,
                session_id=sid,
                approval_type=approval_type,
                title=title,
                description=description,
                payload=payload,
                options=["approve", "reject", "modify", "skip"],
            )

        interrupt_state = gateway.build_interrupt_state(approval)
        try:
            from job_agent_os.graph.main_graph import get_main_graph

            await get_main_graph().aupdate_state(
                {"configurable": {"thread_id": session_id}},
                {"pending_approval": interrupt_state},
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to mirror approval into graph state")

        return {
            "id": str(approval.id),
            "type": approval.approval_type,
            "title": approval.title,
        }

    async def _persist_applications(self, result: dict) -> None:
        """Persist tracker output using only owned resumes and stored jobs."""
        from job_agent_os.models.application import Application
        from job_agent_os.models.job import Job
        from job_agent_os.models.resume import Resume

        candidates = [
            item for item in result.get("applications", []) if isinstance(item, dict)
        ]
        profile = result.get("user_profile") or {}
        if not candidates or not profile.get("resume_id") or not result.get("user_id"):
            return

        try:
            user_id = UUID(str(result["user_id"]))
            resume_id = UUID(str(profile["resume_id"]))
        except (TypeError, ValueError):
            return
        owned_resume = await self.db.execute(
            select(Resume.id).where(
                Resume.id == resume_id, Resume.user_id == user_id
            )
        )
        if owned_resume.scalar_one_or_none() is None:
            logger.warning("Skipping application persistence: resume ownership failed")
            return

        candidate_ids: set[UUID] = set()
        for item in candidates:
            try:
                candidate_ids.add(UUID(str(item.get("job_id", ""))))
            except (TypeError, ValueError):
                continue
        if not candidate_ids:
            return

        stored_job_ids = set(
            (
                await self.db.execute(select(Job.id).where(Job.id.in_(candidate_ids)))
            ).scalars().all()
        )
        existing_job_ids = set(
            (
                await self.db.execute(
                    select(Application.job_id).where(
                        Application.user_id == user_id,
                        Application.job_id.in_(stored_job_ids),
                    )
                )
            ).scalars().all()
        )
        for item in candidates:
            try:
                job_id = UUID(str(item.get("job_id", "")))
            except (TypeError, ValueError):
                continue
            if job_id not in stored_job_ids or job_id in existing_job_ids:
                continue
            application = Application(
                user_id=user_id,
                job_id=job_id,
                resume_id=resume_id,
                status="pending",
                stage="none",
                match_score=float(item.get("match_score", 0) or 0),
                recommendation_reason=item.get("recommendation_reason") or None,
                status_history=[
                    {"status": "pending", "timestamp": utc_now().isoformat()}
                ],
            )
            self.db.add(application)
            await self.db.flush()
            item["application_id"] = str(application.id)
            existing_job_ids.add(job_id)

    # ------------------------------------------------------------------
    # Long-term memory (issue #5)
    # ------------------------------------------------------------------

    async def _save_session_memories(
        self, user_id: str, result: dict, session_id: str
    ) -> None:
        """Write distilled session outcomes into long-term memory.

        Best-effort: failures are logged but never break the session flow.
        """
        if not user_id:
            return
        try:
            from job_agent_os.memory.store import PostgresMemoryStore

            session_factory = get_session_factory()
            async with session_factory() as db:
                store = PostgresMemoryStore(db)
                uid = UUID(user_id)

                # 1. Latest job preference (drives future intent recall)
                job_query = result.get("job_query")
                if isinstance(job_query, dict) and any(job_query.values()):
                    await store.save_memory(
                        user_id=uid,
                        key="job_preference_latest",
                        content=dict(job_query),
                        category="preference",
                        memory_type="long_term",
                        importance_score=0.8,
                        source_agent="session",
                        source_session_id=UUID(session_id),
                    )

                # 2. Top matched jobs of this session
                match_results = result.get("match_results") or []
                for i, match in enumerate(match_results[:3]):
                    if not isinstance(match, dict):
                        continue
                    try:
                        score = float(match.get("overall_score", 0))
                    except (TypeError, ValueError):
                        score = 0.0
                    await store.save_memory(
                        user_id=uid,
                        key=f"top_match_{session_id}_{i}",
                        content=dict(match),
                        category="job_match",
                        memory_type="long_term",
                        importance_score=max(0.0, min(1.0, score / 100.0)),
                        source_agent="match",
                        source_session_id=UUID(session_id),
                    )

                await db.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to save session memories for %s: %s", session_id, e)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def list_sessions(self, user: User) -> list[SessionResponse]:
        """List all sessions for a user."""
        all_sessions = await self.store.list_all()
        sessions = []
        for sid, info in all_sessions.items():
            if info.get("user_id") == str(user.id):
                sessions.append(
                    SessionResponse(
                        session_id=UUID(sid),
                        status=info.get("status", "unknown"),
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
        # Sort by started_at desc (missing timestamps last)
        sessions.sort(
            key=lambda s: s.started_at.isoformat() if s.started_at else "", reverse=True
        )
        return sessions

    async def get_session(self, user: User, session_id: UUID) -> SessionResponse:
        """Get session status."""
        info = await self.store.get(str(session_id))
        if not info or info.get("user_id") != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )
        return SessionResponse(
            session_id=session_id,
            status=info.get("status", "unknown"),
            intent=info.get("intent"),
            current_phase=info.get("current_phase"),
            progress=info.get("progress"),
            pending_approval=info.get("pending_approval"),
            results_summary=info.get("results_summary", {}),
            token_usage=info.get("token_usage", {}),
            started_at=info.get("started_at"),
            updated_at=info.get("updated_at"),
        )

    # ------------------------------------------------------------------
    # Multi-turn interaction (issue #4)
    # ------------------------------------------------------------------

    async def send_message(
        self, user: User, session_id: UUID, message: SessionMessage
    ) -> dict:
        """Send a message to an active session (e.g. clarification answer).

        Closes the multi-turn loop:
        1. append the user message to the graph checkpoint state
        2. reset intent so the pipeline re-parses with the new information
        3. resume graph execution in the background
        """
        info = await self.store.get(str(session_id))
        if not info or info.get("user_id") != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )
        if info.get("status") not in ACTIVE_STATUSES:
            raise ValidationException(
                message="Session is not active",
                code=ErrorCode.SESSION_ENDED,
            )

        from job_agent_os.graph.main_graph import get_main_graph

        graph = get_main_graph()
        config = {"configurable": {"thread_id": str(session_id)}}

        try:
            # 1+2. Inject the reply and reset the pipeline to re-parse intent.
            # as_node="supervisor" makes execution continue from the
            # supervisor's routing edge, which reads the fresh next_agent.
            await graph.aupdate_state(
                config,
                {
                    "messages": [HumanMessage(content=message.content)],
                    "clarification_needed": False,
                    "clarification_question": None,
                    "job_query": None,
                    # A new/clarified intent starts a new result generation.
                    # Clear current-run products so the Supervisor cannot skip
                    # search/match based on stale data from the previous turn.
                    "search_results": [],
                    "search_errors": [],
                    "platforms_searched": [],
                    "parsed_jobs": [],
                    "parse_failures": [],
                    "match_results": [],
                    "approved_recommendations": None,
                    "optimized_resume": None,
                    "resume_diff": [],
                    "resume_approved": False,
                    "interview_questions": [],
                    "applications": [],
                    "kanban_state": {},
                    "pending_approval": None,
                    "human_feedback": None,
                    "next_agent": "intent",
                    "task_instruction": "用户补充了信息，请重新解析求职意向",
                    "is_finished": False,
                },
                as_node="supervisor",
            )
        except Exception as exc:
            logger.exception("Failed to inject message into session graph")
            raise ValidationException(
                message="Session graph state is unavailable; please start a new session",
                code=ErrorCode.SESSION_ENDED,
            ) from exc

        # Mark session running again
        await self.store.update(
            str(session_id),
            status="running",
            current_phase="intent",
            progress={
                "completed_steps": [],
                "current_step": "intent",
                "pending_steps": [],
                "active_agent": "intent",
                "active_agent_status": "running",
                "activity_message": "正在重新解析求职意向",
                "items_found": 0,
                "items_saved": 0,
                "last_activity_at": utc_now().isoformat(),
            },
            updated_at=utc_now().isoformat(),
        )

        # 3. Resume execution in background (independent DB session)
        _spawn_background(_resume_session_background(str(session_id)))

        return {
            "message_id": str(generate_uuid_obj()),
            "response": "已收到，正在重新解析您的求职意向...",
            "session_status": "running",
        }

    async def cancel_session(self, user: User, session_id: UUID) -> dict:
        """Cancel an active session."""
        info = await self.store.get(str(session_id))
        if not info or info.get("user_id") != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )
        if info.get("status") not in ACTIVE_STATUSES:
            raise ValidationException(
                message="Session is not active",
                code=ErrorCode.SESSION_ENDED,
            )

        runtime = get_harness_runtime()
        runtime.cancel_session(str(session_id))
        progress = dict(info.get("progress") or {})
        progress.update(
            {
                "current_step": None,
                "active_agent": None,
                "active_agent_status": "completed",
            }
        )
        await self.store.update(
            str(session_id),
            status="cancelled",
            progress=progress,
            updated_at=utc_now().isoformat(),
        )

        return {"session_id": str(session_id), "status": "cancelled"}

    async def delete_session(self, user: User, session_id: UUID) -> dict:
        """Permanently remove one of the user's session records.

        Session history is stored in ``SessionStore`` rather than an SQL
        session table.  Cancelling first prevents a running graph from
        continuing to consume resources; deleting the store record makes the
        conversation unavailable from every session endpoint immediately.
        """
        info = await self.store.get(str(session_id))
        if not info or info.get("user_id") != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )

        get_harness_runtime().cancel_session(str(session_id))
        await self.store.delete(str(session_id))

        return {"session_id": str(session_id), "status": "deleted"}

    async def get_session_logs(self, user: User, session_id: UUID) -> list[dict]:
        """Get execution logs for a session."""
        info = await self.store.get(str(session_id))
        if not info or info.get("user_id") != str(user.id):
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
        info = await self.store.get(str(session_id))
        if not info or info.get("user_id") != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )

        timeline = [
            {"event": "session_created", "timestamp": info.get("started_at"), "data": {"mode": info.get("mode")}},
        ]
        progress = info.get("progress", {}) or {}
        for step in progress.get("completed_steps", []):
            timeline.append({"event": f"step_completed:{step}", "timestamp": info.get("updated_at"), "data": {}})

        status = info.get("status")
        if status == "completed":
            timeline.append({"event": "session_completed", "timestamp": info.get("updated_at"), "data": info.get("results_summary", {})})
        elif status == "failed":
            timeline.append({"event": "session_error", "timestamp": info.get("updated_at"), "data": info.get("results_summary", {})})
        elif status == "waiting_input":
            timeline.append({
                "event": "waiting_for_user_input",
                "timestamp": info.get("updated_at"),
                "data": {
                    "clarification_question": info.get("results_summary", {}).get("clarification_question")
                },
            })

        return timeline

    async def get_recommendations(self, user: User, session_id: UUID) -> list[dict]:
        """Get recommendations from a session."""
        info = await self.store.get(str(session_id))
        if not info or info.get("user_id") != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )
        return info.get("results_summary", {}).get("recommendations", [])

    # ------------------------------------------------------------------
    # Feedback (issue #7)
    # ------------------------------------------------------------------

    async def submit_recommendation_feedback(
        self, user: User, session_id: UUID, feedback: dict
    ) -> dict:
        """Persist recommendation feedback into long-term memory.

        Feedback now has durable effects:
        - every action is stored (category=feedback) for auditing/analysis
        - rejected recommendations create an "avoid" preference memory that
          biases future matching
        """
        info = await self.store.get(str(session_id))
        if not info or info.get("user_id") != str(user.id):
            raise NotFoundException(
                message="Session not found",
                code=ErrorCode.SESSION_NOT_FOUND,
            )

        try:
            from job_agent_os.memory.store import PostgresMemoryStore

            store = PostgresMemoryStore(self.db)

            action = feedback.get("action", "")
            job_id = str(feedback.get("job_id", ""))

            # 1. Persist the raw feedback event
            await store.save_memory(
                user_id=user.id,
                key=f"feedback_{session_id}_{job_id}",
                content={
                    "action": action,  # accept / reject / interested
                    "job_id": job_id,
                    "reason": feedback.get("reason") or "",
                },
                category="feedback",
                memory_type="long_term",
                importance_score=0.6,
                source_agent="user_feedback",
                source_session_id=UUID(str(session_id)),
            )

            # 2. Turn negative feedback into an avoid-pattern preference
            if action == "reject":
                avoid_payload: dict = {"action": "avoid"}
                if feedback.get("reason"):
                    avoid_payload["reason"] = feedback["reason"]
                if isinstance(feedback.get("adjust_weights"), dict):
                    avoid_payload["adjust_weights"] = feedback["adjust_weights"]
                await store.save_memory(
                    user_id=user.id,
                    key=f"avoid_pattern_{job_id}",
                    content=avoid_payload,
                    category="preference",
                    memory_type="long_term",
                    importance_score=0.7,
                    source_agent="user_feedback",
                    source_session_id=UUID(str(session_id)),
                )

            await self.db.flush()
        except Exception:
            logger.exception("Failed to persist recommendation feedback")
            return {"status": "feedback_failed", "session_id": str(session_id)}

        return {"status": "feedback_saved", "session_id": str(session_id)}
