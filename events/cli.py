from __future__ import annotations

import argparse
import cmd
import shlex
from datetime import timedelta

from .alert_manager import AlertManager
from .bus import EventBus, Subscription
from .handlers import AlertHandler, ConsoleHandler, LogHandler
from .models import AlertState, Event, Severity, format_alert, format_event


class _CommandParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


class EventShell(cmd.Cmd):
    intro = "Vault OS Event Engine. Type 'help' to list commands."
    prompt = "events> "

    def __init__(self) -> None:
        super().__init__()
        self.alert_manager = AlertManager()
        self.bus = EventBus(max_history=50, dedup_threshold=3, dedup_window=timedelta(seconds=60))
        self.log_handler = LogHandler()
        self._available_handlers = {
            "console": ConsoleHandler(self._emit_line),
            "log": self.log_handler,
            "alert": AlertHandler(self.alert_manager),
        }
        self.bus.subscribe(self._available_handlers["console"], name="console")
        self.bus.subscribe(self._available_handlers["log"], name="log")
        self.bus.subscribe(
            self._available_handlers["alert"],
            name="alert",
            severities=[Severity.WARNING, Severity.CRITICAL],
        )
    
    def emptyline(self) -> None:
        return None
    
    def default(self, line: str) -> None:
        self._emit_line(f"Unknown command: {line}. Type 'help' for available commands.")















def main() -> int:
    shell = EventShell()
    shell.cmdloop()
    return 0
