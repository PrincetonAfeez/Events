
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