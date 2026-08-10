"""Harness Runtime main entry (lifecycle management)."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from job_agent_os.graph.state import JobAgentState
from job_agent_os.harness.budget_controller import BudgetController
from job_agent_os.harness.guard_rails import GuardRailChain, GuardRailViolation
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
        self._active_sessions: dict[str, Any] = {}
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._trace_managers: dict[str, TraceManager] = {}
        self._budget_controllers: dict[str, BudgetController] = {}
        self._recovery_managers: dict[str, RecoveryManager] = {}
        self._guard_chains: dict[str, GuardRailChain] = {}

    async def execute(
        self,
        graph: Any,
        initial_state: JobAgentState,
        config: dict | None = None,
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
        session_id = initial_state.get("session_id", "default")

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
            "started_at": datetime.now(timezone).isoformat(),
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
                # Guard rails before execution
                try:
                    guard_chain.before_node("__graph_start__", dict(initial_state))
                except GuardRailViolation:
                    raise
                except Exception as e:
                    logger.warning("Guard rail before_node failed: %s", e)

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

            # --- Post-execution: guard rails after node ---
            if isinstance(result, dict):
                try:
                    guard_chain.after_node(
                        "__graph_end__", dict(initial_state), result
                    )
                except GuardRailViolation as e:
                    logger.warning("Guard rail after_node violation: %s", e)
                except Exception as e:
                    logger.warning("Guard rail after_node failed: %s", e)

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
                datetime.now(timezone).isoformat()
            )

            return result

        except asyncio.CancelledError:
            self._active_sessions[session_id]["status"] = "cancelled"
            self._active_sessions[session_id]["finished_at"] = (
                datetime.now(timezone).isoformat()
            )
            raise
        except Exception as e:
            self._active_sessions[session_id]["status"] = "error"
            self._active_sessions[session_id]["error"] = str(e)
            self._active_sessions[session_id]["finished_at"] = (
                datetime.now(timezone).isoformat()
            )
            raise
        finally:
            self._schedule_cleanup(session_id)

    def get_session_status(self, session_id: str) -> dict:
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
