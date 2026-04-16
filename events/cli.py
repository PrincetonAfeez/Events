""" Command-line interface for the event engine """

# Enable postponed evaluation of type annotations for forward references and cleaner syntax
from __future__ import annotations

# Import argparse for sophisticated command-line argument parsing within the shell
import argparse
# Import the cmd module to provide a framework for the interactive command-line interface
import cmd
# Import shlex for correctly splitting command strings into tokens, respecting quotes
import shlex
# Import timedelta to define the time duration for the deduplication window
from datetime import timedelta

# Import the AlertManager to handle the lifecycle of generated alerts
from .alert_manager import AlertManager
# Import the EventBus and Subscription model for event distribution logic
from .bus import EventBus, Subscription
# Import specific handlers to process events as they are published to the bus
from .handlers import AlertHandler, ConsoleHandler, LogHandler
# Import models and formatting utilities for consistent data representation
from .models import AlertState, Event, Severity, format_alert, format_event


# Define a specialized ArgumentParser that raises exceptions instead of exiting the program
class _CommandParser(argparse.ArgumentParser):
    # Override the default error method to prevent the CLI from crashing on bad input
    def error(self, message: str) -> None:
        # Raise a ValueError which can be caught and displayed gracefully by the shell
        raise ValueError(message)


# Define the main interactive shell class inheriting from the standard cmd.Cmd framework
class EventShell(cmd.Cmd):
    # Set the introductory message shown when the shell starts up
    intro = "Vault OS Event Engine. Type 'help' to list commands."
    # Define the custom prompt string shown to the user at the command line
    prompt = "events> "

    # Initialize the shell components and set up default subscriptions
    def __init__(self) -> None:
        # Initialize the parent cmd.Cmd class
        super().__init__()
        # Instantiate the central AlertManager for the session
        self.alert_manager = AlertManager()
        # Initialize the EventBus with a 50-event history and a 60-second deduplication logic
        self.bus = EventBus(max_history=50, dedup_threshold=3, dedup_window=timedelta(seconds=60))
        # Instantiate a LogHandler to keep an in-memory record of events
        self.log_handler = LogHandler()
        # Create a registry of available handlers mapped to their string names
        self._available_handlers = {
            # ConsoleHandler: prints events directly to the shell's standard output
            "console": ConsoleHandler(self._emit_line),
            # LogHandler: stores events in a list for later inspection
            "log": self.log_handler,
            # AlertHandler: routes events to the AlertManager based on severity
            "alert": AlertHandler(self.alert_manager),
        }
        # Automatically subscribe the console handler to all events for visibility
        self.bus.subscribe(self._available_handlers["console"], name="console")
        # Automatically subscribe the log handler to all events for persistence
        self.bus.subscribe(self._available_handlers["log"], name="log")
        # Subscribe the alert handler specifically for high-severity events
        self.bus.subscribe(
            self._available_handlers["alert"],
            name="alert",
            # Only trigger alerts for WARNING and CRITICAL severity levels
            severities=[Severity.WARNING, Severity.CRITICAL],
        )

    # Prevent the shell from repeating the previous command when an empty line is entered
    def emptyline(self) -> None:
        # Simply return None to do nothing on an empty enter key press
        return None

    # Handle cases where the user enters a command that is not recognized
    def default(self, line: str) -> None:
        # Emit a helpful message suggesting the 'help' command
        self._emit_line(f"Unknown command: {line}. Type 'help' for available commands.")

    # Implementation for the 'publish' command to emit new events into the system
    def do_publish(self, arg: str) -> None:
        """publish SOURCE TYPE SEVERITY MESSAGE: Publish an event. Run 'publish' with no args for prompts."""
        # If no arguments are provided, enter interactive prompt mode
        if not arg.strip():
            # Prompt for the system/component originating the event
            source = input("Source: ").strip()
            # Prompt for the specific category of the event
            event_type = input("Event type: ").strip()
            # Prompt for the priority level (INFO, WARNING, or CRITICAL)
            severity = input("Severity (INFO/WARNING/CRITICAL): ").strip()
            # Prompt for the detailed description of the occurrence
            message = input("Message: ").strip()
        # If arguments are provided as a single line, parse them using argparse
        else:
            # Create a parser for the publish command
            parser = _CommandParser(prog="publish", add_help=False)
            # Add positional argument for the source
            parser.add_argument("source")
            # Add positional argument for the event type
            parser.add_argument("event_type")
            # Add positional argument for the severity
            parser.add_argument("severity")
            # Add argument for the message, allowing multiple words to be captured as one
            parser.add_argument("message", nargs="+")
            try:
                # Tokenize and parse the input string using shlex for safety
                args = parser.parse_args(shlex.split(arg))
            except ValueError as error:
                # Catch parsing errors (like missing arguments) and inform the user
                self._emit_line(f"publish error: {error}")
                # Exit the command early on error
                return

            # Assign parsed values to local variables
            source = args.source
            event_type = args.event_type
            severity = args.severity
            # Join message parts back into a single string if multiple words were provided
            message = " ".join(args.message)

        try:
            # Create a new Event instance, which performs internal validation
            event = Event(
                source=source,
                event_type=event_type,
                # Convert string severity (e.g., "info") to the appropriate Enum member
                severity=Severity.from_value(severity),
                message=message,
            )
        except ValueError as error:
            # Handle validation errors (e.g., empty fields or invalid severity)
            self._emit_line(f"publish error: {error}")
            # Exit the command early on error
            return

        # Publish the event to the bus and capture any events that were actually dispatched
        dispatched = self.bus.publish(event)
        # If the returned collection is empty, the bus suppressed the event due to spamming
        if not dispatched:
            # Inform the user that the deduplication logic prevented this event from firing
            self._emit_line("Event suppressed by deduplication.")

    # Implementation for the 'handlers' command to show available and active subscribers
    def do_handlers(self, arg: str) -> None:
        """handlers: List available handlers and the active subscriptions."""
        # Ignore any arguments passed to this command
        del arg
        # Header for available handler classes
        self._emit_line("Available handlers:")
        # Loop through and display the names of handlers registered in __init__
        for name in sorted(self._available_handlers):
            self._emit_line(f"  - {name}")

        # Retrieve the current list of subscriptions from the EventBus
        subscriptions = self.bus.list_subscriptions()
        # Header for current active event listeners
        self._emit_line("Active subscriptions:")
        # If no subscriptions exist, notify the user
        if not subscriptions:
            self._emit_line("  (none)")
            # Exit early
            return
        # Loop through each subscription and print its descriptive summary
        for subscription in subscriptions:
            self._emit_line(f"  - {self._describe_subscription(subscription)}")

    # Implementation for the 'subscribe' command to create new event filters at runtime
    def do_subscribe(self, arg: str) -> None:
        """subscribe HANDLER [--type EVENT_TYPE ...] [--severity LEVEL ...]: Add a subscription."""
        # Setup argparse for a more complex command with flags
        parser = _CommandParser(prog="subscribe", add_help=False)
        # The first argument must be the name of a registered handler
        parser.add_argument("handler")
        # Optional flag to filter by one or more event types
        parser.add_argument("--type", dest="event_types", action="append", default=[])
        # Optional flag to filter by one or more severity levels
        parser.add_argument("--severity", dest="severities", action="append", default=[])

        try:
            # Parse the command line arguments
            args = parser.parse_args(shlex.split(arg))
        except ValueError as error:
            # Display errors for malformed command syntax
            self._emit_line(f"subscribe error: {error}")
            # Exit early
            return

        # Look up the actual handler object by the name provided in the command
        handler = self._available_handlers.get(args.handler)
        # If the handler name is invalid, show a list of valid ones
        if handler is None:
            # Construct a comma-separated list of valid handler names
            available = ", ".join(sorted(self._available_handlers))
            # Notify user of the error
            self._emit_line(f"subscribe error: unknown handler '{args.handler}'. Available: {available}.")
            # Exit early
            return

        try:
            # Register the subscription with the EventBus using the parsed filters
            subscription_id = self.bus.subscribe(
                handler,
                # Use the handler name as the subscription name
                name=args.handler,
                # Pass the list of requested event types
                event_types=args.event_types,
                # Pass the list of requested severity levels
                severities=args.severities,
            )
        except ValueError as error:
            # Catch errors like invalid severity names within the subscription attempt
            self._emit_line(f"subscribe error: {error}")
            # Exit early
            return

        # Confirm to the user that the subscription is now active
        self._emit_line(f"Subscribed {args.handler} as {subscription_id}.")

    # Implementation for the 'unsubscribe' command to stop a handler from receiving events
    def do_unsubscribe(self, arg: str) -> None:
        """unsubscribe SUBSCRIPTION_ID: Remove an active subscription."""
        # Clean the input argument to get the ID string
        subscription_id = arg.strip()
        # If no ID was provided, report an error
        if not subscription_id:
            self._emit_line("unsubscribe error: subscription id is required.")
            # Exit early
            return

        # Attempt to remove the subscription from the bus
        if self.bus.unsubscribe(subscription_id):
            # If successful, notify the user
            self._emit_line(f"Removed subscription {subscription_id}.")
            # Exit early
            return

        # If the ID didn't exist, report the failure
        self._emit_line(f"unsubscribe error: no subscription found for {subscription_id}.")

    # Implementation for the 'history' command to view recently published events
    def do_history(self, arg: str) -> None:
        """history [LIMIT]: Show event history, newest last."""
        # Clean the input to check for a numeric limit
        limit_text = arg.strip()
        try:
            # Convert text to integer if present, otherwise default to None (show all)
            limit = int(limit_text) if limit_text else None
        except ValueError:
            # Handle non-integer inputs gracefully
            self._emit_line("history error: limit must be an integer.")
            # Exit early
            return

        # Fetch the event history from the bus
        events = self.bus.history
        # If a limit was specified, slice the collection to show the most recent ones
        if limit is not None:
            events = events[-limit:]

        # Header for the history display
        self._emit_line("Event history:")
        # Check if the history buffer is currently empty
        if not events:
            # Display placeholder message
            self._emit_line("  (empty)")
            # Exit early
            return
        # Iterate and print each event in the collection using the standard formatter
        for event in events:
            self._emit_line(f"  - {format_event(event)}")

    # Implementation for the 'alerts' command to view and filter system alerts
    def do_alerts(self, arg: str) -> None:
        """alerts [--all] [--severity LEVEL] [--source SOURCE] [--unacknowledged]: Show alerts."""
        # Setup argparse for filtering flags
        parser = _CommandParser(prog="alerts", add_help=False)
        # Flag to include RESOLVED alerts in the output
        parser.add_argument("--all", action="store_true")
        # Flag to filter alerts by a specific severity
        parser.add_argument("--severity")
        # Flag to filter alerts by a specific source system
        parser.add_argument("--source")
        # Flag to show only NEW alerts that haven't been touched yet
        parser.add_argument("--unacknowledged", action="store_true")

        try:
            # Parse the provided flags
            args = parser.parse_args(shlex.split(arg))
        except ValueError as error:
            # Display errors for syntax issues
            self._emit_line(f"alerts error: {error}")
            # Exit early
            return

        # Initialize the severity filter variable
        severity = None
        # If the user provided a severity string, convert it to an Enum
        if args.severity:
            try:
                # Use the Severity helper to validate and convert the input
                severity = Severity.from_value(args.severity)
            except ValueError as error:
                # Handle unknown severity names
                self._emit_line(f"alerts error: {error}")
                # Exit early
                return

        # Request filtered alerts from the AlertManager
        alerts = self.alert_manager.filter_alerts(
            severity=severity,
            source=args.source,
            # Pass the toggle for including resolved alerts
            include_resolved=args.all,
        )
        # If the user specifically wants NEW alerts, filter the result set further
        if args.unacknowledged:
            # Keep only alerts where state is NEW
            alerts = tuple(alert for alert in alerts if alert.state == AlertState.NEW)

        # Header for the alert list
        self._emit_line("Alerts:")
        # Check if any alerts matched the criteria
        if not alerts:
            # Notify the user no matches were found
            self._emit_line("  (none)")
            # Exit early
            return
        # Iterate and print each alert using the alert formatter
        for alert in alerts:
            self._emit_line(f"  - {format_alert(alert)}")

    # Implementation for the 'ack' command to acknowledge an alert
    def do_ack(self, arg: str) -> None:
        """ack ALERT_ID USER: Acknowledge an alert."""
        # Setup argparse for positional acknowledgment data
        parser = _CommandParser(prog="ack", add_help=False)
        # The unique ID of the alert to acknowledge
        parser.add_argument("alert_id")
        # The name of the user performing the acknowledgment
        parser.add_argument("user")

        try:
            # Parse the ID and username
            args = parser.parse_args(shlex.split(arg))
        except ValueError as error:
            # Report parsing errors
            self._emit_line(f"ack error: {error}")
            # Exit early
            return

        try:
            # Instruct the AlertManager to record the acknowledgment
            alert = self.alert_manager.acknowledge_alert(args.alert_id, args.user)
        except (KeyError, ValueError) as error:
            # Catch cases where ID is missing or alert is already resolved
            self._emit_line(f"ack error: {error}")
            # Exit early
            return

        # Confirm acknowledgment success to the user
        self._emit_line(f"Acknowledged alert {alert.alert_id}.")

    # Implementation for the 'resolve' command to close an alert
    def do_resolve(self, arg: str) -> None:
        """resolve ALERT_ID NOTES: Resolve an alert with notes."""
        # Setup argparse for positional resolution data
        parser = _CommandParser(prog="resolve", add_help=False)
        # The unique ID of the alert to resolve
        parser.add_argument("alert_id")
        # The mandatory resolution notes explaining the fix
        parser.add_argument("notes", nargs="+")

        try:
            # Parse input arguments
            args = parser.parse_args(shlex.split(arg))
        except ValueError as error:
            # Report parsing errors
            self._emit_line(f"resolve error: {error}")
            # Exit early
            return

        try:
            # Instruct AlertManager to resolve the alert with the combined notes string
            alert = self.alert_manager.resolve_alert(args.alert_id, " ".join(args.notes))
        except (KeyError, ValueError) as error:
            # Catch cases where ID is missing or notes are empty
            self._emit_line(f"resolve error: {error}")
            # Exit early
            return

        # Confirm resolution success to the user
        self._emit_line(f"Resolved alert {alert.alert_id}.")

    # Implementation for the 'replay' command to re-run events through handlers
    def do_replay(self, arg: str) -> None:
        """replay [COUNT]: Replay stored history through the bus without re-recording it."""
        # Clean the input to check for a count
        count_text = arg.strip()
        try:
            # Convert text to integer if present, otherwise default to None (replay all)
            limit = int(count_text) if count_text else None
        except ValueError:
            # Handle non-integer inputs gracefully
            self._emit_line("replay error: count must be an integer.")
            # Exit early
            return

        # Retrieve the history sequence from the bus
        events = self.bus.history
        # If a count was provided, slice the history to the most recent X events
        if limit is not None:
            events = events[-limit:]

        # Trigger the bus replay mechanism which dispatches events to current subscribers
        replayed = self.bus.replay(events)
        # Notify the user of how many events were successfully re-processed
        self._emit_line(f"Replayed {replayed} event(s).")

    # Implementation for the 'log' command to inspect the LogHandler buffer
    def do_log(self, arg: str) -> None:
        """log [LIMIT]: Show the in-memory log handler output."""
        # Clean the input to check for a limit
        limit_text = arg.strip()
        try:
            # Convert text to integer or None
            limit = int(limit_text) if limit_text else None
        except ValueError:
            # Handle non-integer inputs gracefully
            self._emit_line("log error: limit must be an integer.")
            # Exit early
            return

        # Request the string records from the specialized log handler
        records = self.log_handler.tail(limit)
        # Header for the log output
        self._emit_line("Log records:")
        # Check if any records were captured
        if not records:
            # Notify the user the log is empty
            self._emit_line("  (empty)")
            # Exit early
            return
        # Iterate and print each log line to the shell
        for record in records:
            self._emit_line(f"  - {record}")

    # Standard command to exit the interactive shell
    def do_exit(self, arg: str) -> bool:
        """exit: Leave the CLI."""
        # Unused argument
        del arg
        # Return True to signal to cmd.Cmd that the shell should terminate
        return True

    # Alias for the 'exit' command for user convenience
    def do_quit(self, arg: str) -> bool:
        """quit: Leave the CLI."""
        # Route to the exit implementation
        return self.do_exit(arg)

    # Handle the End-of-File character (Ctrl+D) to exit the shell
    def do_EOF(self, arg: str) -> bool:
        # Unused argument
        del arg
        # Print a newline for clean shell exit
        self._emit_line("")
        # Return True to terminate
        return True

    # Helper method to generate a human-readable string describing a subscription
    def _describe_subscription(self, subscription: Subscription) -> str:
        # Format the event types list, showing "all types" if the set is empty
        event_types = ", ".join(sorted(subscription.event_types)) or "all types"
        # Format the severities list, showing "all severities" if the set is empty
        severities = ", ".join(severity.name for severity in sorted(subscription.severities)) or "all severities"
        # Return a summary string with the ID, name, and filter criteria
        return (
            f"{subscription.subscription_id} -> {subscription.name} "
            f"(types: {event_types}; severities: {severities})"
        )

    # Centralized method for writing lines to the shell's output stream
    def _emit_line(self, text: str) -> None:
        # Write the text followed by a newline to the standard output
        self.stdout.write(f"{text}\n")


# Standard entry point function for the CLI script
def main() -> int:
    # Instantiate the EventShell
    shell = EventShell()
    # Start the interactive loop which waits for user input
    shell.cmdloop()
    # Return 0 to indicate successful program termination
    return 0