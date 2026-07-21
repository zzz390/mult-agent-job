"""Node registry (Agent -> Node mapping)."""

from job_agent_os.agents.intent_agent import intent_agent
from job_agent_os.agents.interview_agent import interview_agent
from job_agent_os.agents.match_agent import match_agent
from job_agent_os.agents.parse_agent import parse_agent
from job_agent_os.agents.resume_agent import resume_agent
from job_agent_os.agents.search_agent import search_agent
from job_agent_os.agents.tracker_agent import tracker_agent
from job_agent_os.graph.state import JobAgentState


async def intent_node(state: JobAgentState) -> dict:
    """Intent Agent node - parse user intent."""
    return await intent_agent.execute(state)


async def search_node(state: JobAgentState) -> dict:
    """Search Agent node - search job platforms."""
    return await search_agent.execute(state)


async def parse_node(state: JobAgentState) -> dict:
    """Parse Agent node - parse job descriptions."""
    return await parse_agent.execute(state)


async def match_node(state: JobAgentState) -> dict:
    """Match Agent node - match jobs with resume."""
    return await match_agent.execute(state)


async def resume_node(state: JobAgentState) -> dict:
    """Resume Agent node - optimize resume."""
    return await resume_agent.execute(state)


async def interview_node(state: JobAgentState) -> dict:
    """Interview Agent node - generate interview questions."""
    return await interview_agent.execute(state)


async def tracker_node(state: JobAgentState) -> dict:
    """Tracker Agent node - manage applications."""
    return await tracker_agent.execute(state)


async def human_clarify_node(state: JobAgentState) -> dict:
    """Human clarification node - wait for user input."""
    return {"current_phase": "human_clarify"}


async def human_review_node(state: JobAgentState) -> dict:
    """Human review node - wait for recommendation approval."""
    return {"current_phase": "human_review"}


async def human_approve_node(state: JobAgentState) -> dict:
    """Human approval node - wait for resume approval."""
    return {"current_phase": "human_approve"}
