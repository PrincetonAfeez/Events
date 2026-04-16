from __future__ import annotations

import io
import unittest
from datetime import UTC, datetime, timedelta

from events import AlertHandler, AlertManager, Event, EventBus, LogHandler, Severity
from events.cli import EventShell
from events.models import AlertState


class EventBusTests(unittest.TestCase):
    def test_handlers_match_by_type_and_severity(self) -> None:
        bus = EventBus(dedup_threshold=10)
        captured: dict[str, list[str]] = {
            "type": [],
            "severity": [],
            "both": [],
            "catch_all": [],
        }

        bus.subscribe(lambda event: captured["type"].append(event.event_type), name="type", event_types=["motion"])
        bus.subscribe(
            lambda event: captured["severity"].append(event.event_type),
            name="severity",
            severities=[Severity.CRITICAL],
        )
        bus.subscribe(
            lambda event: captured["both"].append(event.event_type),
            name="both",
            event_types=["motion"],
            severities=[Severity.CRITICAL],
        )
        bus.subscribe(lambda event: captured["catch_all"].append(event.event_type), name="catch_all")

        bus.publish(
            Event(
                source="camera-7",
                event_type="motion",
                severity=Severity.CRITICAL,
                message="Motion detected in loading bay.",
            )
        )

        self.assertEqual(captured["type"], ["motion"])
        self.assertEqual(captured["severity"], ["motion"])
        self.assertEqual(captured["both"], ["motion"])
        self.assertEqual(captured["catch_all"], ["motion"])

    def test_warning_events_generate_alerts(self) -> None:
        alert_manager = AlertManager()
        bus = EventBus(dedup_threshold=10)
        bus.subscribe(AlertHandler(alert_manager), name="alerting")

        bus.publish(Event(source="door-1", event_type="access_granted", severity="INFO", message="All clear."))
        bus.publish(
            Event(
                source="door-1",
                event_type="access_denied",
                severity="WARNING",
                message="Badge rejected.",
            )
        )

        alerts = alert_manager.all_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].event.event_type, "access_denied")

    def test_alerts_can_be_acknowledged_and_resolved(self) -> None:
        alert_manager = AlertManager()
        alert = alert_manager.create_alert(
            Event(
                source="sensor-1",
                event_type="temp_threshold_exceeded",
                severity=Severity.WARNING,
                message="Server room exceeded temperature threshold.",
            )
        )

        assert alert is not None
        alert_manager.acknowledge_alert(alert.alert_id, "operator-1")
        self.assertEqual(alert.acknowledged_by, "operator-1")
        self.assertIsNotNone(alert.acknowledged_at)

        alert_manager.resolve_alert(alert.alert_id, "HVAC reset completed.")
        self.assertEqual(alert.resolution_notes, "HVAC reset completed.")
        self.assertEqual(alert.state.value, "resolved")

    def test_deduplication_emits_one_summary_then_suppresses_followups(self) -> None:
        bus = EventBus(dedup_threshold=2, dedup_window=timedelta(seconds=30))
        log = LogHandler()
        bus.subscribe(log, name="log")
        base_time = datetime(2026, 4, 12, 18, 0, tzinfo=UTC)

        first = bus.publish(
            Event(
                source="camera-1",
                event_type="motion_detected",
                severity=Severity.WARNING,
                message="Motion detected.",
                timestamp=base_time,
            )
        )
        second = bus.publish(
            Event(
                source="camera-1",
                event_type="motion_detected",
                severity=Severity.WARNING,
                message="Motion detected again.",
                timestamp=base_time + timedelta(seconds=5),
            )
        )
        third = bus.publish(
            Event(
                source="camera-1",
                event_type="motion_detected",
                severity=Severity.WARNING,
                message="Still seeing motion.",
                timestamp=base_time + timedelta(seconds=10),
            )
        )
        fourth = bus.publish(
            Event(
                source="camera-1",
                event_type="motion_detected",
                severity=Severity.WARNING,
                message="Repeated motion event.",
                timestamp=base_time + timedelta(seconds=15),
            )
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(len(third), 1)
        self.assertEqual(third[0].event_type, EventBus.SUMMARY_EVENT_TYPE)
        self.assertEqual(len(fourth), 0)
        self.assertEqual(len(log.events), 3)

    def test_history_acts_like_a_ring_buffer(self) -> None:
        bus = EventBus(max_history=2, dedup_threshold=10)

        bus.publish(Event(source="device-1", event_type="a", severity=Severity.INFO, message="one"))
        bus.publish(Event(source="device-1", event_type="b", severity=Severity.INFO, message="two"))
        bus.publish(Event(source="device-1", event_type="c", severity=Severity.INFO, message="three"))

        self.assertEqual([event.event_type for event in bus.history], ["b", "c"])

    def test_replay_calls_handlers_without_duplicating_history(self) -> None:
        bus = EventBus(dedup_threshold=10)
        seen: list[str] = []
        bus.subscribe(lambda event: seen.append(event.event_type), name="collector")

        bus.publish(Event(source="device-1", event_type="online", severity=Severity.INFO, message="Boot complete."))
        bus.publish(
            Event(
                source="device-2",
                event_type="heartbeat",
                severity=Severity.INFO,
                message="Heartbeat received.",
            )
        )

        replayed = bus.replay()

        self.assertEqual(replayed, 2)
        self.assertEqual(seen, ["online", "heartbeat", "online", "heartbeat"])
        self.assertEqual(len(bus.history), 2)

    def test_raising_handler_stops_later_subscribers_for_that_dispatch(self) -> None:
        bus = EventBus(dedup_threshold=10)
        seen: list[str] = []

        def failing(_: Event) -> None:
            raise RuntimeError("handler failure")

        def recording(event: Event) -> None:
            seen.append(event.event_type)

        bus.subscribe(failing, name="failing")
        bus.subscribe(recording, name="recording")

        with self.assertRaises(RuntimeError):
            bus.publish(Event(source="s", event_type="t", severity=Severity.INFO, message="m"))

        self.assertEqual(seen, [])


class AlertManagerQueryTests(unittest.TestCase):
    def test_active_alerts_excludes_resolved(self) -> None:
        manager = AlertManager()
        warn = manager.create_alert(
            Event(source="a", event_type="w", severity=Severity.WARNING, message="warn"),
        )
        crit = manager.create_alert(
            Event(source="b", event_type="c", severity=Severity.CRITICAL, message="crit"),
        )
        assert warn is not None and crit is not None
        manager.resolve_alert(warn.alert_id, "fixed")

        active = manager.active_alerts()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].alert_id, crit.alert_id)

    def test_unacknowledged_alerts_and_alerts_by_severity_and_source(self) -> None:
        manager = AlertManager()
        a = manager.create_alert(
            Event(source="room-a", event_type="heat", severity=Severity.WARNING, message="warm"),
        )
        b = manager.create_alert(
            Event(source="room-b", event_type="smoke", severity=Severity.CRITICAL, message="smoke"),
        )
        assert a is not None and b is not None
        manager.acknowledge_alert(a.alert_id, "op")

        new_only = manager.unacknowledged_alerts()
        self.assertEqual(len(new_only), 1)
        self.assertEqual(new_only[0].alert_id, b.alert_id)

        critical = manager.alerts_by_severity(Severity.CRITICAL)
        self.assertEqual({x.alert_id for x in critical}, {b.alert_id})

        by_source = manager.alerts_by_source("room-a")
        self.assertEqual(len(by_source), 1)
        self.assertEqual(by_source[0].alert_id, a.alert_id)

    def test_filter_alerts_respects_state_and_include_resolved(self) -> None:
        manager = AlertManager()
        alert = manager.create_alert(
            Event(source="x", event_type="y", severity=Severity.WARNING, message="z"),
        )
        assert alert is not None
        manager.acknowledge_alert(alert.alert_id, "u")

        acknowledged = manager.filter_alerts(state=AlertState.ACKNOWLEDGED, include_resolved=True)
        self.assertEqual(len(acknowledged), 1)

        with_resolved = manager.filter_alerts(include_resolved=True)
        self.assertEqual(len(with_resolved), 1)

        manager.resolve_alert(alert.alert_id, "done")
        none_active = manager.filter_alerts(include_resolved=False)
        self.assertEqual(none_active, ())


