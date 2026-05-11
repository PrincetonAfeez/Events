# Architecture Decision Record
## App 19 — Events
**Vault OS Group | Document 1 of 5**  
**Status: Accepted**

---

## Title

Use an in-memory publish–subscribe event engine with alerting, deduplication, bounded history, and replay.

## Status

Accepted.

## Date

2026-05-08

## Context

App 19 extends the Vault OS sequence from stateful facility objects into event-driven coordination. Earlier apps model devices, access control, inventory, and personnel as direct method calls. The Events app introduces a central event engine that allows facility subsystems to publish facts without knowing which components will consume those facts.

The repository implements this as a small Python package named `vaultos-events`, importable as `events`, with an interactive shell launched through `python main.py`. The runtime has no third-party dependencies; `pytest` is used only for development and testing.

The core problem is not just logging. The application needs to show the architectural distinction between:

- an **event**, which is an immutable fact that something happened;
- a **handler**, which reacts to matching events;
- an **alert**, which is a higher-level operational judgment created from warning or critical events;
- a **bus**, which routes events without hard-coding publishers to consumers.

The design also needs to support noisy subsystems. A camera or sensor can generate many identical events in a short period, so the bus includes deduplication and suppression summaries. To support operational review, the bus keeps a bounded event history and can replay stored events through the current subscribers.

## Decision Drivers

- Keep the app achievable as a focused student build while still demonstrating real system architecture.
- Use standard-library Python at runtime.
- Demonstrate the Observer / publish-subscribe pattern clearly.
- Separate event production from event consumption.
- Keep `Event` records immutable so history is trustworthy.
- Keep `Alert` records mutable because alert lifecycle changes over time.
- Avoid persistent storage for this app; use in-memory structures.
- Provide both importable library classes and an interactive CLI.
- Make verification practical with unit and CLI tests.

## Options Considered

### Option 1 — Direct function calls between subsystems

**Chosen / Rejected:** Rejected.

A direct-call model would let each subsystem invoke the exact consumer it needs, such as calling an alert function directly when a warning occurs.

**Reason:** This would not teach the event-bus architecture the app is meant to demonstrate. It would couple producers to consumers and make later systems harder to extend.

### Option 2 — Simple append-only event log

**Chosen / Rejected:** Rejected as the primary architecture.

An append-only list would be simple and useful for history, but it would only record events after they happen.

**Reason:** The app needs live dispatch, filtered subscribers, alerts, replay, and deduplication. A list alone does not provide those behaviors.

### Option 3 — In-memory EventBus with filtered subscriptions

**Chosen / Rejected:** Chosen.

The implemented `EventBus` owns subscriptions, publishes events to matching handlers, tracks history, deduplicates repeated event streams, and can replay events without adding duplicate history entries.

**Reason:** This gives the project a clear architectural center while staying small enough for a CLI portfolio app.

### Option 4 — Async queue or threaded event loop

**Chosen / Rejected:** Rejected.

The app could use `asyncio`, background worker threads, or queues.

**Reason:** That would increase scope and obscure the core lesson. The current implementation dispatches synchronously, which makes tests deterministic and keeps failure behavior easy to understand.

### Option 5 — Persistent event store

**Chosen / Rejected:** Rejected for App 19.

The event bus includes restore-oriented methods, but the app itself does not persist events or alerts to disk.

**Reason:** Persistence belongs to a later integration layer. For this app, in-memory behavior is sufficient to demonstrate the event model.

## Decision

Build App 19 as a standard-library Python package with:

- immutable `Event` records;
- mutable `Alert` records;
- `Severity` and `AlertState` enums;
- `EventBus` with subscription filtering by event type and severity;
- `ConsoleHandler`, `LogHandler`, and `AlertHandler`;
- `AlertManager` for alert creation, filtering, acknowledgment, and resolution;
- deduplication by `(source, event_type)` inside a time window;
- a bounded ring-buffer history;
- replay that dispatches old events without recording them again;
- an interactive `cmd.Cmd` shell with publish, subscribe, history, log, replay, alerts, ack, and resolve commands.

## Rationale

The chosen design gives the app a strong architectural identity. It is not just a CRUD CLI. The project demonstrates a small event-driven system where producers publish facts and consumers react based on subscription rules.

The immutable `Event` model supports auditability. Once an event is created, the event source, type, severity, message, timestamp, and ID do not change. This makes event history and replay safer.

The mutable `Alert` model reflects operational reality. Alerts move from `new` to `acknowledged` to `resolved`, and their lifecycle metadata changes as operators respond.

The `EventBus` is intentionally synchronous. This keeps the implementation readable and allows tests to assert exact handler order, history length, deduplication behavior, and replay behavior without waiting on background workers.

The CLI uses `cmd.Cmd` instead of one-shot argparse subcommands because the app is a session-oriented simulator. Users can publish multiple events, inspect alerts, acknowledge them, resolve them, and replay history without restarting the process.

