# Vault OS — Facility Event Engine

A small Python library and interactive CLI that models a **publish–subscribe event bus**, **severity-based alerting**, **deduplication**, **ring-buffer history**, and **replay**. The runtime uses only the **standard library**; **pytest** is used for tests.

## Quick start

**Requirements:** Python 3.10 or newer.

```bash
cd Events
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -e ".[dev]"
```

Run the shell:

```bash
python main.py
```

Run the test suite:

```bash
pytest
```

Install tests only (without editable package):

```bash
pip install -r requirements.txt
pytest
```

*(For imports like `from events import EventBus` to resolve, run `pytest` from this directory or use `pip install -e .`.)*

## Project layout

| Path | Role |
|------|------|
| `events/` | Package: models, `EventBus`, handlers, `AlertManager`, CLI (`EventShell`) |
| `main.py` | Entry point → `events.cli:main` |
| `tests/test_events.py` | Unit and CLI tests |

## CLI overview

After `python main.py`, try `help`. Useful commands include `publish`, `handlers`, `subscribe` / `unsubscribe`, `history`, `log`, `replay`, `alerts` (with filters), `ack`, and `resolve`.

## Library overview

- **`Event`** — Immutable record: source, type, severity (`INFO` / `WARNING` / `CRITICAL`), message, timestamp, id.
- **`Alert`** — Wraps an event with state (`new` / `acknowledged` / `resolved`) and lifecycle fields.
- **`EventBus`** — Subscriptions by event type and/or severity; dedup window; history; `replay()`.
- **`AlertManager`** — Creates alerts for `WARNING`+ events; filtered views and acknowledge/resolve.

---

## Features

- **Observer pattern** and separating **event production** from **event consumption**.
- **Event** vs **alert**: an event is a fact; an alert is a judgment that something needs attention.
- **Features implemented here**
  - **Event:** unique id, timestamp, source, event type, severity enum, message.
  - **Alert:** state, acknowledged-by, acknowledged-at, resolution notes; only **WARNING** and **CRITICAL** events auto-create alerts.
  - **EventBus:** subscribe by event type, severity, or both; publish dispatches to matching handlers.
  - **Handler protocol:** callables taking an `Event`; includes **ConsoleHandler**, **LogHandler**, **AlertHandler**.
  - **AlertManager:** stores alerts, acknowledge/resolve, filtered views (unacknowledged, by severity, by source).
  - **Deduplication:** same source + event type beyond a threshold inside a time window → summary event, then suppression.
  - **History:** max size with ring-buffer behavior; **replay()** re-dispatches without duplicating history.
  - **CLI:** publish, subscribe/unsubscribe, history, alerts, ack/resolve, replay.
