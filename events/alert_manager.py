""" Alert manager """

# Enable postponed evaluation of type annotations for cleaner forward references
from __future__ import annotations

# Import relevant data models and enums from the local models module
from .models import Alert, AlertState, Event, Severity


# Define a manager class to handle the lifecycle and storage of system alerts
class AlertManager:
    # Initialize the manager with an empty dictionary to store alerts by their unique ID
    def __init__(self) -> None:
        # Internal storage mapping alert IDs (strings) to Alert object instances
        self._alerts: dict[str, Alert] = {}

    # Provide a mechanism to bulk-load alerts, typically used when restoring from a saved state
    def replace_alerts_for_restore(self, alerts: dict[str, Alert]) -> None:
        """Replace stored alerts (persistence restore only)."""
        # Create a new dictionary from the input to replace current in-memory alert data
        self._alerts = dict(alerts)

    # Evaluate an incoming event and create a corresponding alert if it is severe enough
    def create_alert(self, event: Event) -> Alert | None:
        # Ignore events with severity lower than WARNING (e.g., INFO events don't trigger alerts)
        if event.severity < Severity.WARNING:
            # Return None to indicate no alert was generated for this specific event
            return None

        # Instantiate a new Alert object wrapping the provided Event
        alert = Alert(event=event)
        # Store the newly created alert in the internal dictionary using its unique ID
        self._alerts[alert.alert_id] = alert
        # Return the alert instance so the caller can react to its creation
        return alert

    # Retrieve a specific alert from storage using its unique identifier
    def get_alert(self, alert_id: str) -> Alert:
        try:
            # Attempt to return the alert associated with the provided ID
            return self._alerts[alert_id]
        # Catch cases where the ID does not exist in the internal dictionary
        except KeyError as error:
            # Raise a descriptive KeyError to inform the caller the ID was not found
            raise KeyError(f"No alert found for id '{alert_id}'.") from error

    # Mark a specific alert as acknowledged by a specific user
    def acknowledge_alert(self, alert_id: str, user: str) -> Alert:
        # Fetch the alert instance using the internal get_alert helper
        alert = self.get_alert(alert_id)
        # Invoke the alert's own internal method to update its state and timestamp
        alert.acknowledge(user)
        # Return the updated alert object
        return alert

    # Mark a specific alert as resolved with mandatory explanatory notes
    def resolve_alert(self, alert_id: str, notes: str) -> Alert:
        # Fetch the alert instance using the internal get_alert helper
        alert = self.get_alert(alert_id)
        # Invoke the alert's own internal method to transition it to the RESOLVED state
        alert.resolve(notes)
        # Return the resolved alert object
        return alert

    # Return a collection of every alert currently stored in the manager
    def all_alerts(self) -> tuple[Alert, ...]:
        # Convert the dictionary values into an immutable tuple of all Alert objects
        return tuple(self._alerts.values())

    # Return only the alerts that have not yet been resolved
    def active_alerts(self) -> tuple[Alert, ...]:
        # Use the filter helper to exclude alerts in the RESOLVED state
        return self.filter_alerts(include_resolved=False)

    # Return alerts that are still in the NEW state (ignoring acknowledged/resolved)
    def unacknowledged_alerts(self, include_resolved: bool = False) -> tuple[Alert, ...]:
        # Use the filter helper targeting the NEW state specifically
        return self.filter_alerts(state=AlertState.NEW, include_resolved=include_resolved)

    # Return alerts filtered by a specific severity level (INFO, WARNING, or CRITICAL)
    def alerts_by_severity(
        self,
        # Accept either the Severity enum or a string representation of it
        severity: Severity | str,
        *,
        # Optional flag to determine if resolved alerts should be included in the results
        include_resolved: bool = False,
    ) -> tuple[Alert, ...]:
        # Perform the filter by converting input to a Severity enum and calling the filter helper
        return self.filter_alerts(
            severity=Severity.from_value(severity),
            include_resolved=include_resolved,
        )

    # Return alerts filtered by their source system or component name
    def alerts_by_source(
        self,
        source: str,
        *,
        # Optional flag to determine if resolved alerts should be included in the results
        include_resolved: bool = False,
    ) -> tuple[Alert, ...]:
        # Use the filter helper targeting the specific source string
        return self.filter_alerts(source=source, include_resolved=include_resolved)

    # Core internal filtering logic that applies multiple criteria to the alert set
    def filter_alerts(
        self,
        *,
        # Criteria: specific severity level
        severity: Severity | None = None,
        # Criteria: specific source system
        source: str | None = None,
        # Criteria: specific alert state (NEW, ACKNOWLEDGED, etc.)
        state: AlertState | None = None,
        # Toggle: whether to include alerts that have already been resolved
        include_resolved: bool = False,
    ) -> tuple[Alert, ...]:
        # Convert all stored alerts into a list to begin the filtering process
        alerts = list(self._alerts.values())
        # If include_resolved is False, remove any alert whose state is RESOLVED
        if not include_resolved:
            alerts = [alert for alert in alerts if alert.state != AlertState.RESOLVED]
        # If a specific severity is requested, keep only alerts matching that severity
        if severity is not None:
            alerts = [alert for alert in alerts if alert.severity == severity]
        # If a specific source is requested, keep only alerts matching that source
        if source is not None:
            alerts = [alert for alert in alerts if alert.source == source]
        # If a specific state is requested, keep only alerts matching that state
        if state is not None:
            alerts = [alert for alert in alerts if alert.state == state]
        # Return the final filtered list as an immutable tuple
        return tuple(alerts)