"""Event bus (in-process pub/sub)."""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Coroutine
from uuid import UUID, uuid4

# Event handler type
EventHandler = Callable[["Event"], Coroutine[Any, Any, None]]


@dataclass
class Event:
    """Base event class."""

    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_type: str = ""


@dataclass
class SessionCreated(Event):
    """Session created event."""

    event_type: str = "session_created"
    session_id: UUID | None = None
    user_id: UUID | None = None
    intent: str = ""


@dataclass
class PhaseChanged(Event):
    """Phase changed event."""

    event_type: str = "phase_changed"
    session_id: UUID | None = None
    from_phase: str = ""
    to_phase: str = ""


@dataclass
class ApprovalRequested(Event):
    """Approval requested event."""

    event_type: str = "approval_requested"
    approval_id: UUID | None = None
    session_id: UUID | None = None
    approval_type: str = ""
    title: str = ""


@dataclass
class AgentCompleted(Event):
    """Agent completed event."""

    event_type: str = "agent_completed"
    session_id: UUID | None = None
    agent_name: str = ""
    duration_ms: int = 0
    status: str = "success"


class EventBus:
    """In-process event bus with async handler support."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event type."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type."""
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribed handlers."""
        handlers = self._handlers.get(event.event_type, [])
        if handlers:
            await asyncio.gather(
                *(handler(event) for handler in handlers),
                return_exceptions=True,
            )

    def clear(self) -> None:
        """Clear all handlers."""
        self._handlers.clear()


# Global event bus instance
event_bus = EventBus()