## Trade-offs Accepted

- Event and alert storage is process-local and disappears on exit.
- Handler failures are not isolated; a raising handler stops later subscribers during that dispatch.
- Deduplication is based on source and event type, not the full message body.
- Replay sends events to current subscribers, which can create side effects such as duplicate console output or additional alert records depending on current subscriptions.
- The CLI is interactive rather than automation-first.
- There is no persistence, authentication, structured JSON export, or cross-process event delivery.
- The system is not concurrent and does not model delivery guarantees.

## Consequences

The result is a clear event-driven architecture that fits the Vault OS learning sequence. The app can serve as the event backbone conceptually for later integration work without prematurely building a production message broker.

The code is easy to test because events, alerts, subscriptions, and handlers are ordinary Python objects. Tests verify subscription filtering, warning-to-alert behavior, alert lifecycle transitions, deduplication, ring-buffer history, replay, handler failure behavior, CLI command behavior, and alert filters.

The main technical debt is that all state is in memory. A future integration layer would need a durable event store, stronger handler isolation, and a policy for replay side effects.

## Superseded By

Not superseded.

---

# Technical Design Document
## App 19 — Events
**Vault OS Group | Document 2 of 5**

---

## Purpose & Scope

The Events app provides a facility event engine for Vault OS. It models how components publish events, how subscribers consume matching events, and how serious events become operational alerts.

In scope:

- event creation and validation;
- event severity modeling;
- alert creation and lifecycle management;
- publish-subscribe routing;
- subscription filtering by event type and severity;
- console, log, and alert handlers;
- deduplication of repeated event streams;
- bounded event history;
- replay of stored events;
- interactive CLI shell.

Out of scope:

- durable persistence;
- distributed messaging;
- async dispatch;
- authentication;
- network APIs;
- file-based logging;
- integration with the earlier Vault OS apps at runtime.

## System Context

The app is both a library and an interactive CLI.

As a library, callers import classes such as `Event`, `EventBus`, `AlertManager`, `LogHandler`, and `AlertHandler` from the `events` package.

As a CLI, users run:

```bash
python main.py
```

The CLI creates an `EventShell`, which initializes:

- an `AlertManager`;
- an `EventBus` with max history of 50, dedup threshold of 3, and dedup window of 60 seconds;
- a `LogHandler`;
- a `ConsoleHandler`;
- an `AlertHandler`.

The default shell subscribes:

- console handler to all events;
- log handler to all events;
- alert handler to WARNING and CRITICAL events.

## Component Breakdown

### `events.models`

Defines the core data objects.

Primary types:

- `Severity`
- `AlertState`
- `Event`
- `Alert`
- `format_event`
- `format_alert`

`Severity` is an `IntEnum`, which allows ordered comparisons such as `event.severity >= Severity.WARNING`.

`Event` is a frozen dataclass with slots. It normalizes source, event type, message, severity, timestamp, and event ID. Naive timestamps are treated as UTC by attaching UTC timezone information.

`Alert` is a mutable dataclass. It wraps an event and tracks alert lifecycle state, acknowledgment metadata, and resolution notes.

### `events.bus`

Defines the event routing engine.

Primary types:

- `Subscription`
- `_SuppressionState`
- `EventBus`

`Subscription` stores the handler, name, ID, event-type filter, and severity filter.

`EventBus` stores active subscriptions, bounded history, suppression windows, and a subscription ID sequence.

Important methods:

- `subscribe()`
- `unsubscribe()`
- `list_subscriptions()`
- `publish()`
- `replay()`
- `restore_history_snapshot()`

### `events.handlers`

Defines callable handler objects.

Primary types:

- `Handler` protocol
- `ConsoleHandler`
- `LogHandler`
- `AlertHandler`

`ConsoleHandler` formats events and emits them to a provided output function.

`LogHandler` stores raw events and formatted records in memory.

`AlertHandler` sends WARNING and CRITICAL events to an `AlertManager`.

### `events.alert_manager`

Defines alert storage and query behavior.

Primary type:

- `AlertManager`

Important methods:

- `create_alert()`
- `get_alert()`
- `acknowledge_alert()`
- `resolve_alert()`
- `all_alerts()`
- `active_alerts()`
- `unacknowledged_alerts()`
- `alerts_by_severity()`
- `alerts_by_source()`
- `filter_alerts()`
- `replace_alerts_for_restore()`

### `events.cli`

Defines the interactive command shell.

Primary types:

- `_CommandParser`
- `EventShell`
- `main()`

`_CommandParser` overrides `argparse.ArgumentParser.error()` so command parsing errors raise `ValueError` instead of terminating the whole shell.

`EventShell` extends `cmd.Cmd` and implements shell commands such as `publish`, `handlers`, `subscribe`, `unsubscribe`, `history`, `alerts`, `ack`, `resolve`, `replay`, `log`, `exit`, and `quit`.

### `main.py`

Small entry point that imports `events.cli.main` and exits with its return code.

