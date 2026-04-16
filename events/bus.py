""" Event bus implementation for the event engine """

# Enable postponed evaluation of annotations for cleaner type-hinting of the class itself
from __future__ import annotations

# Import deque for efficient ring-buffer history and timestamps tracking
from collections import deque
# Import dataclasses to create structured, memory-efficient data containers
from dataclasses import dataclass, field
# Import time utilities for calculating deduplication windows and timestamps
from datetime import datetime, timedelta
# Import count to generate a thread-safe-ish monotonic sequence of subscription IDs
from itertools import count

# Import the Handler protocol to ensure subscribers follow the expected interface
from .handlers import Handler
# Import the core Event model and Severity levels for filtering and dispatching
from .models import Event, Severity


# Define a container for a subscriber's configuration and filtering logic
@dataclass(slots=True)
class Subscription:
    # A unique identifier assigned by the EventBus
    subscription_id: str
    # A human-readable name for identifying the handler (e.g., "ConsoleLogger")
    name: str
    # The actual callable object that will process matching events
    handler: Handler
    # A set of specific event types this subscriber is interested in (empty means all)
    event_types: frozenset[str]
    # A set of specific severity levels this subscriber filters for (empty means all)
    severities: frozenset[Severity]

    # Evaluate whether a specific event meets the criteria of this subscription
    def matches(self, event: Event) -> bool:
        # Check if the subscription is 'all-types' or if the event type is in the allowed set
        event_type_match = not self.event_types or event.event_type in self.event_types
        # Check if the subscription is 'all-severities' or if the event severity is in the set
        severity_match = not self.severities or event.severity in self.severities
        # Return True only if both the type and the severity requirements are satisfied
        return event_type_match and severity_match


# Internal class to track the frequency and suppression status of repeating events
@dataclass(slots=True)
class _SuppressionState:
    # A queue of timestamps for recent occurrences of a specific (source, type) pair
    timestamps: deque[datetime] = field(default_factory=deque)
    # A flag to track if we have already alerted the system that deduplication is active
    summary_emitted: bool = False
    # A counter of how many actual events have been hidden from handlers during suppression
    suppressed_count: int = 0


