"""Global State definition (TypedDict)."""

import operator
from typing import Annotated, Any
from uuid import UUID

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class TokenUsage(TypedDict, total=False):
    """Token usage tracking."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


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
    messages: Annotated[list[BaseMessage], add_messages]

    # === Intent Agent Output ===
    job_query: dict | None  # Structured job query (JobQuery schema)
    clarification_needed: bool
    clarification_question: str | None

    # === Search Agent Output ===
    search_results: Annotated[list[dict], operator.add]  # Raw search results
    search_errors: Annotated[list[dict], operator.add]  # Platform errors
    platforms_searched: Annotated[list[str], operator.add]

    # === Parse Agent Output ===
    parsed_jobs: Annotated[list[dict], operator.add]  # Structured JD list (ParsedJD schema)
    parse_failures: Annotated[list[str], operator.add]  # Failed URLs

    # === Match Agent Output ===
    match_results: Annotated[list[dict], operator.add]  # Sorted match results (MatchScore schema)
    user_profile: dict | None  # User resume profile
    match_threshold: float

    # === Resume Agent Output ===
    optimized_resume: dict | None
    resume_diff: Annotated[list[dict], operator.add]
    resume_approved: bool

    # === Interview Agent Output ===
    interview_questions: Annotated[list[dict], operator.add]

    # === Tracker Agent Output ===
    applications: Annotated[list[dict], operator.add]
    kanban_state: dict[str, list]

    # === Supervisor Decision ===
    next_agent: str  # Supervisor 决定的下一个 Agent
    task_instruction: str  # 给 Agent 的任务指令
    supervisor_reasoning: str  # Supervisor 的推理过程
    is_finished: bool  # 整体任务是否完成
    agent_execution_order: Annotated[list[str], operator.add]  # 记录 Agent 调用顺序（可观测性）

    # === Human-in-the-Loop ===
    pending_approval: dict | None
    human_feedback: str | None

    # === Harness Metadata ===
    execution_log: Annotated[list[dict], operator.add]
    token_usage: TokenUsage
    error_state: ErrorInfo | None
    retry_count: int
