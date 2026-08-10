"""Node registry (Agent -> Node mapping) for Supervisor-based graph."""

from job_agent_os.agents.intent_agent import intent_agent
from job_agent_os.agents.interview_agent import interview_agent
from job_agent_os.agents.match_agent import match_agent
from job_agent_os.agents.parse_agent import parse_agent
from job_agent_os.agents.resume_agent import resume_agent
from job_agent_os.agents.search_agent import search_agent
from job_agent_os.agents.supervisor import supervisor_agent
from job_agent_os.agents.tracker_agent import tracker_agent
from job_agent_os.agents.web_search_agent import web_search_agent
from job_agent_os.graph.state import JobAgentState


async def supervisor_node(state: JobAgentState) -> dict:
    """Supervisor node: LLM dynamic routing decision."""
    decision = await supervisor_agent.decide(state)

    execution_order = state.get("agent_execution_order", [])
    if not decision.is_finished:
        execution_order = execution_order + [decision.next_agent]

    return {
        "next_agent": decision.next_agent,
        "task_instruction": decision.task_instruction,
        "supervisor_reasoning": decision.reasoning,
        "is_finished": decision.is_finished,
        "agent_execution_order": execution_order,
    }


async def intent_node(state: JobAgentState) -> dict:
    """Intent Agent node - parse user intent."""
    return await intent_agent.execute(state)


async def search_node(state: JobAgentState) -> dict:
    """Search Agent node - search database and platforms."""
    return await search_agent.execute(state)


async def web_search_node(state: JobAgentState) -> dict:
    """Web Search Agent node - search company career sites."""
    return await web_search_agent.execute(state)


async def parse_node(state: JobAgentState) -> dict:
    """Parse Agent node - structure raw JDs."""
    return await parse_agent.execute(state)


async def match_node(state: JobAgentState) -> dict:
    """Match Agent node - score and rank jobs."""
    return await match_agent.execute(state)


async def resume_node(state: JobAgentState) -> dict:
    """Resume Agent node - optimize resume."""
    return await resume_agent.execute(state)


async def interview_node(state: JobAgentState) -> dict:
    """Interview Agent node - generate questions."""
    return await interview_agent.execute(state)


async def tracker_node(state: JobAgentState) -> dict:
    """Tracker Agent node - create applications."""
    return await tracker_agent.execute(state)
