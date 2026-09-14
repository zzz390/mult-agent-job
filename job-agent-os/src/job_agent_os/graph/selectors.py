"""Selectors that keep downstream agents on the same reviewed targets."""

from typing import Any

from job_agent_os.graph.state import JobAgentState


def selected_recommendations(state: JobAgentState) -> list[dict[str, Any]]:
    """Return the reviewed recommendation set, preserving an explicit empty set."""
    approved = state.get("approved_recommendations")
    if approved is not None:
        return [item for item in approved if isinstance(item, dict)]
    return [item for item in state.get("match_results", []) if isinstance(item, dict)]
