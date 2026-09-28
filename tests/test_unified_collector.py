"""
Tests for btbatterylab.collector.unified_collector.

Scope, deliberately: the pure-logic helpers (_is_generic_name,
_parse_timestamp, _maybe_update_name, _maybe_update_battery), plus an
integration-style test of process_json_line/_handle_ble_event against
a real tmp-path SqliteStorage. The threaded pieces (_polling_loop,
_wait_for_next_poll, start/stop) are timing-dependent and are not
covered here to keep the suite fast and non-flaky; they were verified
manually against real hardware (see docs/roadmap.md).
"""

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from btbatterylab.collector.unified_collector import (
    DeviceState,
    UnifiedCollector,
    _is_generic_name,
)
from btbatterylab.models.battery_reading import BatteryReading
from btbatterylab.models.device import Device


class IsGenericNameTests(unittest.TestCase):
    def test_none_is_generic(self) -> None:
        self.assertTrue(_is_generic_name(None))

    def test_empty_string_is_generic(self) -> None:
        self.assertTrue(_is_generic_name(""))

    def test_bluetooth_prefixed_name_is_generic(self) -> None:
        self.assertTrue(_is_generic_name("Bluetooth AA:BB:CC:DD:EE:FF"))

    def test_prefix_check_is_case_insensitive(self) -> None:
        self.assertTrue(_is_generic_name("BLUETOOTH mouse"))

    def test_real_name_is_not_generic(self) -> None:
        self.assertFalse(_is_generic_name("MX Master 2S"))


class ParseTimestampTests(unittest.TestCase):
    def test_none_returns_none(self) -> None:
        self.assertIsNone(UnifiedCollector._parse_timestamp(None))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(UnifiedCollector._parse_timestamp(""))

    def test_parses_naive_iso_string_unchanged(self) -> None:
        parsed = UnifiedCollector._parse_timestamp("2026-01-01T10:00:00")
        self.assertEqual(parsed, datetime(2026, 1, 1, 10, 0, 0))

    def test_invalid_string_returns_none(self) -> None:
        self.assertIsNone(UnifiedCollector._parse_timestamp("not-a-date"))

    def test_z_suffix_is_normalized_to_a_naive_local_time(self) -> None:
        # BluetoothWatcher (C#) emits UTC timestamps with a "Z" suffix.
        # The result must be naive (so it compares cleanly against
        # other naive timestamps elsewhere in the app) and must
        # represent the same instant as the explicit "+00:00" form.
        via_z = UnifiedCollector._parse_timestamp("2026-01-01T10:00:00Z")
        via_offset = UnifiedCollector._parse_timestamp("2026-01-01T10:00:00+00:00")

        self.assertIsNone(via_z.tzinfo)
        self.assertEqual(via_z, via_offset)


class MaybeUpdateNameTests(unittest.TestCase):
    def test_sets_name_when_state_has_none(self) -> None:
        state = DeviceState(address="AA:BB:CC:DD:EE:FF")
        UnifiedCollector._maybe_update_name(state, "MX Master 2S")
        self.assertEqual(state.name, "MX Master 2S")

    def test_empty_candidate_does_not_overwrite(self) -> None:
        state = DeviceState(address="AA:BB:CC:DD:EE:FF", name="MX Master 2S")
        UnifiedCollector._maybe_update_name(state, None)
        self.assertEqual(state.name, "MX Master 2S")

    def test_generic_name_is_replaced_by_a_real_one(self) -> None:
        state = DeviceState(
            address="AA:BB:CC:DD:EE:FF", name="Bluetooth AA:BB:CC:DD:EE:FF"
        )
        UnifiedCollector._maybe_update_name(state, "MX Master 2S")
        self.assertEqual(state.name, "MX Master 2S")

    def test_real_name_is_not_replaced_by_a_generic_one(self) -> None:
        state = DeviceState(address="AA:BB:CC:DD:EE:FF", name="MX Master 2S")
        UnifiedCollector._maybe_update_name(state, "Bluetooth AA:BB:CC:DD:EE:FF")
        self.assertEqual(state.name, "MX Master 2S")

    def test_real_name_is_not_replaced_by_another_real_name(self) -> None:
        state = DeviceState(address="AA:BB:CC:DD:EE:FF", name="First Name")
        UnifiedCollector._maybe_update_name(state, "Second Name")
        self.assertEqual(state.name, "First Name")