class LogHandlerTests(unittest.TestCase):
    def test_tail_limits_records(self) -> None:
        log = LogHandler()
        for idx in range(4):
            log(
                Event(
                    source="d",
                    event_type=f"e{idx}",
                    severity=Severity.INFO,
                    message=str(idx),
                )
            )
        self.assertEqual(len(log.tail(2)), 2)
        self.assertEqual(len(log.tail(None)), 4)


class EventShellCliTests(unittest.TestCase):
    def _shell(self) -> tuple[EventShell, io.StringIO]:
        out = io.StringIO()
        shell = EventShell()
        shell.stdout = out
        shell.use_rawinput = False
        return shell, out

    def test_handlers_lists_subscriptions(self) -> None:
        shell, out = self._shell()
        shell.onecmd("handlers")
        text = out.getvalue()
        self.assertIn("Available handlers:", text)
        self.assertIn("Active subscriptions:", text)
        self.assertIn("console", text)

    def test_publish_alerts_ack_resolve_and_unacknowledged_filter(self) -> None:
        shell, out = self._shell()
        shell.onecmd("publish door-1 access_denied WARNING Badge rejected at door")
        shell.onecmd("alerts --unacknowledged")
        text = out.getvalue()
        self.assertIn("Alerts:", text)
        self.assertIn("access_denied", text)
        self.assertIn("id=", text)

        alert_id = ""
        for ln in text.splitlines():
            if "id=" in ln:
                fragment = ln.split("id=", 1)[1]
                alert_id = fragment.split("|", 1)[0].strip()
        self.assertTrue(alert_id)

        shell.onecmd(f"ack {alert_id} operator-1")
        out.truncate(0)
        out.seek(0)
        shell.onecmd("alerts --unacknowledged")
        self.assertIn("(none)", out.getvalue())

    def test_alerts_filters_by_severity_and_source(self) -> None:
        shell, out = self._shell()
        shell.onecmd("publish s1 motion WARNING Motion")
        shell.onecmd("publish s2 fire CRITICAL Fire")
        out.truncate(0)
        out.seek(0)
        shell.onecmd("alerts --severity CRITICAL")
        text = out.getvalue()
        self.assertIn("fire", text)
        self.assertNotIn("motion", text)

        out.truncate(0)
        out.seek(0)
        shell.onecmd("alerts --source s1")
        self.assertIn("motion", out.getvalue())
        self.assertNotIn("fire", out.getvalue())

    def test_history_log_replay_and_bad_publish(self) -> None:
        shell, out = self._shell()
        shell.onecmd("publish unit-9 boot INFO System started")
        out.truncate(0)
        out.seek(0)
        shell.onecmd("history 5")
        self.assertIn("boot", out.getvalue())

        out.truncate(0)
        out.seek(0)
        shell.onecmd("log 10")
        self.assertIn("boot", out.getvalue())

        out.truncate(0)
        out.seek(0)
        shell.onecmd("replay")
        self.assertIn("Replayed", out.getvalue())

        out.truncate(0)
        out.seek(0)
        shell.onecmd("publish x y NOT_A_SEVERITY msg")
        self.assertIn("publish error:", out.getvalue())

    def test_subscribe_unsubscribe_and_unknown_command(self) -> None:
        shell, out = self._shell()
        shell.onecmd("subscribe log --type ping")
        text = out.getvalue()
        self.assertIn("Subscribed log as", text)
        sub_id = text.split("Subscribed log as ")[1].strip().rstrip(".")

        out.truncate(0)
        out.seek(0)
        shell.onecmd(f"unsubscribe {sub_id}")
        self.assertIn("Removed subscription", out.getvalue())

        out.truncate(0)
        out.seek(0)
        shell.onecmd("not-a-real-command")
        self.assertIn("Unknown command:", out.getvalue())


if __name__ == "__main__":
    unittest.main()
