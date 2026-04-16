# Schema Folder

Simple JSON Schema files for the repository's main data shapes.

Included files:
- `severity.schema.json`
- `alert-state.schema.json`
- `event.schema.json`
- `alert.schema.json`
- `subscription.schema.json`
- `publish-event-request.schema.json`

Notes:
- These schemas mirror the repository's core models and CLI-facing publish payload.
- `alert_id`, `source`, and `severity` in `alert.schema.json` are marked as read-only convenience fields because they are derived from the nested `event`.
- `subscription.schema.json` uses `handler_name` instead of the raw callable because handlers are not directly serializable.