class MaybeUpdateBatteryTests(unittest.TestCase):
    def test_sets_battery_when_state_has_none(self) -> None:
        state = DeviceState(address="AA:BB:CC:DD:EE:FF")
        now = datetime.now()

        UnifiedCollector._maybe_update_battery(state, 77, now, source="ble")

        self.assertEqual(state.battery_percent, 77)
        self.assertEqual(state.battery_timestamp, now)
        self.assertEqual(state.battery_source, "ble")

    def test_newer_reading_replaces_older_one(self) -> None:
        base = datetime.now()
        state = DeviceState(address="AA:BB:CC:DD:EE:FF")
        UnifiedCollector._maybe_update_battery(state, 50, base, source="pnp")

        newer = base + timedelta(minutes=5)
        UnifiedCollector._maybe_update_battery(state, 60, newer, source="ble")

        self.assertEqual(state.battery_percent, 60)
        self.assertEqual(state.battery_timestamp, newer)
        self.assertEqual(state.battery_source, "ble")

    def test_older_reading_does_not_replace_newer_one(self) -> None:
        base = datetime.now()
        state = DeviceState(address="AA:BB:CC:DD:EE:FF")
        UnifiedCollector._maybe_update_battery(state, 60, base, source="ble")

        older = base - timedelta(minutes=5)
        UnifiedCollector._maybe_update_battery(state, 50, older, source="pnp")

        self.assertEqual(state.battery_percent, 60)
        self.assertEqual(state.battery_source, "ble")

    def test_equal_timestamp_does_not_replace(self) -> None:
        base = datetime.now()
        state = DeviceState(address="AA:BB:CC:DD:EE:FF")
        UnifiedCollector._maybe_update_battery(state, 60, base, source="ble")
        UnifiedCollector._maybe_update_battery(state, 99, base, source="pnp")

        self.assertEqual(state.battery_percent, 60)
        self.assertEqual(state.battery_source, "ble")


