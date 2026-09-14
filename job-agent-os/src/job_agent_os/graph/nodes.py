"""Node registry (Agent -> Node mapping) for Supervisor-based graph."""

from collections.abc import Awaitable, Callable
from typing import Any

from job_agent_os.agents.intent_agent import intent_agent
from job_agent_os.agents.interview_agent import interview_agent
from job_agent_os.agents.match_agent import match_agent
from job_agent_os.agents.resume_agent import resume_agent
from job_agent_os.agents.search_agent import search_agent
from job_agent_os.agents.supervisor import supervisor_agent
from job_agent_os.graph.state import JobAgentState


async def _run_node(
    name: str,
    state: JobAgentState,
    operation: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Run every node through the same tracing/budget/guard boundary."""
    from job_agent_os.harness.runtime import get_harness_runtime

    return await get_harness_runtime().execute_node(name, state, operation)


async def supervisor_node(state: JobAgentState) -> dict[str, Any]:
    """Supervisor node: deterministic routing or exception replanning."""

    async def decide() -> dict[str, Any]:
        decision = await supervisor_agent.decide(state)

        # NOTE: agent_execution_order uses an operator.add reducer, so return
        # only the increment, otherwise entries get duplicated.
        return {
            "current_phase": "supervisor",
            "next_agent": decision.next_agent,
            "task_instruction": decision.task_instruction,
            "supervisor_reasoning": decision.reasoning,
            "is_finished": decision.is_finished,
            "agent_execution_order": [] if decision.is_finished else [decision.next_agent],
        }

    return await _run_node("supervisor", state, decide)


async def intent_node(state: JobAgentState) -> dict[str, Any]:
    """Intent Agent node - parse user intent."""
    return await _run_node("intent", state, lambda: intent_agent.execute(state))


async def search_node(state: JobAgentState) -> dict[str, Any]:
    """Search Agent node - search database and platforms."""
    return await _run_node("search", state, lambda: search_agent.execute(state))


async def match_node(state: JobAgentState) -> dict[str, Any]:
    """Match Agent node - score and rank jobs."""
    return await _run_node("match", state, lambda: match_agent.execute(state))


async def resume_node(state: JobAgentState) -> dict[str, Any]:
    """Resume Agent node - optimize resume."""
    return await _run_node("resume", state, lambda: resume_agent.execute(state))


async def interview_node(state: JobAgentState) -> dict[str, Any]:
    """Interview Agent node - generate questions."""
    return await _run_node("interview", state, lambda: interview_agent.execute(state))