## Module Dependency Graph

```text
main.py
  └── events.cli
        ├── argparse / cmd / shlex / datetime.timedelta
        ├── events.alert_manager
        ├── events.bus
        ├── events.handlers
        └── events.models

events.handlers
  ├── typing.Protocol / Callable
  ├── events.alert_manager
  └── events.models

events.bus
  ├── collections.deque
  ├── dataclasses
  ├── datetime
  ├── itertools.count
  ├── events.handlers
  └── events.models

events.alert_manager
  └── events.models

events.__init__
  ├── events.alert_manager
  ├── events.bus
  ├── events.handlers
  └── events.models
```

## Core Algorithms & Logic

### Event normalization

When an `Event` is created:

1. Strip `source`, `event_type`, and `message`.
2. Convert severity using `Severity.from_value()`.
3. Attach UTC timezone if the timestamp is naive.
4. Reject empty source, empty event type, or empty message.
5. Store the normalized values on the frozen dataclass using `object.__setattr__`.

### Subscription matching

Each subscription checks two independent filters:

1. Event type matches if the subscription has no type filter or the event type is present in the filter set.
2. Severity matches if the subscription has no severity filter or the event severity is present in the filter set.

The event is dispatched only when both filters match.

### Publishing

`EventBus.publish(event)` calls `_events_to_dispatch(event)` first. That function returns:

- the original event;
- a suppression-summary event;
- or an empty list if the event is suppressed.

Every returned event is dispatched to matching handlers and added to history.

### Deduplication

Deduplication key:

```text
(source, event_type)
```

For each key, the bus stores recent timestamps in a deque.

Algorithm:

1. Compute cutoff as `event.timestamp - dedup_window`.
2. Remove timestamps older than cutoff.
3. Reset summary state if the recent count has dropped below threshold.
4. Append the current event timestamp.
5. If count is less than or equal to threshold, dispatch the original event.
6. If count is over threshold and summary has not been emitted, dispatch one `suppression_summary` event.
7. If count is over threshold and summary already emitted, suppress the event completely.

The summary event uses the same source and severity as the triggering event and includes a message explaining that deduplication engaged.

### History ring buffer

`EventBus` uses:

```python
deque(maxlen=max_history)
```

When history exceeds the configured size, the oldest events are dropped automatically.

### Replay

`EventBus.replay()` dispatches stored events to current subscriptions with `record_history=False`.

Replay therefore exercises handlers without growing the bus history.

### Alert creation

`AlertHandler` checks:

```python
event.severity >= Severity.WARNING
```

If true, it calls `AlertManager.create_alert(event)`.

`AlertManager.create_alert()` also ignores INFO events defensively.

### Alert lifecycle

A new alert starts in `AlertState.NEW`.

`acknowledge(user)`:

- requires nonblank user;
- rejects acknowledgment of resolved alerts;
- sets state to `ACKNOWLEDGED`;
- records `acknowledged_by`;
- records `acknowledged_at`.

`resolve(notes)`:

- requires nonblank notes;
- sets state to `RESOLVED`;
- records resolution notes.

## Data Structures

| Structure | Purpose |
|---|---|
| `Severity` | Ordered event severity levels: INFO, WARNING, CRITICAL |
| `AlertState` | Alert lifecycle: new, acknowledged, resolved |
| `Event` | Immutable event record |
| `Alert` | Mutable alert lifecycle record |
| `Subscription` | Handler plus event type and severity filters |
| `_SuppressionState` | Recent timestamps and suppression flags for a repeated event stream |
| `deque[Event]` | Ring-buffer event history |
| `dict[str, Subscription]` | Subscription registry |
| `dict[tuple[str, str], _SuppressionState]` | Deduplication state by source and event type |
| `dict[str, Alert]` | Alert storage keyed by alert/event ID |
| `LogHandler.events` | Raw captured events |
| `LogHandler.records` | Formatted captured event strings |

## State Management

All state is in memory.

`EventBus` owns:

- history;
- subscriptions;
- deduplication state;
- subscription ID sequence.

`AlertManager` owns:

- alert dictionary.

`LogHandler` owns:

- raw captured events;
- formatted records.

`EventShell` owns:

- bus;
- alert manager;
- log handler;
- available handler map.

Events themselves do not mutate after creation. Alerts mutate during acknowledgment and resolution.

## Error Handling Strategy

The app uses standard exceptions rather than a custom application error hierarchy.

Model validation raises `ValueError` for:

- unknown severity;
- empty event source;
- empty event type;
- empty event message;
- blank acknowledgment user;
- acknowledging resolved alerts;
- blank resolution notes;
- invalid bus configuration.

Alert lookup raises `KeyError` when an alert ID does not exist.

The CLI catches parse and validation errors inside command handlers and prints command-specific messages such as:

- `publish error: ...`
- `subscribe error: ...`
- `alerts error: ...`
- `ack error: ...`
- `resolve error: ...`
- `history error: ...`
- `log error: ...`
- `replay error: ...`

