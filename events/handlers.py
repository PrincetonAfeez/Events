
from __future__ import annotations

from typing import Callable, Protocol

from .alert_manager import AlertManager
from .models import Event, Severity, format_event


class Handler(Protocol):
    def __call__(self, event: Event) -> None: ...

class ConsoleHandler:
    def __init__(self, emit: Callable[[str], None] | None = None) -> None:
        self._emit = emit or print

    def __call__(self, event: Event) -> None:
        self._emit(format_event(event))

class LogHandler:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self.records: list[str] = []

    def __call__(self, event: Event) -> None:
        self.events.append(event)
        self.records.append(format_event(event))

    def tail(self, limit: int | None = None) -> tuple[str, ...]:
        if limit is None or limit >= len(self.records):
            return tuple(self.records)
        return tuple(self.records[-limit:])

    def replace_captured_events(self, events: list[Event], records: list[str]) -> None:
        self.events = list(events)
        self.records = list(records)