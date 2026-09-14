"""Runtime contracts shared by the core LangGraph nodes.

The graph state remains a ``TypedDict`` because LangGraph relies on its
reducers, but node boundaries are validated with Pydantic so malformed LLM or
tool output cannot silently poison the next stage.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

type CoreAgentName = Literal[
    "intent",
    "search",
    "match",
    "resume",
    "interview",
]
type RouteName = Literal[
    "intent",
    "search",
    "match",
    "resume",
    "interview",
    "__end__",
]

CORE_AGENT_NAMES: tuple[CoreAgentName, ...] = (
    "intent",
    "search",
    "match",
    "resume",
    "interview",
)


class _NodeOutput(BaseModel):
    model_config = ConfigDict(extra="allow")


class SupervisorNodeOutput(_NodeOutput):
    current_phase: Literal["supervisor"]
    next_agent: RouteName
    task_instruction: str
    supervisor_reasoning: str
    is_finished: bool
    agent_execution_order: list[str]


class IntentNodeOutput(_NodeOutput):
    current_phase: Literal["intent"]
    job_query: dict[str, Any] | None = None
    clarification_needed: bool = False
    clarification_question: str | None = None


class SearchNodeOutput(_NodeOutput):
    current_phase: Literal["search"]
    search_results: list[dict[str, Any]]
    search_errors: list[dict[str, Any]]
    platforms_searched: list[str]
    parsed_jobs: list[dict[str, Any]] | None = None
    parse_failures: list[str] | None = None


class MatchNodeOutput(_NodeOutput):
    current_phase: Literal["match"]
    match_results: list[dict[str, Any]]


class ResumeNodeOutput(_NodeOutput):
    current_phase: Literal["resume"]
    optimized_resume: str | dict[str, Any] | None
    resume_diff: list[dict[str, Any]]


class InterviewNodeOutput(_NodeOutput):
    current_phase: Literal["interview"]
    interview_questions: list[dict[str, Any]]


class FailedNodeOutput(_NodeOutput):
    current_phase: str
    error_state: dict[str, Any]


_OUTPUT_CONTRACTS: dict[str, type[_NodeOutput]] = {
    "supervisor": SupervisorNodeOutput,
    "intent": IntentNodeOutput,
    "search": SearchNodeOutput,
    "match": MatchNodeOutput,
    "resume": ResumeNodeOutput,
    "interview": InterviewNodeOutput,
}


def validate_node_output(node_name: str, result: object) -> None:
    """Raise ``ValidationError`` when a core node violates its contract."""
    if isinstance(result, dict) and result.get("error_state"):
        FailedNodeOutput.model_validate(result)
        return

    contract = _OUTPUT_CONTRACTS.get(node_name)
    if contract is not None:
        contract.model_validate(result)
        return

    _NodeOutput.model_validate(result)


__all__ = [
    "CORE_AGENT_NAMES",
    "CoreAgentName",
    "RouteName",
    "validate_node_output",
]
