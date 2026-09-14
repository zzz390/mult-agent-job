"""Main workflow graph - Supervisor loop architecture.

Architecture:
    START -> supervisor -> [dynamic route] -> specialist agent -> supervisor -> ... -> END

The Supervisor uses deterministic state transitions for the normal pipeline and
LLM structured output only for exception replanning. Specialists may use ReAct
or direct deterministic/generative execution depending on their responsibility.
After each agent completes, control returns to the Supervisor for the next decision.
"""

from typing import Any

from langgraph.graph import END, START, StateGraph

from job_agent_os.graph.checkpointer import get_checkpointer
from job_agent_os.graph.contracts import CORE_AGENT_NAMES
from job_agent_os.graph.edges import route_from_supervisor
from job_agent_os.graph.nodes import (
    intent_node,
    interview_node,
    match_node,
    resume_node,
    search_node,
    supervisor_node,
)
from job_agent_os.graph.state import JobAgentState

# All specialist agents that Supervisor can route to
SPECIALIST_AGENTS = list(CORE_AGENT_NAMES)


def build_main_graph() -> Any:
    """Build and compile the Supervisor-loop workflow graph.

    Graph flow:
    START -> supervisor -> [route_from_supervisor] -> agent -> supervisor -> ... -> END
    """
    workflow = StateGraph(JobAgentState)

    # Add supervisor node
    workflow.add_node("supervisor", supervisor_node)

    # Add all specialist agent nodes
    workflow.add_node("intent", intent_node)
    workflow.add_node("search", search_node)
    workflow.add_node("match", match_node)
    workflow.add_node("resume", resume_node)
    workflow.add_node("interview", interview_node)

    # Entry point: always start with supervisor
    workflow.add_edge(START, "supervisor")

    # Supervisor dynamic routing (core of the architecture)
    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "intent": "intent",
            "search": "search",
            "match": "match",
            "resume": "resume",
            "interview": "interview",
            "__end__": END,
        },
    )

    # Every specialist agent returns to supervisor after execution
    for agent_name in SPECIALIST_AGENTS:
        workflow.add_edge(agent_name, "supervisor")

    # Compile with checkpointer for session persistence
    checkpointer = get_checkpointer()

    return workflow.compile(
        checkpointer=checkpointer,
        # Recommendations and generated resumes both require explicit review.
        interrupt_before=["resume", "interview"],
    )


# Global compiled graph instance
_main_graph = None


def get_main_graph() -> Any:
    """Get or create the main graph instance."""
    global _main_graph
    if _main_graph is None:
        _main_graph = build_main_graph()
    return _main_graph


def reset_main_graph() -> None:
    """Drop the compiled singleton so it can use a new checkpointer."""
    global _main_graph
    _main_graph = None