class ProcessJsonLineTests(unittest.TestCase):
    """
    Exercises process_json_line -> _handle_ble_event end to end against
    a real (tmp-path) SqliteStorage, since that's the actual consumer
    interface JsonlTailMonitor calls. The tail monitor itself is never
    started, so no background thread or file-watching is involved.
    """

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="btb_unified_"))
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

        self.collector = UnifiedCollector(
            jsonl_path=self.tmp_dir / "ble-events.jsonl",
            db_path=self.tmp_dir / "btbatterylab.db",
        )
        self.addCleanup(self.collector._storage.close)

    def _battery_log_count(self, address: str) -> int:
        count, = self.collector._storage._connection.execute(
            "SELECT COUNT(*) FROM battery_log WHERE address = ?", (address,)
        ).fetchone()
        return count

    def test_blank_line_is_a_no_op(self) -> None:
        self.collector.process_json_line("")
        self.collector.process_json_line("   \n")
        self.assertEqual(self.collector.snapshot(), {})

    def test_connection_status_changed_updates_state_and_persists(self) -> None:
        event = {
            "Event": "ConnectionStatusChanged",
            "BluetoothAddress": "aa:bb:cc:dd:ee:ff",
            "Status": "Connected",
            "DeviceName": "MX Master 2S",
            "BatteryPercent": 77,
            "Timestamp": "2026-01-01T10:00:00",
        }
        self.collector.process_json_line(json_line(event))

        state = self.collector.snapshot()["AA:BB:CC:DD:EE:FF"]
        self.assertEqual(state.name, "MX Master 2S")
        self.assertTrue(state.online)
        self.assertEqual(state.battery_percent, 77)
        self.assertEqual(state.battery_source, "ble")
        self.assertEqual(self._battery_log_count("AA:BB:CC:DD:EE:FF"), 1)

    def test_startup_event_type_is_also_handled(self) -> None:
        event = {
            "Event": "Startup",
            "BluetoothAddress": "AA:BB:CC:DD:EE:FF",
            "Status": "Connected",
            "DeviceName": "Headset",
            "Timestamp": "2026-01-01T10:00:00",
        }
        self.collector.process_json_line(json_line(event))
        self.assertIn("AA:BB:CC:DD:EE:FF", self.collector.snapshot())

    def test_unrelated_event_type_is_ignored(self) -> None:
        event = {"Event": "SomethingElse", "BluetoothAddress": "AA:BB:CC:DD:EE:FF"}
        self.collector.process_json_line(json_line(event))
        self.assertEqual(self.collector.snapshot(), {})

    def test_event_without_address_is_ignored(self) -> None:
        event = {"Event": "ConnectionStatusChanged", "Status": "Connected"}
        self.collector.process_json_line(json_line(event))
        self.assertEqual(self.collector.snapshot(), {})

    def test_address_is_normalized_to_uppercase(self) -> None:
        event = {
            "Event": "ConnectionStatusChanged",
            "BluetoothAddress": "aa:bb:cc:dd:ee:ff",
            "Status": "Connected",
        }
        self.collector.process_json_line(json_line(event))
        self.assertIn("AA:BB:CC:DD:EE:FF", self.collector.snapshot())

    def test_every_observation_is_persisted_even_when_out_of_order(self) -> None:
        # Raw history in battery_log keeps every observation, even one
        # that arrives "late" and therefore loses the in-memory
        # "freshest wins" comparison in _maybe_update_battery.
        newer = {
            "Event": "ConnectionStatusChanged",
            "BluetoothAddress": "AA:BB:CC:DD:EE:FF",
            "Status": "Connected",
            "BatteryPercent": 50,
            "Timestamp": "2026-01-01T12:00:00",
        }
        older = {
            "Event": "ConnectionStatusChanged",
            "BluetoothAddress": "AA:BB:CC:DD:EE:FF",
            "Status": "Connected",
            "BatteryPercent": 90,
            "Timestamp": "2026-01-01T08:00:00",
        }
        self.collector.process_json_line(json_line(newer))
        self.collector.process_json_line(json_line(older))

        state = self.collector.snapshot()["AA:BB:CC:DD:EE:FF"]
        self.assertEqual(state.battery_percent, 50)  # the newer one still wins
        self.assertEqual(self._battery_log_count("AA:BB:CC:DD:EE:FF"), 2)

    def test_missing_timestamp_falls_back_to_now(self) -> None:
        before = datetime.now()
        event = {
            "Event": "ConnectionStatusChanged",
            "BluetoothAddress": "AA:BB:CC:DD:EE:FF",
            "Status": "Connected",
        }
        self.collector.process_json_line(json_line(event))
        after = datetime.now()

        state = self.collector.snapshot()["AA:BB:CC:DD:EE:FF"]
        self.assertTrue(before <= state.last_seen <= after)

    def test_classic_device_connect_without_battery_triggers_immediate_poll(self) -> None:
        event = {
            "Event": "ConnectionStatusChanged",
            "BluetoothAddress": "AA:BB:CC:DD:EE:FF",
            "Status": "Connected",
            "BatteryPercent": None,
        }
        self.collector.process_json_line(json_line(event))
        self.assertTrue(self.collector._poll_now_event.is_set())

    def test_disconnect_event_does_not_trigger_immediate_poll(self) -> None:
        event = {
            "Event": "ConnectionStatusChanged",
            "BluetoothAddress": "AA:BB:CC:DD:EE:FF",
            "Status": "Disconnected",
        }
        self.collector.process_json_line(json_line(event))
        self.assertFalse(self.collector._poll_now_event.is_set())

    def test_generic_ble_name_is_upgraded_by_a_later_real_name(self) -> None:
        first = {
            "Event": "ConnectionStatusChanged",
            "BluetoothAddress": "AA:BB:CC:DD:EE:FF",
            "Status": "Connected",
            "DeviceName": "Bluetooth AA:BB:CC:DD:EE:FF",
        }
        second = {
            "Event": "ConnectionStatusChanged",
            "BluetoothAddress": "AA:BB:CC:DD:EE:FF",
            "Status": "Connected",
            "DeviceName": "OPPO Enco Air2",
        }
        self.collector.process_json_line(json_line(first))
        self.collector.process_json_line(json_line(second))

        self.assertEqual(
            self.collector.snapshot()["AA:BB:CC:DD:EE:FF"].name, "OPPO Enco Air2"
        )


