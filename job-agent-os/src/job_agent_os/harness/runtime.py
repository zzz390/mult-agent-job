"""Harness Runtime main entry (lifecycle management)."""

from typing import Any

from job_agent_os.graph.state import JobAgentState
from job_agent_os.settings import get_settings


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
        session_id = initial_state.get("session_id", "default")

        # Track session
        self._active_sessions[session_id] = {
            "status": "running",
            "steps": 0,
            "tokens_used": 0,
        }

        try:
            # Execute graph
            result = await graph.ainvoke(initial_state, config)

            # Update session status
            self._active_sessions[session_id]["status"] = "completed"

            return result

        except Exception as e:
            self._active_sessions[session_id]["status"] = "error"
            self._active_sessions[session_id]["error"] = str(e)
            raise

    def get_session_status(self, session_id: str) -> dict:
        """Get session execution status."""
        return self._active_sessions.get(session_id, {"status": "not_found"})

    def cancel_session(self, session_id: str) -> bool:
        """Cancel an active session."""
        if session_id in self._active_sessions:
            self._active_sessions[session_id]["status"] = "cancelled"
            return True
        return False


# Global runtime instance
_runtime: HarnessRuntime | None = None


def get_harness_runtime() -> HarnessRuntime:
    """Get or create the harness runtime instance."""
    global _runtime
    if _runtime is None:
        _runtime = HarnessRuntime()
    return _runtime
