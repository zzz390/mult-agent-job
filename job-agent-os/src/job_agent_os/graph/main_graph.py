"""Main workflow graph construction and compilation."""

from langgraph.graph import END, START, StateGraph

from job_agent_os.graph.checkpointer import get_checkpointer
from job_agent_os.graph.edges import (
    after_human_clarify,
    after_human_review,
    after_resume_approval,
    should_clarify,
)
from job_agent_os.graph.nodes import (
    human_approve_node,
    human_clarify_node,
    human_review_node,
    intent_node,
    interview_node,
    match_node,
    parse_node,
    resume_node,
    search_node,
    tracker_node,
)
from job_agent_os.graph.state import JobAgentState


def build_main_graph():  # type: ignore
    """Build and compile the main workflow graph.

    Graph flow:
    START -> intent -> [clarify?] -> search -> parse -> match -> human_review
         -> resume -> human_approve -> interview -> tracker -> END
    """
    # Create state graph
    workflow = StateGraph(JobAgentState)

    # Add nodes
    workflow.add_node("intent", intent_node)
    workflow.add_node("search", search_node)
    workflow.add_node("parse", parse_node)
    workflow.add_node("match", match_node)
    workflow.add_node("resume", resume_node)
    workflow.add_node("interview", interview_node)
    workflow.add_node("tracker", tracker_node)

    # Human-in-the-loop nodes
    workflow.add_node("human_clarify", human_clarify_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("human_approve", human_approve_node)

    # Add edges
    workflow.add_edge(START, "intent")

    # Intent -> conditional (clarify or search)
    workflow.add_conditional_edges(
        "intent",
        should_clarify,
        {
            "human_clarify": "human_clarify",
            "search": "search",
        },
    )

    # Human clarify -> back to intent
    workflow.add_conditional_edges(
        "human_clarify",
        after_human_clarify,
        {"intent": "intent"},
    )

    # Search -> Parse -> Match
    workflow.add_edge("search", "parse")
    workflow.add_edge("parse", "match")

    # Match -> Human review
    workflow.add_edge("match", "human_review")

    # Human review -> conditional (resume or match)
    workflow.add_conditional_edges(
        "human_review",
        after_human_review,
        {
            "resume": "resume",
            "match": "match",
        },
    )

    # Resume -> Human approve
    workflow.add_edge("resume", "human_approve")

    # Human approve -> conditional (interview or resume)
    workflow.add_conditional_edges(
        "human_approve",
        after_resume_approval,
        {
            "interview": "interview",
            "resume": "resume",
        },
    )

    # Interview -> Tracker -> END
    workflow.add_edge("interview", "tracker")
    workflow.add_edge("tracker", END)

    # Compile with checkpointer and interrupt points
    checkpointer = get_checkpointer()

    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_clarify", "human_review", "human_approve"],
    )


# Global compiled graph instance
_main_graph = None


def get_main_graph():  # type: ignore
    """Get or create the main graph instance."""
    global _main_graph
    if _main_graph is None:
        _main_graph = build_main_graph()
    return _main_graph
