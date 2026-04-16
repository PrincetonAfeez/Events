from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from uuid import uuid4

class Severity(IntEnum):
    INFO = 1
    WARNING = 2
    CRITICAL = 3

    @classmethod
    def from_value(cls, value: "Severity | str") -> "Severity":
        if isinstance(value, cls):
            return value

        normalized = value.strip().upper()
        try:
            return cls[normalized]
        except KeyError as error:
            allowed = ", ".join(member.name for member in cls)
            raise ValueError(f"Unknown severity '{value}'. Expected one of: {allowed}.") from error

    def __str__(self) -> str:
        return self.name

class AlertState(StrEnum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


@dataclass(slots=True, frozen=True)
class Event:
    source: str
    event_type: str
    severity: Severity
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        source = self.source.strip()
        event_type = self.event_type.strip()
        message = self.message.strip()
        severity = Severity.from_value(self.severity)
        timestamp = self.timestamp if self.timestamp.tzinfo else self.timestamp.replace(tzinfo=UTC)

        if not source:
            raise ValueError("Event source cannot be empty.")
        if not event_type:
            raise ValueError("Event type cannot be empty.")
        if not message:
            raise ValueError("Event message cannot be empty.")

        object.__setattr__(self, "source", source)
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "timestamp", timestamp)


@dataclass(slots=True)
class Alert:
    event: Event
    state: AlertState = AlertState.NEW
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    resolution_notes: str | None = None

    @property
    def alert_id(self) -> str:
        return self.event.event_id

    @property
    def source(self) -> str:
        return self.event.source

    @property
    def severity(self) -> Severity:
        return self.event.severity

    def acknowledge(self, user: str, when: datetime | None = None) -> None:
        user = user.strip()
        if not user:
            raise ValueError("Acknowledged-by cannot be empty.")
        if self.state == AlertState.RESOLVED:
            raise ValueError("Resolved alerts cannot be acknowledged.")

        self.state = AlertState.ACKNOWLEDGED
        self.acknowledged_by = user
        self.acknowledged_at = when or datetime.now(UTC)

    def resolve(self, notes: str) -> None:
        notes = notes.strip()
        if not notes:
            raise ValueError("Resolution notes cannot be empty.")

        self.state = AlertState.RESOLVED
        self.resolution_notes = notes

def format_event(event: Event) -> str:
    timestamp = event.timestamp.astimezone(UTC).isoformat(timespec="seconds")
    return (
        f"[{timestamp}] {event.severity.name:<8} "
        f"{event.source:<16} {event.event_type:<24} {event.message}"
    )
