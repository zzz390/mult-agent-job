"""Full-chain tracing manager.

LangGraph Callback implementation that records each node execution:
- Start/end time, input/output, token usage
- Writes to agent_logs table
- Optional Langfuse integration
"""

import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.models.agent_log import AgentLog


class TraceManager:
    """Manages execution tracing for LangGraph workflows.

    Records each node execution with timing, I/O snapshots,
    token usage, and writes to the agent_logs table.
    """

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db
        self._step_counter: int = 0
        self._active_spans: dict[str, dict] = {}
        self._trace_id: str = str(uuid4())[:16]
        self._logs: list[dict] = []

    def reset(self) -> None:
        """Reset trace state for a new session."""
        self._step_counter = 0
        self._active_spans = {}
        self._trace_id = str(uuid4())[:16]
        self._logs = []

    @property
    def trace_id(self) -> str:
        return self._trace_id

    def on_node_start(
        self,
        node_name: str,
        agent_name: str,
        input_data: dict | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> str:
        """Record node execution start.

        Returns:
            span_id for correlating with on_node_end
        """
        self._step_counter += 1
        span_id = f"{self._trace_id}_{self._step_counter}"

        self._active_spans[span_id] = {
            "span_id": span_id,
            "node_name": node_name,
            "agent_name": agent_name,
            "step_order": self._step_counter,
            "session_id": session_id,
            "user_id": user_id,
            "input_snapshot": self._safe_snapshot(input_data),
            "started_at": datetime.now(UTC),
            "start_time": time.perf_counter(),
        }
        return span_id

    def on_node_end(
        self,
        span_id: str,
        output_data: dict | None = None,
        token_usage: dict | None = None,
        model_name: str | None = None,
        status: str = "success",
        error_message: str | None = None,
        error_type: str | None = None,
    ) -> dict:
        """Record node execution end.

        Args:
            error_type: Optional exception type name (e.g. ``ValueError``).
                If not provided but ``error_message`` is set, falls back to
                ``"Error"``.

        Returns:
            Complete log entry dict
        """
        span = self._active_spans.pop(span_id, None)
        if not span:
            return {}

        end_time = time.perf_counter()
        duration_ms = int((end_time - span["start_time"]) * 1000)

        # Derive error_type from error_message only as a last resort
        if error_message and not error_type:
            error_type = "Error"

        tokens = token_usage or {}
        log_entry = {
            "trace_id": self._trace_id,
            "session_id": span.get("session_id"),
            "user_id": span.get("user_id"),
            "agent_name": span["agent_name"],
            "node_name": span["node_name"],
            "step_order": span["step_order"],
            "status": status,
            "input_snapshot": span.get("input_snapshot"),
            "output_snapshot": self._safe_snapshot(output_data),
            "model_name": model_name,
            "prompt_tokens": tokens.get("prompt_tokens", 0),
            "completion_tokens": tokens.get("completion_tokens", 0),
            "total_tokens": tokens.get("total_tokens", 0),
            "cost_usd": tokens.get("cost_usd", 0.0),
            "duration_ms": duration_ms,
            "error_message": error_message,
            "error_type": error_type,
            "started_at": span["started_at"],
            "finished_at": datetime.now(UTC),
        }

        self._logs.append(log_entry)
        return log_entry

    def on_node_error(self, span_id: str, error: Exception) -> dict:
        """Record node execution error."""
        return self.on_node_end(
            span_id=span_id,
            status="error",
            error_message=str(error),
            error_type=type(error).__name__,
        )

    def get_logs(self) -> list[dict]:
        """Get all recorded log entries."""
        return self._logs.copy()

    def get_total_tokens(self) -> int:
        """Get total tokens used across all steps."""
        return sum(log.get("total_tokens", 0) for log in self._logs)

    def get_total_duration_ms(self) -> int:
        """Get total execution duration."""
        return sum(log.get("duration_ms", 0) for log in self._logs)

    async def flush_to_db(self) -> int:
        """Write all pending logs to agent_logs table.

        Returns:
            Number of records written
        """
        if not self.db or not self._logs:
            return 0

        count = 0
        skipped: list[dict] = []
        for log in self._logs:
            if not log.get("session_id") or not log.get("user_id"):
                skipped.append(log)
                continue

            agent_log = AgentLog(
                session_id=log["session_id"],
                user_id=log["user_id"],
                trace_id=log["trace_id"],
                agent_name=log["agent_name"],
                node_name=log["node_name"],
                step_order=log["step_order"],
                status=log["status"],
                input_snapshot=log.get("input_snapshot"),
                output_snapshot=log.get("output_snapshot"),
                model_name=log.get("model_name"),
                prompt_tokens=log.get("prompt_tokens", 0),
                completion_tokens=log.get("completion_tokens", 0),
                total_tokens=log.get("total_tokens", 0),
                cost_usd=log.get("cost_usd", 0.0),
                duration_ms=log.get("duration_ms"),
                error_message=log.get("error_message"),
                error_type=log.get("error_type"),
                started_at=log["started_at"],
                finished_at=log.get("finished_at"),
            )
            self.db.add(agent_log)
            count += 1

        if count > 0:
            await self.db.flush()

        # Clear only successfully written logs, retain skipped ones
        self._logs = skipped
        return count

    def _safe_snapshot(self, data: Any) -> dict | None:
        """Create a safe JSON-serializable snapshot of data."""
        if data is None:
            return None
        if isinstance(data, dict):
            # Limit snapshot size
            result = {}
            for k, v in list(data.items())[:20]:
                if isinstance(v, (str, int, float, bool, type(None))):
                    result[k] = v
                elif isinstance(v, list):
                    result[k] = f"[list:{len(v)} items]"
                elif isinstance(v, dict):
                    result[k] = f"{{dict:{len(v)} keys}}"
                else:
                    result[k] = str(type(v).__name__)
            return result
        return {"_raw": str(data)[:500]}