Unknown shell commands are handled by `EventShell.default()`.

One important behavior is that handler exceptions are not caught inside the bus. Tests verify that a raising handler stops later subscribers for that dispatch.

## External Dependencies

Runtime dependencies:

- None beyond the Python standard library.

Development dependency:

- `pytest>=8`

Packaging:

- package name: `vaultos-events`;
- import package: `events`;
- Python requirement: `>=3.10`;
- build backend: `setuptools.build_meta`.

## Concurrency Model

The app is synchronous and single-process.

There are no threads, async tasks, subprocesses, sockets, queues, or background workers. This is intentional. The goal is to make event routing explicit and testable before introducing concurrency.

## Known Limitations

- State disappears when the process exits.
- There is no durable event store.
- There is no persistent alert database.
- There is no handler isolation.
- A failing handler can prevent later matching handlers from receiving an event.
- Deduplication does not include message content.
- Deduplication summary events can themselves generate alerts when severity is WARNING or CRITICAL.
- Replay can trigger handlers again, so it is not side-effect-free.
- CLI subscription names refer only to built-in handler instances.
- There is no JSON import/export or machine-readable CLI output.
- There is no direct integration with earlier Vault OS apps.

## Design Patterns Used

- **Observer / Publish-Subscribe:** producers publish events to a bus, and subscribers react independently.
- **Strategy:** handlers are interchangeable callable strategies.
- **Protocol:** `Handler` defines the callable interface expected by the bus.
- **Value Object:** `Event` is immutable and identity-bearing.
- **State Machine:** alerts move through new, acknowledged, and resolved states.
- **Ring Buffer:** event history uses `deque(maxlen=...)`.
- **Facade:** `EventShell` wraps the library into a user-facing operational interface.
- **Repository-like Manager:** `AlertManager` stores and queries alert records.

---

# Interface Design Specification
## App 19 — Events
**Vault OS Group | Document 3 of 5**

---

## Invocation Syntax

### Run from source

```bash
python main.py
```

### Install development dependencies

```bash
pip install -e ".[dev]"
```

### Test-only install

```bash
pip install -r requirements.txt
```

### Run tests

```bash
pytest
```

The CLI starts an interactive shell with the prompt:

```text
events>
```

## Argument Reference Table

The top-level `main.py` entry point accepts no documented command-line options.

| Name | Type | Required | Default | Accepted Values | Description |
|---|---:|---:|---|---|---|
| None | N/A | N/A | N/A | N/A | The application enters the interactive shell immediately. |

## Interactive Command Reference

### `publish`

```text
publish SOURCE TYPE SEVERITY MESSAGE
```

Publishes an event. With no arguments, prompts interactively for source, event type, severity, and message.

| Field | Type | Required | Default | Accepted Values | Description |
|---|---:|---:|---|---|---|
| `SOURCE` | string | yes | none | nonblank text | Component or subsystem emitting the event |
| `TYPE` | string | yes | none | nonblank text | Event category |
| `SEVERITY` | string | yes | none | INFO, WARNING, CRITICAL | Event severity |
| `MESSAGE` | string | yes | none | nonblank text | Human-readable event message |

### `handlers`

```text
handlers
```

Lists available handlers and active subscriptions.

### `subscribe`

```text
subscribe HANDLER [--type EVENT_TYPE ...] [--severity LEVEL ...]
```

| Field | Type | Required | Default | Accepted Values | Description |
|---|---:|---:|---|---|---|
| `HANDLER` | string | yes | none | console, log, alert | Handler to subscribe |
| `--type` | string | no | all types | any nonblank event type | Restricts subscription to one or more event types |
| `--severity` | string | no | all severities | INFO, WARNING, CRITICAL | Restricts subscription to one or more severities |

### `unsubscribe`

```text
unsubscribe SUBSCRIPTION_ID
```

Removes a subscription by ID.

| Field | Type | Required | Default | Accepted Values | Description |
|---|---:|---:|---|---|---|
| `SUBSCRIPTION_ID` | string | yes | none | existing subscription ID such as `sub-4` | Subscription to remove |

### `history`

```text
history [LIMIT]
```

Shows event history.

| Field | Type | Required | Default | Accepted Values | Description |
|---|---:|---:|---|---|---|
| `LIMIT` | integer | no | all history | integer | Number of most recent events to show |

### `log`

```text
log [LIMIT]
```

Shows formatted records captured by the log handler.

| Field | Type | Required | Default | Accepted Values | Description |
|---|---:|---:|---|---|---|
| `LIMIT` | integer | no | all records | integer | Number of most recent log records to show |

### `replay`

```text
replay [COUNT]
```

Re-dispatches history through current subscribers without adding the replayed events to history.

| Field | Type | Required | Default | Accepted Values | Description |
|---|---:|---:|---|---|---|
| `COUNT` | integer | no | all history | integer | Number of most recent historical events to replay |