class PollPnpBatteryTests(unittest.TestCase):
    """
    _poll_pnp_battery isn't threaded itself (only _polling_loop, which
    calls it, is) - see this module's own docstring - so it's exercised
    directly here, against a real tmp-path SqliteStorage, with
    BluetoothCollector.discover()/read_battery_levels() mocked out
    (same reasoning as tests/test_bluetooth_collector.py: no real
    Windows/PowerShell involved).

    Regression coverage for the Test.txt feedback (2026-09-28):
    "last seen" for offline devices being stuck at dashboard-launch
    time, traced to PnP polling calling record_device_seen() for
    every reading - including stale/cached ones for devices that
    aren't actually online (see ensure_device_exists() in
    SqliteStorage) - and analytics accuracy, traced to a new
    battery_log row being written for every poll even when the value
    hadn't changed (see _last_pnp_percent).
    """

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="btb_pnp_poll_"))
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

        self.collector = UnifiedCollector(
            jsonl_path=self.tmp_dir / "ble-events.jsonl",
            db_path=self.tmp_dir / "btbatterylab.db",
        )
        self.addCleanup(self.collector._storage.close)

    def _battery_rows(self, address: str) -> list[tuple[int, str]]:
        rows = self.collector._storage._connection.execute(
            "SELECT battery_percent, timestamp FROM battery_log "
            "WHERE address = ? ORDER BY timestamp",
            (address,),
        ).fetchall()
        return rows

    def _device_last_seen(self, address: str) -> str | None:
        row = self.collector._storage._connection.execute(
            "SELECT last_seen FROM devices WHERE address = ?", (address,)
        ).fetchone()
        return row[0] if row else None

    def test_pnp_only_reading_never_moves_last_seen(self) -> None:
        # A classic headset that's actually offline: PnP still reports
        # its last cached battery value, with a fabricated "now"
        # timestamp (no BatteryUpdated property) each poll - last_seen
        # must not follow that fabricated timestamp forward.
        address = "AA:BB:CC:DD:EE:FF"
        first_poll_time = datetime(2026, 1, 1, 9, 0, 0)
        second_poll_time = datetime(2026, 1, 1, 9, 5, 0)

        with patch.object(self.collector._collector, "discover", return_value=[
            Device(id="id1", name="Test Headset", status="OK", address=address)
        ]), patch.object(
            self.collector._collector, "read_battery_levels",
            return_value=[BatteryReading(device_id=address, battery_percent=42, timestamp=first_poll_time)],
        ):
            self.collector._poll_pnp_battery()

        last_seen_after_first = self._device_last_seen(address)
        self.assertEqual(last_seen_after_first, first_poll_time.isoformat(timespec="microseconds"))

        with patch.object(self.collector._collector, "discover", return_value=[
            Device(id="id1", name="Test Headset", status="OK", address=address)
        ]), patch.object(
            self.collector._collector, "read_battery_levels",
            return_value=[BatteryReading(device_id=address, battery_percent=42, timestamp=second_poll_time)],
        ):
            self.collector._poll_pnp_battery()

        # Still the first poll's timestamp: a PnP-only reading must
        # never advance last_seen, no matter how many times it polls.
        self.assertEqual(self._device_last_seen(address), last_seen_after_first)

    def test_ble_presence_still_advances_last_seen_for_a_pnp_known_device(self) -> None:
        # last_seen is the "ble" channel's job - confirm it still works
        # normally for a device PnP already created a row for.
        address = "AA:BB:CC:DD:EE:FF"
        with patch.object(self.collector._collector, "discover", return_value=[]),                 patch.object(
                    self.collector._collector, "read_battery_levels",
                    return_value=[BatteryReading(device_id=address, battery_percent=42, timestamp=datetime(2026, 1, 1, 9, 0, 0))],
                ):
            self.collector._poll_pnp_battery()

        event = {
            "Event": "ConnectionStatusChanged",
            "BluetoothAddress": address,
            "Status": "Connected",
            "Timestamp": "2026-01-01T12:00:00",
        }
        self.collector.process_json_line(json_line(event))

        self.assertEqual(
            self._device_last_seen(address),
            datetime(2026, 1, 1, 12, 0, 0).isoformat(timespec="microseconds"),
        )

    def test_unchanged_pnp_value_is_not_rewritten(self) -> None:
        address = "AA:BB:CC:DD:EE:FF"
        for minute in (0, 5, 10):
            with patch.object(self.collector._collector, "discover", return_value=[]),                     patch.object(
                        self.collector._collector, "read_battery_levels",
                        return_value=[
                            BatteryReading(
                                device_id=address,
                                battery_percent=42,
                                timestamp=datetime(2026, 1, 1, 9, minute, 0),
                            )
                        ],
                    ):
                self.collector._poll_pnp_battery()

        self.assertEqual(len(self._battery_rows(address)), 1)

    def test_changed_pnp_value_is_recorded_again(self) -> None:
        address = "AA:BB:CC:DD:EE:FF"
        for minute, percent in ((0, 42), (5, 42), (10, 38)):
            with patch.object(self.collector._collector, "discover", return_value=[]),                     patch.object(
                        self.collector._collector, "read_battery_levels",
                        return_value=[
                            BatteryReading(
                                device_id=address,
                                battery_percent=percent,
                                timestamp=datetime(2026, 1, 1, 9, minute, 0),
                            )
                        ],
                    ):
                self.collector._poll_pnp_battery()

        rows = self._battery_rows(address)
        self.assertEqual(len(rows), 2)
        self.assertEqual([percent for percent, _ in rows], [42, 38])

    def test_discover_and_read_battery_levels_run_concurrently(self) -> None:
        # Regression test for Test.txt feedback (2026-09-28): "slowness
        # updating battery status at launch" - discover() and
        # read_battery_levels() must run on separate threads, not one
        # after the other, so the first poll's latency is roughly
        # max(a, b) instead of a + b.
        import time

        def slow_discover():
            time.sleep(0.2)
            return []

        def slow_read_battery_levels():
            time.sleep(0.2)
            return []

        with patch.object(self.collector._collector, "discover", side_effect=slow_discover),                 patch.object(
                    self.collector._collector, "read_battery_levels",
                    side_effect=slow_read_battery_levels,
                ):
            start = time.monotonic()
            self.collector._poll_pnp_battery()
            elapsed = time.monotonic() - start

        # Serial would take >= 0.4s; concurrent should stay well under
        # that - 0.35s leaves comfortable margin for scheduling jitter.
        self.assertLess(elapsed, 0.35)

    def test_poll_returns_false_on_powershell_error(self) -> None:
        with patch.object(
            self.collector._collector, "discover", side_effect=RuntimeError("boom")
        ):
            self.assertFalse(self.collector._poll_pnp_battery())


def json_line(event: dict) -> str:
    return json.dumps(event)


if __name__ == "__main__":
    unittest.main()
