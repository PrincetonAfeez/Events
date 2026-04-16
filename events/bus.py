from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import count

from .handlers import Handler
from .models import Event, Severity


@dataclass(slots=True)
class Subscription:
    subscription_id: str
    name: str
    handler: Handler
    event_types: frozenset[str]
    severities: frozenset[Severity]

    def matches(self, event: Event) -> bool:
        event_type_match = not self.event_types or event.event_type in self.event_types
        severity_match = not self.severities or event.severity in self.severities
        return event_type_match and severity_match

@dataclass(slots=True)
class _SuppressionState:
    timestamps: deque[datetime] = field(default_factory=deque)
    summary_emitted: bool = False
    suppressed_count: int = 0


class EventBus:
    SUMMARY_EVENT_TYPE = "suppression_summary"

    def __init__(
        self,
        *,
        max_history: int = 100,
        dedup_threshold: int = 3,
        dedup_window: timedelta = timedelta(seconds=60),
    ) -> None:
        if max_history <= 0:
            raise ValueError("max_history must be greater than zero.")
        if dedup_threshold <= 0:
            raise ValueError("dedup_threshold must be greater than zero.")
        if dedup_window.total_seconds() <= 0:
            raise ValueError("dedup_window must be greater than zero.")

        self.max_history = max_history
        self.dedup_threshold = dedup_threshold
        self.dedup_window = dedup_window
        self._history: deque[Event] = deque(maxlen=max_history)
        self._subscriptions: dict[str, Subscription] = {}
        self._suppression_windows: dict[tuple[str, str], _SuppressionState] = {}
        self._sequence = count(1)

    @property
    def history(self) -> tuple[Event, ...]:
        return tuple(self._history)

    def restore_history_snapshot(self, events: list[Event] | tuple[Event, ...]) -> None:
        self._history.clear()
        self._history.extend(events)