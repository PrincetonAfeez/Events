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

    def do_publish(self, arg: str) -> None:
        if not arg.strip():
            source = input("Source: ").strip()
            event_type = input("Event type: ").strip()
            severity = input("Severity (INFO/WARNING/CRITICAL): ").strip()
            message = input("Message: ").strip()
        else:
            parser = _CommandParser(prog="publish", add_help=False)
            parser.add_argument("source")
            parser.add_argument("event_type")
            parser.add_argument("severity")
            parser.add_argument("message", nargs="+")
            try:
                args = parser.parse_args(shlex.split(arg))
            except ValueError as error:
                self._emit_line(f"publish error: {error}")
                return

            source = args.source
            event_type = args.event_type
            severity = args.severity
            message = " ".join(args.message)

        try:
            event = Event(
                source=source,
                event_type=event_type,
                severity=Severity.from_value(severity),
                message=message,
            )
        except ValueError as error:
            self._emit_line(f"publish error: {error}")
            return

        dispatched = self.bus.publish(event)
        if not dispatched:
            self._emit_line("Event suppressed by deduplication.")

    def do_handlers(self, arg: str) -> None:
        del arg
        self._emit_line("Available handlers:")
        for name in sorted(self._available_handlers):
            self._emit_line(f"  - {name}")

        subscriptions = self.bus.list_subscriptions()
        self._emit_line("Active subscriptions:")
        if not subscriptions:
            self._emit_line("  (none)")
            return
        for subscription in subscriptions:
            self._emit_line(f"  - {self._describe_subscription(subscription)}")

    def do_subscribe(self, arg: str) -> None:
        parser = _CommandParser(prog="subscribe", add_help=False)
        parser.add_argument("handler")
        parser.add_argument("--type", dest="event_types", action="append", default=[])
        parser.add_argument("--severity", dest="severities", action="append", default=[])

        try:
            args = parser.parse_args(shlex.split(arg))
        except ValueError as error:
            self._emit_line(f"subscribe error: {error}")
            return

        handler = self._available_handlers.get(args.handler)
        if handler is None:
            available = ", ".join(sorted(self._available_handlers))
            self._emit_line(f"subscribe error: unknown handler '{args.handler}'. Available: {available}.")
            return

        try:
            subscription_id = self.bus.subscribe(
                handler,
                name=args.handler,
                event_types=args.event_types,
                severities=args.severities,
            )
        except ValueError as error:
            self._emit_line(f"subscribe error: {error}")
            return

        self._emit_line(f"Subscribed {args.handler} as {subscription_id}.")

    def do_unsubscribe(self, arg: str) -> None:
        subscription_id = arg.strip()
        if not subscription_id:
            self._emit_line("unsubscribe error: subscription id is required.")
            return

        if self.bus.unsubscribe(subscription_id):
            self._emit_line(f"Removed subscription {subscription_id}.")
            return

        self._emit_line(f"unsubscribe error: no subscription found for {subscription_id}.")






















def main() -> int:
    shell = EventShell()
    shell.cmdloop()
    return 0
