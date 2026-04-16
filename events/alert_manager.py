
from __future__ import annotations

from .models import Alert, AlertState, Event, Severity


class AlertManager:
    def __init__(self) -> None:
        self._alerts: dict[str, Alert] = {}

    def replace_alerts_for_restore(self, alerts: dict[str, Alert]) -> None:
        self._alerts = dict(alerts)

    def create_alert(self, event: Event) -> Alert | None:
        if event.severity < Severity.WARNING:
            return None

        alert = Alert(event=event)
        self._alerts[alert.alert_id] = alert
        return alert