### `alerts`

```text
alerts [--all] [--severity LEVEL] [--source SOURCE] [--unacknowledged]
```

Displays alerts with optional filters.

| Field | Type | Required | Default | Accepted Values | Description |
|---|---:|---:|---|---|---|
| `--all` | flag | no | false | present/absent | Include resolved alerts |
| `--severity` | string | no | all severities | INFO, WARNING, CRITICAL | Filter by severity |
| `--source` | string | no | all sources | exact source string | Filter by event source |
| `--unacknowledged` | flag | no | false | present/absent | Show only alerts in NEW state |

### `ack`

```text
ack ALERT_ID USER
```

Acknowledges an alert.

| Field | Type | Required | Default | Accepted Values | Description |
|---|---:|---:|---|---|---|
| `ALERT_ID` | string | yes | none | existing alert ID | Alert to acknowledge |
| `USER` | string | yes | none | nonblank string | Operator acknowledging the alert |

### `resolve`

```text
resolve ALERT_ID NOTES
```

Resolves an alert.

| Field | Type | Required | Default | Accepted Values | Description |
|---|---:|---:|---|---|---|
| `ALERT_ID` | string | yes | none | existing alert ID | Alert to resolve |
| `NOTES` | string | yes | none | nonblank text | Resolution notes |

### `exit` / `quit` / EOF

Leaves the shell.

## Input Contract

Event inputs must satisfy:

- source is nonblank;
- event type is nonblank;
- message is nonblank;
- severity is INFO, WARNING, or CRITICAL.

Alert lifecycle inputs must satisfy:

- alert ID exists;
- acknowledgment user is nonblank;
- resolution notes are nonblank;
- resolved alerts cannot be acknowledged again.

Subscription inputs must satisfy:

- handler name is one of the available handlers;
- severities are valid enum values.

History, log, and replay limits must be integers when provided.

## Output Contract

The shell writes human-readable text to stdout.

Events are formatted approximately as:

```text
[2026-04-12T18:00:00+00:00] WARNING  camera-1         motion_detected          Motion detected.
```

Alerts are formatted as pipe-delimited key-value fields:

```text
id=<uuid> | state=new | severity=WARNING | source=door-1 | type=access_denied | message=Badge rejected.
```

Tables are not used; the CLI favors short lists and log-style output.

## Exit Code Reference

| Situation | Exit Code |
|---|---:|
| Normal shell exit through `exit`, `quit`, or EOF | 0 |
| Unhandled Python exception | nonzero, managed by Python runtime |

`events.cli.main()` returns `0` after the command loop exits.

## Error Output Behavior

The shell does not raise most user input errors to the terminal. It catches them and prints command-specific error messages.

Examples:

```text
publish error: Unknown severity 'BAD'. Expected one of: INFO, WARNING, CRITICAL.
subscribe error: unknown handler 'file'. Available: alert, console, log.
unsubscribe error: subscription id is required.
history error: limit must be an integer.
ack error: "No alert found for id 'missing'."
resolve error: Resolution notes cannot be empty.
```

Unknown commands use:

```text
Unknown command: <command>. Type 'help' for available commands.
```

## Environment Variables

None.

## Configuration Files

None.

Runtime behavior is configured in code through constructor parameters:

- `EventBus(max_history=50, dedup_threshold=3, dedup_window=timedelta(seconds=60))` in the CLI.
- Custom values can be used programmatically when constructing `EventBus`.

## Side Effects

- Prints output to stdout.
- Stores events in in-memory history.
- Stores formatted log records in `LogHandler`.
- Stores alerts in `AlertManager`.
- Mutates alert state during acknowledgment and resolution.
- Replays events through current handlers.
- Does not write files.
- Does not perform network calls.
- Does not persist across process restarts.

## Usage Examples

### Basic event publish

```text
events> publish door-1 access_granted INFO Badge accepted
[2026-...+00:00] INFO     door-1           access_granted           Badge accepted
```

### Warning event creates alert

```text
events> publish door-1 access_denied WARNING Badge rejected
events> alerts --unacknowledged
Alerts:
  - id=<uuid> | state=new | severity=WARNING | source=door-1 | type=access_denied | message=Badge rejected
```

### Acknowledge and resolve alert

```text
events> ack <uuid> operator-1
Acknowledged alert <uuid>.
events> resolve <uuid> Badge reissued after identity check
Resolved alert <uuid>.
```

### Subscribe log handler to one event type

```text
events> subscribe log --type motion_detected
Subscribed log as sub-4.
```

### View history

```text
events> history 5
Event history:
  - [2026-...+00:00] WARNING  camera-1         motion_detected          Motion detected
```

### Replay events

```text
events> replay 3
Replayed 3 event(s).
```

### Intentional failure: bad severity

```text
events> publish sensor-1 heat BAD_LEVEL Too hot
publish error: Unknown severity 'BAD_LEVEL'. Expected one of: INFO, WARNING, CRITICAL.
```

