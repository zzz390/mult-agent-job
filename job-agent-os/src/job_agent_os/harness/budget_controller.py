"""Token budget controller.

Real-time token counting with:
- 80% warning threshold
- 100% degradation to smaller model or termination
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum

from job_agent_os.settings import get_settings


class BudgetLevel(Enum):
    """Budget status levels."""

    NORMAL = "normal"
    WARNING = "warning"  # 80% used
    CRITICAL = "critical"  # 95% used
    EXCEEDED = "exceeded"  # 100% used


@dataclass
class BudgetStatus:
    """Current budget status."""

    total_budget: int
    tokens_used: int
    level: BudgetLevel
    usage_ratio: float
    should_degrade: bool = False
    should_terminate: bool = False
    message: str = ""


class BudgetController:
    """Controls token budget for a session.

    Tracks token usage and triggers:
    - Warning at 80% usage
    - Model degradation at 95% usage
    - Termination at 100% usage
    """

    WARNING_THRESHOLD = 0.80
    DEGRADE_THRESHOLD = 0.95
    EXCEED_THRESHOLD = 1.00

    def __init__(self, budget: int | None = None) -> None:
        settings = get_settings()
        self.total_budget = budget or settings.harness_token_budget_per_session
        self.tokens_used: int = 0
        self._degraded: bool = False
        self._history: deque[dict] = deque(maxlen=1000)

    def record_usage(self, tokens: int, node_name: str = "") -> BudgetStatus:
        """Record token usage and return current status."""
        self.tokens_used += tokens
        self._history.append({"node": node_name, "tokens": tokens})
        return self.get_status()

    def get_status(self) -> BudgetStatus:
        """Get current budget status."""
        ratio = self.tokens_used / self.total_budget if self.total_budget > 0 else 1.0

        if ratio >= self.EXCEED_THRESHOLD:
            level = BudgetLevel.EXCEEDED
            message = f"Token budget exceeded: {self.tokens_used}/{self.total_budget}"
            self._degraded = True
            return BudgetStatus(
                total_budget=self.total_budget,
                tokens_used=self.tokens_used,
                level=level,
                usage_ratio=ratio,
                should_degrade=True,
                should_terminate=True,
                message=message,
            )
        elif ratio >= self.DEGRADE_THRESHOLD:
            level = BudgetLevel.CRITICAL
            message = f"Token budget critical ({ratio:.0%}), degrading to smaller model"
            self._degraded = True
            return BudgetStatus(
                total_budget=self.total_budget,
                tokens_used=self.tokens_used,
                level=level,
                usage_ratio=ratio,
                should_degrade=True,
                should_terminate=False,
                message=message,
            )
        elif ratio >= self.WARNING_THRESHOLD:
            level = BudgetLevel.WARNING
            message = f"Token budget warning: {ratio:.0%} used"
            return BudgetStatus(
                total_budget=self.total_budget,
                tokens_used=self.tokens_used,
                level=level,
                usage_ratio=ratio,
                should_degrade=False,
                should_terminate=False,
                message=message,
            )
        else:
            return BudgetStatus(
                total_budget=self.total_budget,
                tokens_used=self.tokens_used,
                level=BudgetLevel.NORMAL,
                usage_ratio=ratio,
            )

    @property
    def is_degraded(self) -> bool:
        """Whether the controller has triggered model degradation."""
        return self._degraded

    @property
    def remaining_budget(self) -> int:
        """Remaining token budget."""
        return max(0, self.total_budget - self.tokens_used)

    def should_use_fallback_model(self) -> bool:
        """Whether to use the fallback (smaller) model."""
        return self._degraded

    def reset(self) -> None:
        """Reset budget for a new session."""
        self.tokens_used = 0
        self._degraded = False
        self._history = deque(maxlen=1000)
