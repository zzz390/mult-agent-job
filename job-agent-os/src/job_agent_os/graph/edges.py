"""Conditional edges and routing functions."""

from job_agent_os.graph.state import JobAgentState


def should_clarify(state: JobAgentState) -> str:
    """Route after intent parsing - check if clarification is needed."""
    if state.get("clarification_needed", False):
        return "human_clarify"
    return "search"


def after_human_clarify(state: JobAgentState) -> str:
    """Route after human clarification."""
    # After user provides clarification, go back to intent parsing
    return "intent"


def after_human_review(state: JobAgentState) -> str:
    """Route after human review of recommendations."""
    feedback = state.get("human_feedback", "")
    if feedback and "reject" in feedback.lower():
        return "match"  # Re-run matching with adjusted weights
    return "resume"


def after_resume_approval(state: JobAgentState) -> str:
    """Route after resume approval."""
    if state.get("resume_approved", False):
        return "interview"
    return "resume"  # Re-optimize resume
