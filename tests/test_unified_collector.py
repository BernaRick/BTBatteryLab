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

from btbatterylab.collector.unified_collector import (
    DeviceState,
    UnifiedCollector,
    _is_generic_name,
)


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


def json_line(event: dict) -> str:
    return json.dumps(event)


if __name__ == "__main__":
    unittest.main()
