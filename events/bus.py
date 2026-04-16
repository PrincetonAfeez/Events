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