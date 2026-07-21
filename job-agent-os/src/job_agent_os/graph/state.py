"""Global State definition (TypedDict)."""

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
    search_results: list[dict]  # Raw search results
    search_errors: list[dict]  # Platform errors
    platforms_searched: list[str]

    # === Parse Agent Output ===
    parsed_jobs: list[dict]  # Structured JD list (ParsedJD schema)
    parse_failures: list[str]  # Failed URLs

    # === Match Agent Output ===
    match_results: list[dict]  # Sorted match results (MatchScore schema)
    user_profile: dict | None  # User resume profile
    match_threshold: float

    # === Resume Agent Output ===
    optimized_resume: dict | None
    resume_diff: list[dict]
    resume_approved: bool

    # === Interview Agent Output ===
    interview_questions: list[dict]

    # === Tracker Agent Output ===
    applications: list[dict]
    kanban_state: dict[str, list]

    # === Human-in-the-Loop ===
    pending_approval: dict | None
    human_feedback: str | None

    # === Harness Metadata ===
    execution_log: list[dict]
    token_usage: TokenUsage
    error_state: ErrorInfo | None
    retry_count: int
