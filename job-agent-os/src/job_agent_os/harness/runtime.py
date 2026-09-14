"""Harness Runtime main entry (lifecycle management)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from job_agent_os.graph.state import JobAgentState
from job_agent_os.harness.budget_controller import BudgetController
from job_agent_os.harness.guard_rails import (
    GuardRailChain,
    GuardRailViolation,
    TokenBudgetGuard,
)
from job_agent_os.harness.recovery_manager import RecoveryManager
from job_agent_os.harness.trace_manager import TraceManager
from job_agent_os.settings import get_settings

logger = logging.getLogger(__name__)

# TTL for completed sessions (in seconds)
_SESSION_TTL_SECONDS = 300  # 5 minutes


class HarnessRuntime:
    """Harness Runtime manages the execution of LangGraph workflows.

    It provides:
    - Execution engine wrapper
    - Tracing and observability
    - Guard rails (token budget, step limits)
    - Error recovery
    - Human-in-the-loop gateway
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        # TODO: Replace in-memory _active_sessions with Redis backend for multi-instance deployments
        self._active_sessions: dict[str, dict[str, Any]] = {}
        self._active_tasks: dict[str, asyncio.Task[Any]] = {}
        self._trace_managers: dict[str, TraceManager] = {}
        self._budget_controllers: dict[str, BudgetController] = {}
        self._recovery_managers: dict[str, RecoveryManager] = {}
        self._guard_chains: dict[str, GuardRailChain] = {}

    async def execute(
        self,
        graph: Any,
        initial_state: JobAgentState | None,
        config: dict[str, Any] | None = None,
    ) -> JobAgentState:
        """Execute a graph with harness protections.

        Args:
            graph: Compiled LangGraph
            initial_state: Initial workflow state
            config: Execution configuration

        Returns:
            Final workflow state
        """
        config = config or {}
        # Supervisor loop needs higher recursion limit:
        # each agent = 2 steps (supervisor + agent), 8 agents = 16+ steps
        config.setdefault("recursion_limit", 100)
        configurable = config.get("configurable", {})
        session_id = (
            initial_state.get("session_id", "default")
            if initial_state is not None
            else str(configurable.get("thread_id", "default"))
        )

        # Initialize harness components for this session
        trace_manager = TraceManager()
        budget_controller = BudgetController()
        recovery_manager = RecoveryManager()
        guard_chain = GuardRailChain()

        self._trace_managers[session_id] = trace_manager
        self._budget_controllers[session_id] = budget_controller
        self._recovery_managers[session_id] = recovery_manager
        self._guard_chains[session_id] = guard_chain

        # Track session
        self._active_sessions[session_id] = {
            "status": "running",
            "steps": 0,
            "tokens_used": 0,
            "started_at": datetime.now(UTC).isoformat(),
        }

        try:
            # --- Pre-execution: check budget ---
            try:
                budget_status = budget_controller.get_status()
                if budget_status.should_terminate:
                    raise GuardRailViolation(
                        "budget",
                        f"Budget exceeded before execution: {budget_status.message}",
                    )
            except GuardRailViolation:
                raise
            except Exception as e:
                logger.warning(
                    "Budget pre-check failed for session %s: %s", session_id, e
                )

            # --- Wrap graph invocation as asyncio.Task for cancellation ---
            async def _invoke_graph() -> Any:
                # Execute graph with recovery wrapping
                async def _graph_call() -> Any:
                    return await graph.ainvoke(initial_state, config)

                return await recovery_manager.execute_with_recovery(
                    _graph_call, node_name="graph_invoke"
                )

            task = asyncio.create_task(_invoke_graph())
            self._active_tasks[session_id] = task

            try:
                result = await task
            except asyncio.CancelledError:
                self._active_sessions[session_id]["status"] = "cancelled"
                raise
            finally:
                self._active_tasks.pop(session_id, None)

            # --- Update session tracking data from trace manager ---
            try:
                logs = trace_manager.get_logs()
                self._active_sessions[session_id]["steps"] = len(logs)
                self._active_sessions[session_id]["tokens_used"] = (
                    trace_manager.get_total_tokens()
                )
            except Exception as e:
                logger.warning(
                    "Failed to update session tracking data: %s", e
                )

            # Update session status
            self._active_sessions[session_id]["status"] = "completed"
            self._active_sessions[session_id]["finished_at"] = (
                datetime.now(UTC).isoformat()
            )

            return cast(JobAgentState, result)

        except asyncio.CancelledError:
            self._active_sessions[session_id]["status"] = "cancelled"
            self._active_sessions[session_id]["finished_at"] = (
                datetime.now(UTC).isoformat()
            )
            raise
        except Exception as e:
            self._active_sessions[session_id]["status"] = "error"
            self._active_sessions[session_id]["error"] = str(e)
            self._active_sessions[session_id]["finished_at"] = (
                datetime.now(UTC).isoformat()
            )
            raise
        finally:
            await self._flush_trace(session_id)
            self._schedule_cleanup(session_id)

    async def execute_node(
        self,
        node_name: str,
        state: JobAgentState,
        operation: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Apply node-level guards, traces, and token accounting."""
        session_id = str(state.get("session_id", "default"))
        guard_chain = self._guard_chains.get(session_id)
        trace_manager = self._trace_managers.get(session_id)
        budget = self._budget_controllers.get(session_id)
        if guard_chain is None or trace_manager is None or budget is None:
            return await operation()

        # A HITL resume creates a fresh runtime budget controller. Seed it from
        # the checkpointed cumulative usage so pausing cannot reset the budget.
        checkpoint_usage = state.get("token_usage", {})
        checkpoint_tokens = (
            int(checkpoint_usage.get("total_tokens", 0) or 0)
            if isinstance(checkpoint_usage, dict)
            else 0
        )
        if budget.tokens_used == 0 and checkpoint_tokens > 0:
            budget.record_usage(checkpoint_tokens, "checkpoint")
            token_guard = guard_chain.get_guard("token_budget")
            if isinstance(token_guard, TokenBudgetGuard) and token_guard.tokens_used == 0:
                token_guard.add_usage(checkpoint_tokens)

        # The graph itself knows which node is executing, but previously that
        # information stayed inside the runtime until the whole workflow had
        # finished.  Publish it before invoking the Agent so the SSE endpoint
        # can update the chat UI in real time.
        await self._publish_node_activity(session_id, node_name, "running")
        guard_chain.before_node(node_name, dict(state))
        try:
            sid = UUID(session_id)
        except (TypeError, ValueError):
            sid = None
        try:
            user_id = UUID(str(state.get("user_id", "")))
        except (TypeError, ValueError):
            user_id = None
        span_id = trace_manager.on_node_start(
            node_name=node_name,
            agent_name=node_name,
            input_data=dict(state),
            session_id=sid,
            user_id=user_id,
        )
        try:
            result = await operation()
            if "error_state" not in result:
                result["error_state"] = None
            guard_chain.after_node(node_name, dict(state), result)
            usage = result.get("token_usage", {})
            tokens = int(usage.get("total_tokens", 0) or 0) if isinstance(usage, dict) else 0
            budget_status = budget.record_usage(tokens, node_name)
            if budget_status.should_degrade:
                result["use_fallback_model"] = True
            trace_manager.on_node_end(span_id, result, usage)
            if budget_status.should_terminate:
                raise GuardRailViolation("budget", budget_status.message)
            await self._publish_node_activity(session_id, node_name, "completed")
            return result
        except Exception as exc:
            if span_id in trace_manager._active_spans:
                trace_manager.on_node_error(span_id, exc)
            await self._publish_node_activity(session_id, node_name, "failed")
            raise

    async def _publish_node_activity(
        self, session_id: str, node_name: str, activity_status: str
    ) -> None:
        """Mirror the currently executing graph node into the session store.

        This is deliberately best-effort: observability must never prevent an
        Agent from running.  A missing record is normal when the user deletes
        a session while its background task is winding down.
        """
        if session_id not in self._active_sessions:
            return

        try:
            from job_agent_os.core.utils import utc_now
            from job_agent_os.services.session_store import get_session_store

            store = get_session_store()
            info = await store.get(session_id)
            if info is None:
                return

            progress = dict(info.get("progress") or {})
            completed_steps = list(progress.get("completed_steps") or [])
            if activity_status == "completed" and node_name not in completed_steps:
                completed_steps.append(node_name)

            is_running = activity_status == "running"
            progress.update(
                {
                    "completed_steps": completed_steps,
                    "current_step": node_name if is_running else None,
                    "active_agent": node_name if is_running else None,
                    "active_agent_status": activity_status,
                }
            )
            await store.update(
                session_id,
                current_phase=node_name,
                progress={
                    "completed_steps": progress["completed_steps"],
                    "current_step": progress["current_step"],
                    "active_agent": progress["active_agent"],
                    "active_agent_status": progress["active_agent_status"],
                },
                updated_at=utc_now().isoformat(),
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to publish activity for session %s, node %s",
                session_id,
                node_name,
                exc_info=True,
            )

    async def _flush_trace(self, session_id: str) -> None:
        trace_manager = self._trace_managers.get(session_id)
        if trace_manager is None or not trace_manager.get_logs():
            return
        try:
            from job_agent_os.db.session import get_session_factory

            async with get_session_factory()() as db:
                trace_manager.db = db
                await trace_manager.flush_to_db()
                await db.commit()
        except Exception:
            logger.exception("Failed to persist traces for session %s", session_id)

    def get_session_status(self, session_id: str) -> dict[str, Any]:
        """Get session execution status."""
        return self._active_sessions.get(session_id, {"status": "not_found"})

    def cancel_session(self, session_id: str) -> bool:
        """Cancel an active session."""
        if session_id in self._active_sessions:
            self._active_sessions[session_id]["status"] = "cancelled"
            # Cancel the running asyncio task if it exists
            task = self._active_tasks.get(session_id)
            if task is not None and not task.done():
                task.cancel()
            return True
        return False

    def _schedule_cleanup(self, session_id: str) -> None:
        """Schedule removal of completed/failed/cancelled sessions after TTL."""
        status = self._active_sessions.get(session_id, {}).get("status", "")
        if status not in ("completed", "failed", "error", "cancelled"):
            return

        async def _cleanup() -> None:
            await asyncio.sleep(_SESSION_TTL_SECONDS)
            current = self._active_sessions.get(session_id, {})
            if current.get("status") in (
                "completed",
                "failed",
                "error",
                "cancelled",
            ):
                self._active_sessions.pop(session_id, None)
                self._trace_managers.pop(session_id, None)
                self._budget_controllers.pop(session_id, None)
                self._recovery_managers.pop(session_id, None)
                self._guard_chains.pop(session_id, None)
                logger.debug("Cleaned up session %s after TTL", session_id)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_cleanup())
        except RuntimeError:
            # No running loop; clean up synchronously
            self._active_sessions.pop(session_id, None)
            self._trace_managers.pop(session_id, None)
            self._budget_controllers.pop(session_id, None)
            self._recovery_managers.pop(session_id, None)
            self._guard_chains.pop(session_id, None)


# Global runtime instance
_runtime: HarnessRuntime | None = None


def get_harness_runtime() -> HarnessRuntime:
    """Get or create the harness runtime instance."""
    global _runtime
    if _runtime is None:
        _runtime = HarnessRuntime()
    return _runtime
