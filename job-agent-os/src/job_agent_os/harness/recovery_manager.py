"""Error recovery and checkpoint resume.

Strategies:
- Exponential backoff retry (1s, 2s, 4s)
- Checkpoint rollback
- Model degradation (deepseek-chat -> fallback)
- Platform unavailability skip
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from job_agent_os.settings import get_settings


class RecoveryStrategy(Enum):
    """Available recovery strategies."""

    RETRY = "retry"
    ROLLBACK = "rollback"
    DEGRADE_MODEL = "degrade_model"
    SKIP = "skip"
    ABORT = "abort"


@dataclass
class RecoveryAction:
    """A recovery action to take."""

    strategy: RecoveryStrategy
    reason: str
    retry_delay: float = 0.0
    fallback_model: str | None = None
    skip_platform: str | None = None


@dataclass
class FailureRecord:
    """Record of a failure."""

    node_name: str
    error: str
    error_type: str
    attempt: int
    timestamp: float = 0.0


class RecoveryManager:
    """Manages error recovery for agent execution.

    Implements:
    - Exponential backoff retry (1s, 2s, 4s)
    - Model degradation after repeated failures
    - Platform skip for external service failures
    - Abort after max retries exhausted
    """

    BACKOFF_BASE = 1.0  # seconds
    BACKOFF_MULTIPLIER = 2.0

    def __init__(self, max_retries: int | None = None) -> None:
        settings = get_settings()
        self.max_retries = max_retries or settings.harness_max_retries
        self._failure_counts: dict[str, int] = {}
        self._failure_history: list[FailureRecord] = []
        self._degraded: bool = False
        self._skipped_platforms: set[str] = set()

    def determine_recovery(
        self, node_name: str, error: Exception, attempt: int
    ) -> RecoveryAction:
        """Determine the recovery strategy for a failure.

        Args:
            node_name: Name of the failed node
            error: The exception that occurred
            attempt: Current attempt number (1-based)

        Returns:
            RecoveryAction describing what to do
        """
        self._failure_counts[node_name] = self._failure_counts.get(node_name, 0) + 1
        failure_count = self._failure_counts[node_name]

        self._failure_history.append(
            FailureRecord(
                node_name=node_name,
                error=str(error),
                error_type=type(error).__name__,
                attempt=attempt,
            )
        )

        # Check if it's a platform/external service error
        if self._is_platform_error(error):
            platform = self._extract_platform(node_name)
            if platform:
                self._skipped_platforms.add(platform)
                return RecoveryAction(
                    strategy=RecoveryStrategy.SKIP,
                    reason=f"Platform '{platform}' unavailable, skipping",
                    skip_platform=platform,
                )

        # Retry with exponential backoff
        if attempt < self.max_retries:
            delay = self.BACKOFF_BASE * (self.BACKOFF_MULTIPLIER ** (attempt - 1))
            return RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                reason=f"Retry {attempt}/{self.max_retries} after {delay}s",
                retry_delay=delay,
            )

        # After max retries: try model degradation
        if not self._degraded and failure_count >= self.max_retries:
            self._degraded = True
            settings = get_settings()
            return RecoveryAction(
                strategy=RecoveryStrategy.DEGRADE_MODEL,
                reason=f"Max retries reached, degrading to fallback model",
                fallback_model=settings.openai_model_fallback,
            )

        # Final: abort
        return RecoveryAction(
            strategy=RecoveryStrategy.ABORT,
            reason=f"Recovery exhausted after {failure_count} failures on '{node_name}'",
        )

    async def execute_with_recovery(
        self,
        func: Callable,
        node_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a function with automatic recovery.

        Args:
            func: Async function to execute
            node_name: Name for tracking

        Returns:
            Function result

        Raises:
            Last exception if all recovery fails
        """
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 2):  # +1 for degradation attempt
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                action = self.determine_recovery(node_name, e, attempt)

                if action.strategy == RecoveryStrategy.RETRY:
                    await asyncio.sleep(action.retry_delay)
                    continue
                elif action.strategy == RecoveryStrategy.DEGRADE_MODEL:
                    # Signal caller to use fallback model
                    kwargs["_use_fallback"] = True
                    continue
                elif action.strategy == RecoveryStrategy.SKIP:
                    return None  # Skip this node/platform
                elif action.strategy == RecoveryStrategy.ABORT:
                    break

        raise last_error  # type: ignore[misc]

    def is_platform_skipped(self, platform: str) -> bool:
        """Check if a platform has been skipped."""
        return platform in self._skipped_platforms

    @property
    def is_degraded(self) -> bool:
        """Whether model degradation has been triggered."""
        return self._degraded

    def get_failure_summary(self) -> dict:
        """Get summary of all failures."""
        return {
            "total_failures": len(self._failure_history),
            "by_node": dict(self._failure_counts),
            "skipped_platforms": list(self._skipped_platforms),
            "is_degraded": self._degraded,
        }

    def reset(self) -> None:
        """Reset recovery state."""
        self._failure_counts = {}
        self._failure_history = []
        self._degraded = False
        self._skipped_platforms = set()

    def _is_platform_error(self, error: Exception) -> bool:
        """Check if error is from an external platform."""
        platform_indicators = ["TimeoutError", "ConnectionError", "HTTPStatusError"]
        error_type = type(error).__name__
        return error_type in platform_indicators or "platform" in str(error).lower()

    def _extract_platform(self, node_name: str) -> str | None:
        """Extract platform name from node name."""
        platforms = ["boss", "guopin", "niuke"]
        for p in platforms:
            if p in node_name.lower():
                return p
        return None
