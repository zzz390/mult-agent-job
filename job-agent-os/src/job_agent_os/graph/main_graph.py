"""Main workflow graph - Supervisor loop architecture.

Architecture:
    START -> supervisor -> [dynamic route] -> specialist agent -> supervisor -> ... -> END

The Supervisor uses LLM structured output to decide which agent to call next.
Each specialist agent is a ReAct agent that calls tools autonomously.
After each agent completes, control returns to the Supervisor for the next decision.
"""

from langgraph.graph import END, START, StateGraph

from job_agent_os.graph.checkpointer import get_checkpointer
from job_agent_os.graph.edges import route_from_supervisor
from job_agent_os.graph.nodes import (
    intent_node,
    interview_node,
    match_node,
    parse_node,
    resume_node,
    search_node,
    supervisor_node,
    tracker_node,
    web_search_node,
)
from job_agent_os.graph.state import JobAgentState

# All specialist agents that Supervisor can route to
SPECIALIST_AGENTS = [
    "intent",
    "search",
    "web_search",
    "parse",
    "match",
    "resume",
    "interview",
    "tracker",
]


def build_main_graph():  # type: ignore
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
    workflow.add_node("web_search", web_search_node)
    workflow.add_node("parse", parse_node)
    workflow.add_node("match", match_node)
    workflow.add_node("resume", resume_node)
    workflow.add_node("interview", interview_node)
    workflow.add_node("tracker", tracker_node)

    # Entry point: always start with supervisor
    workflow.add_edge(START, "supervisor")

    # Supervisor dynamic routing (core of the architecture)
    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "intent": "intent",
            "search": "search",
            "web_search": "web_search",
            "parse": "parse",
            "match": "match",
            "resume": "resume",
            "interview": "interview",
            "tracker": "tracker",
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
        interrupt_before=["resume"],
    )


# Global compiled graph instance
_main_graph = None


def get_main_graph():  # type: ignore
    """Get or create the main graph instance."""
    global _main_graph
    if _main_graph is None:
        _main_graph = build_main_graph()
    return _main_graph