### Intentional failure: missing subscription ID

```text
events> unsubscribe
unsubscribe error: subscription id is required.
```

---

# Runbook
## App 19 — Events
**Vault OS Group | Document 4 of 5**

---

## Prerequisites

- Python 3.10 or newer.
- Repository checked out locally.
- Terminal or command prompt.
- Optional virtual environment.
- `pytest>=8` for tests.

## Installation Procedure

From the repository root:

```bash
python -m venv .venv
```

Activate the environment.

Windows:

```bash
.venv\Scripts\activate
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Install in editable development mode:

```bash
pip install -e ".[dev]"
```

Or install test dependency only:

```bash
pip install -r requirements.txt
```

## Configuration Steps

No external configuration is required.

The default shell creates:

```python
EventBus(max_history=50, dedup_threshold=3, dedup_window=timedelta(seconds=60))
```

To change these values, instantiate `EventBus` programmatically rather than using the default shell.

## Standard Operating Procedures

### Start the shell

```bash
python main.py
```

Expected startup:

```text
Vault OS Event Engine. Type 'help' to list commands.
events>
```

### List available commands

```text
events> help
```

### Publish a normal event

```text
events> publish device-1 boot INFO System started
```

### Publish a warning event and review alert

```text
events> publish door-1 access_denied WARNING Badge rejected
events> alerts --unacknowledged
```

### Acknowledge an alert

```text
events> ack <alert_id> operator-1
```

### Resolve an alert

```text
events> resolve <alert_id> Investigation complete
```

### View event history

```text
events> history
events> history 10
```

### View log handler output

```text
events> log
events> log 10
```

### Replay stored events

```text
events> replay
events> replay 5
```

### List handlers and subscriptions

```text
events> handlers
```

### Add a filtered subscription

```text
events> subscribe log --type motion_detected --severity WARNING
```

### Remove a subscription

```text
events> unsubscribe sub-4
```

### Exit

```text
events> exit
```

or

```text
events> quit
```

## Health Checks

### Health check 1 — CLI starts

Command:

```bash
python main.py
```

Pass condition:

```text
events>
```

appears.

### Health check 2 — INFO publish reaches console/log

Commands:

```text
publish device-1 boot INFO System started
history 1
log 1
```

Pass condition:

- console prints the event;
- history includes `boot`;
- log includes `boot`.

### Health check 3 — WARNING publish creates alert

Commands:

```text
publish door-1 access_denied WARNING Badge rejected
alerts --unacknowledged
```

Pass condition:

- alert output includes `access_denied`;
- alert state is `new`;
- severity is `WARNING`.

### Health check 4 — Deduplication engages

Publish the same source/type more than the threshold inside the window.

Pass condition:

- one `suppression_summary` event appears;
- follow-up repeated events may be suppressed.

### Health check 5 — Tests run

Command:

```bash
pytest
```

Pass condition:

- test suite completes successfully.

## Expected Output Samples

### Event output

```text
[2026-04-12T18:00:00+00:00] WARNING  camera-1         motion_detected          Motion detected.
```

### Alert output

```text
id=8aa... | state=new | severity=WARNING | source=door-1 | type=access_denied | message=Badge rejected.
```

### History output

```text
Event history:
  - [2026-04-12T18:00:00+00:00] INFO     device-1         boot                     System started.
```

### Log output

```text
Log records:
  - [2026-04-12T18:00:00+00:00] INFO     device-1         boot                     System started.
```

### Replay output

```text
Replayed 2 event(s).
```

## Known Failure Modes

| Failure Mode | Symptom | Likely Cause | Recovery |
|---|---|---|---|
| Invalid severity | `publish error: Unknown severity...` | Severity not INFO/WARNING/CRITICAL | Re-run with valid severity |
| Blank event field | `publish error: Event ... cannot be empty.` | Source/type/message blank | Provide nonblank values |
| Bad subscription handler | `subscribe error: unknown handler...` | Handler name not registered | Use `handlers` to list valid names |
| Invalid alert ID | `ack error` or `resolve error` | Alert does not exist | Run `alerts --all` and copy exact ID |
| Empty resolution notes | `resolve error: Resolution notes cannot be empty.` | Notes missing | Provide notes |
| Bad numeric limit | `history error`, `log error`, or `replay error` | Non-integer limit | Use integer or omit limit |
| Suppressed event | `Event suppressed by deduplication.` | Repeated event stream exceeded threshold | Wait for dedup window or change source/type |
| Handler exception | Python exception escapes from publish | Handler raised during dispatch | Fix or remove handler |

## Troubleshooting Decision Tree

```text
CLI will not start?
├── Is Python 3.10+ installed?
│   ├── No → install supported Python.
│   └── Yes
├── Are you in the repo root?
│   ├── No → cd into Events.
│   └── Yes
├── Does `python main.py` work?
│   ├── No → install editable package or inspect import error.
│   └── Yes → CLI is healthy.

