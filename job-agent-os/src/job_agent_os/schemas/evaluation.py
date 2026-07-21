"""Evaluation schemas."""

from pydantic import BaseModel, Field


class AgentEvalMetric(BaseModel):
    """Agent evaluation metric."""

    agent: str
    metric: str
    avg: float
    trend: str | None = None


class EvalReport(BaseModel):
    """Evaluation report."""

    period: dict
    summary: dict
    by_agent: list[AgentEvalMetric] = Field(default_factory=list)


class TokenUsageByAgent(BaseModel):
    """Token usage by agent."""

    agent: str
    tokens: int
    cost_usd: float


class TokenUsageStats(BaseModel):
    """Token usage statistics."""

    total_tokens: int
    total_cost_usd: float
    by_day: list[dict] = Field(default_factory=list)
    by_agent: list[TokenUsageByAgent] = Field(default_factory=list)
    budget_remaining: int
