""" Event handlers for the event bus """
# Enable postponed evaluation of type annotations for compatibility and forward references
from __future__ import annotations

# Import typing utilities for defining generic callables and structural protocols
from typing import Callable, Protocol

# Import the AlertManager to allow specific handlers to trigger system alerts
from .alert_manager import AlertManager
# Import core event models and formatting utilities for event processing
from .models import Event, Severity, format_event


# Define a structural protocol that any event handler must implement
class Handler(Protocol):
    # Requirements: any class implementing Handler must be callable with an Event argument
    def __call__(self, event: Event) -> None: ...


# Define a handler responsible for streaming events to a console or specific output function
class ConsoleHandler:
    # Initialize with an optional emission function (like print or a custom logger)
    def __init__(self, emit: Callable[[str], None] | None = None) -> None:
        # Store the provided function or default to the standard Python print function
        self._emit = emit or print

    # Make the instance callable so it can be registered as a subscriber in the EventBus
    def __call__(self, event: Event) -> None:
        # Format the event object into a readable string and send it to the emission function
        self._emit(format_event(event))


# Define a handler that maintains an in-memory buffer of all received events
class LogHandler:
    # Initialize empty lists to store both raw objects and their string representations
    def __init__(self) -> None:
        # Internal storage for raw Event objects for programmatic access
        self.events: list[Event] = []
        # Internal storage for formatted string records for human-readable logs
        self.records: list[str] = []

    # Process an incoming event by appending it to the internal history logs
    def __call__(self, event: Event) -> None:
        # Store the original Event object in the events list
        self.events.append(event)
        # Store the formatted, localized version of the event in the records list
        self.records.append(format_event(event))

    # Retrieve the last 'n' log entries, similar to the Unix 'tail' command
    def tail(self, limit: int | None = None) -> tuple[str, ...]:
        # If no limit is set or the limit exceeds history size, return all records
        if limit is None or limit >= len(self.records):
            # Return records as an immutable tuple for safe reading
            return tuple(self.records)
        # Return only the specified number of most recent records from the end of the list
        return tuple(self.records[-limit:])

    # Provide a way to manually populate logs, usually during a state restoration process
    def replace_captured_events(self, events: list[Event], records: list[str]) -> None:
        """Replace mirrored bus output (persistence restore only)."""
        # Overwrite the current raw event list with the provided data
        self.events = list(events)
        # Overwrite the current string record list with the provided data
        self.records = list(records)


# Define a handler that acts as a bridge between the EventBus and the AlertManager
class AlertHandler:
    # Initialize with a reference to the central AlertManager
    def __init__(self, alert_manager: AlertManager) -> None:
        # Store the alert manager instance to use when specific events occur
        self.alert_manager = alert_manager

    # Filter incoming events and escalate them to alerts if they meet the criteria
    def __call__(self, event: Event) -> None:
        # Check if the event severity is WARNING (2) or CRITICAL (3)
        if event.severity >= Severity.WARNING:
            # Instruct the AlertManager to generate a trackable alert for this event
            self.alert_manager.create_alert(event)