Event not visible?
├── Was it suppressed by deduplication?
│   ├── Yes → wait for window or inspect history.
│   └── No
├── Is a matching handler subscribed?
│   ├── No → use `subscribe`.
│   └── Yes
└── Did handler raise?
    ├── Yes → fix handler.
    └── No → inspect command syntax.

Alert missing?
├── Was event severity INFO?
│   ├── Yes → expected; INFO does not create alerts.
│   └── No
├── Is alert handler subscribed?
│   ├── No → subscribe alert handler.
│   └── Yes
└── Was event suppressed?
    ├── Yes → suppressed originals do not create alerts.
    └── No → inspect AlertManager state.
```

## Dependency Failure Handling

The runtime uses only the Python standard library, so there are no runtime package failures beyond Python itself.

For test dependency issues:

```bash
pip install -e ".[dev]"
```

or:

```bash
pip install -r requirements.txt
```

Then retry:

```bash
pytest
```

## Recovery Procedures

### Recover from bad shell input

Re-enter the command with corrected arguments. The shell is designed to keep running after normal command errors.

### Recover from noisy event stream

Wait until the deduplication window passes, or use a different event type/source for distinct incidents.

### Recover from missing alert ID

Run:

```text
alerts --all
```

Copy the full alert ID and retry `ack` or `resolve`.

### Recover from bad subscription state

List current subscriptions:

```text
handlers
```

Remove unwanted subscriptions:

```text
unsubscribe <subscription_id>
```

### Recover from stale in-memory state

Exit and restart:

```text
exit
python main.py
```

Because state is in memory, restart clears history, logs, alerts, and custom subscriptions.

## Logging Reference

There is no file logging.

In-memory logging is handled by `LogHandler`.

Commands:

```text
log
log 10
```

Programmatic API:

```python
log_handler.tail(limit)
```

Event formatting uses `format_event(event)`.

Alert formatting uses `format_alert(alert)`.

## Maintenance Notes

- Keep `Event` immutable.
- Keep alert lifecycle transitions explicit.
- Add new handlers as callables that accept an `Event`.
- Preserve replay behavior: replay should dispatch without growing history.
- Be careful when adding handler exception handling; tests currently document that a raising handler stops later subscribers.
- Keep runtime dependency-free unless a strong reason is documented.
- If persistence is added later, restore methods already exist for bus history, log output, and alert storage.

---

# Lessons Learned
## App 19 — Events
**Vault OS Group | Document 5 of 5**

---

## Project Summary

Events introduced a different kind of architecture from the earlier Vault OS apps. Instead of one object directly calling another, this project uses an event bus to decouple producers from consumers.

The main outcome is a working facility event engine with:

- immutable event records;
- severity ordering;
- alert lifecycle management;
- filtered subscriptions;
- console, log, and alert handlers;
- deduplication;
- ring-buffer history;
- replay;
- an interactive shell.

The project demonstrates the difference between “something happened” and “someone needs to respond.” That distinction is the difference between an event and an alert.

## Original Goals vs. Actual Outcome

### Original goals

- Model facility events as structured records.
- Publish events through a bus.
- Subscribe handlers by type and severity.
- Generate alerts for serious events.
- Track alert acknowledgment and resolution.
- Suppress noisy duplicate events.
- Keep recent history.
- Provide replay.
- Expose the system through a CLI.

### Actual outcome

The implementation meets the main goals. The system has a compact but realistic event-driven core. It is not a production broker, but it demonstrates the design ideas clearly.

The app also includes a stronger-than-minimum CLI. The shell supports interactive publishing, subscription management, alert filtering, acknowledgment, resolution, history, log inspection, replay, and graceful handling of bad user input.

## Technical Decisions That Paid Off

### Immutable events

Making `Event` frozen was a strong choice. It makes the history buffer more trustworthy because recorded events are not accidentally modified after publication.

### Ordered severity enum

Using `IntEnum` for `Severity` made alert thresholds simple:

```python
event.severity >= Severity.WARNING
```

That is clearer than string comparisons or manual priority maps.

### Separate `AlertManager`

Keeping alert lifecycle logic out of the event bus avoided mixing routing concerns with operational response concerns.

### Handler protocol

Using a callable protocol kept handlers flexible. A handler can be a class instance, function, or lambda as long as it accepts an event.

### Ring-buffer history

Using `deque(maxlen=...)` solved bounded history with very little code and no manual trimming.

### Synchronous dispatch

Synchronous dispatch made the project much easier to reason about and test. The tests can assert exact results immediately after a publish call.

### CLI parser that does not exit the shell

Overriding `argparse.ArgumentParser.error()` prevented malformed subcommands from killing the whole interactive session.

## Technical Decisions That Created Debt

### No handler isolation

If one handler raises, later handlers do not receive that event. This behavior is tested, so it is documented, but it would be dangerous in a production event engine.

### Replay can cause side effects

Replay is useful, but it re-runs handlers. If an alert handler is subscribed, replaying warning events can create additional alert records. That is acceptable for the learning app but would require stricter semantics in a production system.

### In-memory only

All state is lost on restart. This keeps the project scoped, but it limits operational realism.

### Deduplication key is simple

The deduplication key uses source and event type. That is a reasonable first version, but it may suppress events with different messages if they share the same source and type.

### No structured output

The CLI output is human-readable but not machine-readable. JSON output would help if another tool consumed the event engine.

## What Was Harder Than Expected

The hardest part was deciding how much behavior belongs in the bus. The bus has to route events, store history, deduplicate noisy event streams, and replay history. It would be easy for it to become too large.

Another subtle challenge was alert lifecycle. Alerts are not just events. They need mutable state, user actions, and resolution notes. Keeping this separate from the immutable event model required a cleaner separation of responsibilities.

Deduplication also had tricky edge cases. The bus needs to allow the first few repeated events, emit exactly one summary when the threshold is exceeded, suppress follow-ups, and reset once the event stream quiets down.

## What Was Easier Than Expected

The Observer pattern mapped well to Python callables. A handler protocol and `__call__` classes were enough to model subscriptions without a complex class hierarchy.

The standard library was also sufficient. `dataclasses`, `Enum`, `deque`, `cmd`, `argparse`, `shlex`, `datetime`, and `uuid` covered the app’s needs.

Testing was straightforward because the bus is synchronous. Publishing an event immediately returns what was dispatched and immediately updates history, logs, and alerts.

## Python-Specific Learnings

- `dataclass(frozen=True)` is useful for event records, but normalization inside `__post_init__` requires `object.__setattr__`.
- `IntEnum` works well when enum values have meaningful ordering.
- `StrEnum` is a clean fit for human-readable lifecycle states.
- `deque(maxlen=...)` is ideal for fixed-size history buffers.
- `Protocol` can define structural handler requirements without forcing inheritance.
- `cmd.Cmd` is useful for stateful interactive shells.
- `shlex.split()` makes command parsing safer for quoted messages.
- `argparse` can be adapted for shell subcommands by overriding `error()`.

## Architecture Insights

The most important architecture insight is that event-driven systems are about decoupling time and knowledge. A publisher should not need to know who will consume an event. A handler should only need to describe what it cares about.

The second insight is that facts and responses should be separate. Events are facts. Alerts are responses to certain facts. This distinction keeps the system easier to extend.

The third insight is that replay is powerful but dangerous. Once handlers have side effects, replay must be designed carefully.

The fourth insight is that suppression and deduplication are not just optimizations. They are operational design choices. A noisy system can overwhelm operators unless repeated events are summarized.

## Testing Gaps

The tests cover the most important behaviors:

- subscription matching by type and severity;
- warning events generating alerts;
- alert acknowledgment and resolution;
- deduplication summary and suppression;
- ring-buffer history;
- replay without history duplication;
- handler exception behavior;
- alert filtering;
- log tail behavior;
- shell commands for handlers, publishing, alerts, history, log, replay, subscribe, unsubscribe, and unknown commands.

Remaining gaps:

- no tests for custom restore methods;
- no tests for very large histories;
- no tests for simultaneous subscriptions being removed during dispatch;
- no tests for multiple deduplication keys interleaving;
- no tests for replay side effects on alert duplication;
- no tests for interactive prompt-mode `publish` with no arguments;
- no tests for raw terminal EOF from a full shell session.

## Reusable Patterns Identified

- Frozen event records for audit-friendly logs.
- Mutable lifecycle wrapper objects for operational workflows.
- `EventBus` plus handler protocol for decoupled dispatch.
- Enum-based severity thresholds.
- `deque(maxlen=...)` ring buffers.
- CLI subcommands parsed with `argparse` inside a `cmd.Cmd` shell.
- Deduplication by stream key and sliding time window.
- Manager object for filtered views over mutable records.

## If I Built This Again

I would keep the same broad architecture but make a few improvements:

1. Add optional handler isolation so one bad handler does not block later subscribers.
2. Add structured JSON output for events and alerts.
3. Add optional persistent event and alert storage.
4. Add a replay mode that can skip alert creation or mark replayed events explicitly.
5. Add event correlation IDs for grouping related facility events.
6. Add source and type normalization rules.
7. Add a dead-letter handler for failed event deliveries.
8. Add command history or batch script support for demos.
9. Add explicit tests around restore hooks and replay side effects.

## Open Questions

- Should replay create new alerts, or should replayed events be marked as historical?
- Should handler exceptions be isolated by default?
- Should deduplication key include message text?
- Should deduplication summary events always preserve the original severity?
- Should alerts have separate IDs from their underlying event IDs?
- Should the CLI support non-interactive one-shot commands?
- Should event history and alert state persist to disk?
- Should future Vault OS apps publish into this bus directly?
- Should there be a standardized event taxonomy across all Vault OS apps?
