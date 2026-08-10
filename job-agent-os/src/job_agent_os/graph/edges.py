"""Routing functions for Supervisor-based graph."""

from job_agent_os.graph.state import JobAgentState


def route_from_supervisor(state: JobAgentState) -> str:
    """Route to the next agent based on Supervisor's decision.

    Reads state["next_agent"] set by the supervisor node.
    Returns "__end__" if the task is finished or no valid agent is specified.
    """
    if state.get("is_finished", False):
        return "__end__"

    next_agent = state.get("next_agent", "__end__")

    # Validate against known agents
    valid_agents = {
        "intent", "search", "web_search", "parse",
        "match", "resume", "interview", "tracker",
    }

    if next_agent in valid_agents:
        return next_agent

    return "__end__"