# The central hub for publishing events, managing subscribers, and handling history
class EventBus:
    # A reserved event type used for system-generated deduplication notifications
    SUMMARY_EVENT_TYPE = "suppression_summary"

    # Initialize the bus with configurable limits for history and anti-spam logic
    def __init__(
        self,
        *,
        # The maximum number of events to keep in the in-memory history buffer
        max_history: int = 100,
        # The number of identical events allowed before suppression starts
        dedup_threshold: int = 3,
        # The time window within which events are counted for deduplication
        dedup_window: timedelta = timedelta(seconds=60),
    ) -> None:
        # Validate that the history size is a positive integer
        if max_history <= 0:
            raise ValueError("max_history must be greater than zero.")
        # Validate that the deduplication threshold is at least one
        if dedup_threshold <= 0:
            raise ValueError("dedup_threshold must be greater than zero.")
        # Validate that the deduplication window has a positive duration
        if dedup_window.total_seconds() <= 0:
            raise ValueError("dedup_window must be greater than zero.")

        # Store the configuration parameters for runtime reference
        self.max_history = max_history
        # Store the threshold count for suppression triggers
        self.dedup_threshold = dedup_threshold
        # Store the time window for suppression calculations
        self.dedup_window = dedup_window
        # Use a deque with maxlen to automatically drop old events (ring-buffer)
        self._history: deque[Event] = deque(maxlen=max_history)
        # Dictionary mapping subscription IDs to Subscription objects
        self._subscriptions: dict[str, Subscription] = {}
        # Mapping of (source, event_type) tuples to their current suppression state
        self._suppression_windows: dict[tuple[str, str], _SuppressionState] = {}
        # Monotonic counter for generating unique, sequential subscription IDs
        self._sequence = count(1)

    # Property to get a snapshot of the current history as an immutable tuple
    @property
    def history(self) -> tuple[Event, ...]:
        return tuple(self._history)

    # Directly inject events into history, bypassing deduplication and handlers
    def restore_history_snapshot(self, events: list[Event] | tuple[Event, ...]) -> None:
        """Replace published history without notifying handlers (persistence restore only)."""
        # Clear the current ring-buffer
        self._history.clear()
        # Add the restored events into the ring-buffer
        self._history.extend(events)

    # Register a new handler with optional filters for types and severities
    def subscribe(
        self,
        handler: Handler,
        *,
        # Optional name for the subscription; defaults to the handler's class/function name
        name: str | None = None,
        # Optional list of strings to filter by event category
        event_types: list[str] | tuple[str, ...] | set[str] | None = None,
        # Optional list of Severity levels to filter by priority
        severities: list[Severity | str] | tuple[Severity | str, ...] | set[Severity | str] | None = None,
    ) -> str:
        # Generate a unique string ID for this subscription
        subscription_id = f"sub-{next(self._sequence)}"
        # Determine the name by checking 'name', then the handler's __name__, then its class name
        resolved_name = name or getattr(handler, "__name__", handler.__class__.__name__)
        # Clean up event type strings by stripping whitespace and storing in an immutable set
        normalized_event_types = frozenset(item.strip() for item in (event_types or []) if item.strip())
        # Convert all severity inputs into valid Severity Enum members and store in a set
        normalized_severities = frozenset(
            Severity.from_value(severity)
            for severity in (severities or [])
        )

        # Create and store the Subscription object
        self._subscriptions[subscription_id] = Subscription(
            subscription_id=subscription_id,
            name=resolved_name,
            handler=handler,
            event_types=normalized_event_types,
            severities=normalized_severities,
        )
        # Return the ID so the user can unsubscribe later if needed
        return subscription_id

    # Remove a subscriber from the bus using its unique ID
    def unsubscribe(self, subscription_id: str) -> bool:
        # Remove from dictionary and return True if it existed, False otherwise
        return self._subscriptions.pop(subscription_id, None) is not None

    # Return a list of all current active subscriptions
    def list_subscriptions(self) -> tuple[Subscription, ...]:
        return tuple(self._subscriptions.values())

    # Entry point for new events; handles suppression logic and dispatching
    def publish(self, event: Event) -> tuple[Event, ...]:
        # List to track which events were actually sent to handlers (original or summary)
        dispatched: list[Event] = []
        # Process the event through the deduplication engine to see what should be emitted
        for item in self._events_to_dispatch(event):
            # Send the allowed event to all matching subscribers and update history
            self._dispatch(item, record_history=True)
            # Add to the list of successfully processed events
            dispatched.append(item)
        # Return a tuple of events that were effectively 'seen' by the system
        return tuple(dispatched)

    # Re-run a sequence of events through current handlers without adding to history
    def replay(self, events: list[Event] | tuple[Event, ...] | None = None) -> int:
        # Use provided events or default to the entire stored history buffer
        sequence = tuple(events if events is not None else self.history)
        # Iterate through the sequence in chronological order
        for event in sequence:
            # Dispatch to handlers but keep record_history False to prevent duplication
            self._dispatch(event, record_history=False)
        # Return the total count of events that were re-processed
        return len(sequence)

    # Core internal logic to send an event to matching subscribers
    def _dispatch(self, event: Event, *, record_history: bool) -> None:
        # If requested, add the event to the ring-buffer history
        if record_history:
            self._history.append(event)

        # Iterate over a snapshot of current subscriptions to avoid issues if set changes during loop
        for subscription in tuple(self._subscriptions.values()):
            # If the subscriber's filters match this specific event
            if subscription.matches(event):
                # Call the subscriber's handler function with the event
                subscription.handler(event)

    # Deduplication engine: determines if an event should be published, suppressed, or summarized
    def _events_to_dispatch(self, event: Event) -> list[Event]:
        # Never deduplicate the system's own suppression summary events
        if event.event_type == self.SUMMARY_EVENT_TYPE:
            return [event]

        # Identify the event stream by the combination of where it came from and what it is
        key = (event.source, event.event_type)
        # Retrieve or create a suppression state tracker for this specific stream
        state = self._suppression_windows.setdefault(key, _SuppressionState())
        # Calculate the oldest timestamp we care about based on the deduplication window
        cutoff = event.timestamp - self.dedup_window

        # Remove all timestamps from the tracker that are older than the current window
        while state.timestamps and state.timestamps[0] < cutoff:
            state.timestamps.popleft()

        # If the number of recent events has dropped below the threshold, reset suppression flags
        if len(state.timestamps) < self.dedup_threshold:
            state.summary_emitted = False
            state.suppressed_count = 0

        # Record the current event's timestamp in the tracking queue
        state.timestamps.append(event.timestamp)
        # If we haven't hit the limit yet, allow the event to pass through normally
        if len(state.timestamps) <= self.dedup_threshold:
            return [event]

        # If we are here, suppression is active; increment the hidden event counter
        state.suppressed_count += 1
        # If we already told the handlers that deduplication started, send nothing
        if state.summary_emitted:
            return []

        # If this is the first event over the threshold, mark summary as sent
        state.summary_emitted = True
        # Create a special system event explaining that spam protection is now active
        summary = Event(
            source=event.source,
            event_type=self.SUMMARY_EVENT_TYPE,
            severity=event.severity,
            message=(
                f"Deduplication engaged for '{event.event_type}' from {event.source} "
                f"after more than {self.dedup_threshold} events in "
                f"{int(self.dedup_window.total_seconds())} seconds."
            ),
            timestamp=event.timestamp,
        )
        # Dispatch the summary instead of the original repeating event
        return [summary]