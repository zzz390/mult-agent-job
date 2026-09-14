"""Global State definition (TypedDict)."""

import operator
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class TokenUsage(TypedDict, total=False):
    """Token usage tracking."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


def add_token_usage(
    existing: TokenUsage | None, new: TokenUsage | None
) -> TokenUsage:
    """Reducer that accumulates token usage across agent steps."""
    merged: TokenUsage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
    }
    for usage in (existing, new):
        if not usage:
            continue
        merged["prompt_tokens"] = merged["prompt_tokens"] + int(usage.get("prompt_tokens", 0) or 0)
        merged["completion_tokens"] = merged["completion_tokens"] + int(usage.get("completion_tokens", 0) or 0)
        merged["total_tokens"] = merged["total_tokens"] + int(usage.get("total_tokens", 0) or 0)
        merged["cost_usd"] = merged["cost_usd"] + float(usage.get("cost_usd", 0.0) or 0.0)
    return merged


class ErrorInfo(TypedDict, total=False):
    """Error information."""

    error_type: str
    error_message: str
    retry_count: int


class JobAgentState(TypedDict, total=False):
    """Global state for the Job Agent workflow.

    This state is shared across all agents in the graph.
    Each agent reads from and writes to specific fields.
    """

    # === Session Metadata ===
    session_id: str
    user_id: str
    current_phase: str
    mode: str
    requested_platforms: list[str]
    resume_id: str | None
    messages: Annotated[list[BaseMessage], add_messages]

    # === Intent Agent Output ===
    job_query: dict[str, Any] | None  # Structured job query (JobQuery schema)
    clarification_needed: bool
    clarification_question: str | None

    # === Search Agent Output ===
    # Current-run products use overwrite semantics. Keeping an ``operator.add``
    # reducer here makes a clarification/retry append stale results forever.
    search_results: list[dict[str, Any]]  # Raw search results
    search_errors: list[dict[str, Any]]  # Platform errors
    platforms_searched: list[str]

    # === Search Agent Internal Parse Output ===
    parsed_jobs: list[dict[str, Any]]  # Structured JD list (ParsedJD schema)
    parse_failures: list[str]  # Failed URLs

    # === Match Agent Output ===
    match_results: list[dict[str, Any]]  # Sorted match results (MatchScore schema)
    # Once recommendation review completes, every downstream agent reads this
    # single source of truth. None means the review has not happened yet;
    # an empty list is an explicit selection of no jobs.
    approved_recommendations: list[dict[str, Any]] | None
    user_profile: dict[str, Any] | None  # User resume profile
    match_threshold: float

    # === Resume Agent Output ===
    optimized_resume: str | dict[str, Any] | None
    resume_diff: list[dict[str, Any]]
    resume_approved: bool

    # === Interview Agent Output ===
    interview_questions: list[dict[str, Any]]

    # === Interview Agent Internal Tracking Output ===
    applications: list[dict[str, Any]]
    kanban_state: dict[str, list[dict[str, Any]]]

    # === Supervisor Decision ===
    next_agent: str  # Supervisor 决定的下一个 Agent
    task_instruction: str  # 给 Agent 的任务指令
    supervisor_reasoning: str  # Supervisor 的推理过程
    is_finished: bool  # 整体任务是否完成
    agent_execution_order: Annotated[list[str], operator.add]  # 记录 Agent 调用顺序（可观测性）

    # === Human-in-the-Loop ===
    pending_approval: dict[str, Any] | None
    human_feedback: str | None

    # === Harness Metadata ===
    execution_log: Annotated[list[dict[str, Any]], operator.add]
    token_usage: Annotated[TokenUsage, add_token_usage]
    error_state: ErrorInfo | None
    retry_count: int
    use_fallback_model: bool
