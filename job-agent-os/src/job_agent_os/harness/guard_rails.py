"""Guard rails (Token/Steps/Loop/Format validation).

Middleware chain with before_node() / after_node() hooks.
Guards:
- TokenBudgetGuard: block when token budget exceeded
- StepLimitGuard: block when max steps reached
- LoopDetectionGuard: detect same node repeated execution
- OutputValidationGuard: validate output format
"""

from collections import defaultdict
from typing import Any

from job_agent_os.settings import get_settings


class GuardRailViolation(Exception):
    """Raised when a guard rail is violated."""

    def __init__(self, guard_name: str, message: str) -> None:
        self.guard_name = guard_name
        super().__init__(f"[{guard_name}] {message}")


class BaseGuard:
    """Base guard interface."""

    name: str = "base"

    def before_node(self, node_name: str, state: dict) -> None:
        """Called before node execution. Raise GuardRailViolation to block."""
        pass

    def after_node(self, node_name: str, state: dict, result: dict) -> None:
        """Called after node execution."""
        pass

    def reset(self) -> None:
        """Reset guard state."""
        pass


class TokenBudgetGuard(BaseGuard):
    """Blocks execution when token budget is exceeded."""

    name = "token_budget"

    def __init__(self, max_tokens: int | None = None) -> None:
        settings = get_settings()
        self.max_tokens = max_tokens or settings.harness_token_budget_per_session
        self.tokens_used: int = 0

    def add_usage(self, tokens: int) -> None:
        """Record token usage."""
        self.tokens_used += tokens

    def before_node(self, node_name: str, state: dict) -> None:
        if self.tokens_used >= self.max_tokens:
            raise GuardRailViolation(
                self.name,
                f"Token budget exceeded: {self.tokens_used}/{self.max_tokens}",
            )

    def after_node(self, node_name: str, state: dict, result: dict) -> None:
        # Extract token usage from result if available
        token_usage = result.get("token_usage", {})
        if isinstance(token_usage, dict):
            self.add_usage(token_usage.get("total_tokens", 0))

    def reset(self) -> None:
        self.tokens_used = 0

    @property
    def usage_ratio(self) -> float:
        return self.tokens_used / self.max_tokens if self.max_tokens > 0 else 0.0


class StepLimitGuard(BaseGuard):
    """Blocks execution when max steps is reached."""

    name = "step_limit"

    def __init__(self, max_steps: int | None = None) -> None:
        settings = get_settings()
        self.max_steps = max_steps or settings.harness_max_steps
        self.step_count: int = 0

    def before_node(self, node_name: str, state: dict) -> None:
        if self.step_count >= self.max_steps:
            raise GuardRailViolation(
                self.name,
                f"Step limit exceeded: {self.step_count}/{self.max_steps}",
            )

    def after_node(self, node_name: str, state: dict, result: dict) -> None:
        self.step_count += 1

    def reset(self) -> None:
        self.step_count = 0


class LoopDetectionGuard(BaseGuard):
    """Detects when the same node is executed repeatedly."""

    name = "loop_detection"

    def __init__(self, threshold: int | None = None) -> None:
        settings = get_settings()
        self.threshold = threshold or settings.harness_loop_detection_threshold
        self._node_counts: dict[str, int] = defaultdict(int)

    def before_node(self, node_name: str, state: dict) -> None:
        self._node_counts[node_name] += 1
        if self._node_counts[node_name] > self.threshold:
            raise GuardRailViolation(
                self.name,
                f"Loop detected: node '{node_name}' executed {self._node_counts[node_name]} times "
                f"(threshold: {self.threshold})",
            )

    def reset(self) -> None:
        self._node_counts = defaultdict(int)


class OutputValidationGuard(BaseGuard):
    """Validates node output format."""

    name = "output_validation"

    def __init__(self, required_fields: list[str] | None = None) -> None:
        self.required_fields = required_fields or ["current_phase"]

    def after_node(self, node_name: str, state: dict, result: dict) -> None:
        if not isinstance(result, dict):
            raise GuardRailViolation(
                self.name,
                f"Node '{node_name}' output is not a dict: {type(result).__name__}",
            )
        # Soft validation: log warning but don't block
        # (strict mode can raise GuardRailViolation)


class GuardRailChain:
    """Middleware chain that runs all guards in sequence."""

    def __init__(self, guards: list[BaseGuard] | None = None) -> None:
        if guards is None:
            guards = [
                TokenBudgetGuard(),
                StepLimitGuard(),
                LoopDetectionGuard(),
                OutputValidationGuard(),
            ]
        self.guards = guards

    def before_node(self, node_name: str, state: dict) -> None:
        """Run all guards before node execution."""
        for guard in self.guards:
            guard.before_node(node_name, state)

    def after_node(self, node_name: str, state: dict, result: dict) -> None:
        """Run all guards after node execution."""
        for guard in self.guards:
            guard.after_node(node_name, state, result)

    def reset(self) -> None:
        """Reset all guards."""
        for guard in self.guards:
            guard.reset()

    def get_guard(self, name: str) -> BaseGuard | None:
        """Get a specific guard by name."""
        for guard in self.guards:
            if guard.name == name:
                return guard
        return None
