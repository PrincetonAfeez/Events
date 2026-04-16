""" Events models """

# Enable postponed evaluation of annotations for forward-referencing type hints
from __future__ import annotations

# Import tools for creating data-oriented classes and defining custom field behaviors
from dataclasses import dataclass, field
# Import datetime utilities and the UTC timezone constant for standardized time tracking
from datetime import UTC, datetime
# Import specialized Enum types for integer-based and string-based constants
from enum import IntEnum, StrEnum
# Import the UUID version 4 generator to create unique identifiers
from uuid import uuid4


# Define an enumeration for event severity levels inheriting from IntEnum for comparisons
class Severity(IntEnum):
    # Lowest priority: informational messages
    INFO = 1
    # Medium priority: potential issues that don't require immediate action
    WARNING = 2
    # Highest priority: urgent issues requiring immediate attention
    CRITICAL = 3

    # Define a helper to convert raw input (string or existing Enum) into a Severity member
    @classmethod
    def from_value(cls, value: "Severity | str") -> "Severity":
        # If the value is already a Severity instance, return it directly
        if isinstance(value, cls):
            return value

        # Clean up string input by removing whitespace and converting to uppercase
        normalized = value.strip().upper()
        try:
            # Attempt to look up the severity by its name key
            return cls[normalized]
        except KeyError as error:
            # Gather all valid names to provide a helpful error message if lookup fails
            allowed = ", ".join(member.name for member in cls)
            # Raise a ValueError explaining the invalid input and the expected options
            raise ValueError(f"Unknown severity '{value}'. Expected one of: {allowed}.") from error

    # Return the name of the enum member (e.g., "INFO") when converted to a string
    def __str__(self) -> str:
        return self.name


# Define an enumeration for the lifecycle status of an alert using string values
class AlertState(StrEnum):
    # The initial state when an alert is first created
    NEW = "new"
    # State assigned when a user acknowledges they are looking into the issue
    ACKNOWLEDGED = "acknowledged"
    # Final state assigned once the issue has been addressed
    RESOLVED = "resolved"


# Create an immutable data class for Events, using slots for memory efficiency
@dataclass(slots=True, frozen=True)
class Event:
    # The name of the component or system that generated the event
    source: str
    # The specific category or name of the event (e.g., "ConnectionTimeout")
    event_type: str
    # The priority level of the event using the Severity Enum
    severity: Severity
    # A human-readable description of what occurred
    message: str
    # The time of occurrence, defaulting to the current time in UTC
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    # A unique identifier for the event, generated as a UUID string
    event_id: str = field(default_factory=lambda: str(uuid4()))

    # Run validation and normalization logic after the dataclass initializes fields
    def __post_init__(self) -> None:
        # Strip leading/trailing whitespace from the source string
        source = self.source.strip()
        # Strip leading/trailing whitespace from the event type string
        event_type = self.event_type.strip()
        # Strip leading/trailing whitespace from the message string
        message = self.message.strip()
        # Convert the severity input into a valid Severity Enum member
        severity = Severity.from_value(self.severity)
        # Ensure the timestamp is localized to UTC if it doesn't already have timezone info
        timestamp = self.timestamp if self.timestamp.tzinfo else self.timestamp.replace(tzinfo=UTC)

        # Ensure the event source is not an empty string
        if not source:
            raise ValueError("Event source cannot be empty.")
        # Ensure the event type identifier is not an empty string
        if not event_type:
            raise ValueError("Event type cannot be empty.")
        # Ensure the event message content is not an empty string
        if not message:
            raise ValueError("Event message cannot be empty.")

        # Use object.__setattr__ to bypass the 'frozen=True' restriction for normalization
        object.__setattr__(self, "source", source)
        # Apply the normalized event type back to the instance
        object.__setattr__(self, "event_type", event_type)
        # Apply the normalized message back to the instance
        object.__setattr__(self, "message", message)
        # Apply the validated Severity Enum back to the instance
        object.__setattr__(self, "severity", severity)
        # Apply the UTC-enforced timestamp back to the instance
        object.__setattr__(self, "timestamp", timestamp)


# Create a mutable data class to track the lifecycle of an alert linked to an event
@dataclass(slots=True)
class Alert:
    # The underlying immutable event that triggered this alert
    event: Event
    # The current state of the alert, starting as 'NEW'
    state: AlertState = AlertState.NEW
    # The name/ID of the user who acknowledged the alert, if applicable
    acknowledged_by: str | None = None
    # The timestamp of when the alert was acknowledged, if applicable
    acknowledged_at: datetime | None = None
    # Documentation or notes regarding the final fix or resolution
    resolution_notes: str | None = None

    # Property to expose the ID of the underlying event as the alert's ID
    @property
    def alert_id(self) -> str:
        return self.event.event_id

    # Property to expose the source of the underlying event
    @property
    def source(self) -> str:
        return self.event.source

    # Property to expose the severity of the underlying event
    @property
    def severity(self) -> Severity:
        return self.event.severity

    # Transition the alert to the 'ACKNOWLEDGED' state
    def acknowledge(self, user: str, when: datetime | None = None) -> None:
        # Strip whitespace from the username
        user = user.strip()
        # Prevent acknowledgment if no username is provided
        if not user:
            raise ValueError("Acknowledged-by cannot be empty.")
        # Prevent acknowledgment if the alert has already been resolved
        if self.state == AlertState.RESOLVED:
            raise ValueError("Resolved alerts cannot be acknowledged.")

        # Update the state to 'ACKNOWLEDGED'
        self.state = AlertState.ACKNOWLEDGED
        # Record the user taking responsibility
        self.acknowledged_by = user
        # Set the acknowledgment time to the provided time or current UTC time
        self.acknowledged_at = when or datetime.now(UTC)

    # Transition the alert to the 'RESOLVED' state
    def resolve(self, notes: str) -> None:
        # Strip whitespace from the resolution notes
        notes = notes.strip()
        # Prevent resolution if no explanatory notes are provided
        if not notes:
            raise ValueError("Resolution notes cannot be empty.")

        # Update the state to 'RESOLVED'
        self.state = AlertState.RESOLVED
        # Record the final notes for future reference
        self.resolution_notes = notes


# Global function to format an Event object into a human-readable string
def format_event(event: Event) -> str:
    # Convert the event timestamp to UTC and format it to an ISO 8601 string (seconds precision)
    timestamp = event.timestamp.astimezone(UTC).isoformat(timespec="seconds")
    # Return a formatted string with fixed-width columns for alignment
    return (
        f"[{timestamp}] {event.severity.name:<8} "
        f"{event.source:<16} {event.event_type:<24} {event.message}"
    )


# Global function to format an Alert object and its lifecycle data into a string
def format_alert(alert: Alert) -> str:
    # Initialize a list of core alert attributes formatted as key-value pairs
    parts = [
        f"id={alert.alert_id}",
        f"state={alert.state.value}",
        f"severity={alert.severity.name}",
        f"source={alert.source}",
        f"type={alert.event.event_type}",
        f"message={alert.event.message}",
    ]
    # Append acknowledgment user info if it exists
    if alert.acknowledged_by:
        parts.append(f"ack_by={alert.acknowledged_by}")
    # Append acknowledgment timestamp if it exists, formatted to UTC ISO
    if alert.acknowledged_at:
        parts.append(f"ack_at={alert.acknowledged_at.astimezone(UTC).isoformat(timespec='seconds')}")
    # Append resolution notes if the alert has been resolved
    if alert.resolution_notes:
        parts.append(f"resolution={alert.resolution_notes}")
    # Join all populated fields with a pipe separator for a single-line log style
    return " | ".join(parts)