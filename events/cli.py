from __future__ import annotations

import argparse
import cmd
import shlex
from datetime import timedelta

from .alert_manager import AlertManager
from .bus import EventBus, Subscription
from .handlers import AlertHandler, ConsoleHandler, LogHandler
from .models import AlertState, Event, Severity, format_alert, format_event
















def main() -> int:
    shell = EventShell()
    shell.cmdloop()
    return 0
