"""
Tests for btbatterylab.ui.dashboard_data - the nicegui-free helpers
behind the historical dashboard. See tests/test_collector_manager.py
and tests/test_history_reader.py for the same "no nicegui import"
testing pattern this mirrors.
"""

from __future__ import annotations

import unittest
from datetime import datetime

from btbatterylab.collector.unified_collector import DeviceState
from btbatterylab.ui.dashboard_data import (
    STATUS_OFFLINE,
    STATUS_ONLINE,
    STATUS_UNKNOWN,
    build_device_rows,
    chart_series,
    device_options,
    device_row,
    device_status,
)
from btbatterylab.ui.history_reader import BatteryPoint, DeviceSummary


def _summary(
    address: str = "AA:BB:CC:DD:EE:01",
    name: str | None = "Apple Mouse",
    last_seen: datetime = datetime(2026, 9, 19, 10, 0, 0),
    last_battery_percent: int | None = 80,
    last_battery_source: str | None = "ble",
    last_battery_timestamp: datetime | None = datetime(2026, 9, 19, 10, 0, 0),
) -> DeviceSummary:
    return DeviceSummary(
        address=address,
        name=name,
        last_seen=last_seen,
        last_battery_percent=last_battery_percent,
        last_battery_source=last_battery_source,
        last_battery_timestamp=last_battery_timestamp,
    )


class DeviceStatusTests(unittest.TestCase):
    def test_unknown_when_collector_not_running(self) -> None:
        live = {"AA:BB:CC:DD:EE:01": DeviceState(address="AA:BB:CC:DD:EE:01", online=True)}
        self.assertEqual(
            device_status("AA:BB:CC:DD:EE:01", live, collector_running=False),
            STATUS_UNKNOWN,
        )

    def test_unknown_when_device_never_observed_this_run(self) -> None:
        self.assertEqual(
            device_status("AA:BB:CC:DD:EE:01", {}, collector_running=True),
            STATUS_UNKNOWN,
        )

    def test_unknown_when_online_flag_not_yet_known(self) -> None:
        live = {"AA:BB:CC:DD:EE:01": DeviceState(address="AA:BB:CC:DD:EE:01", online=None)}
        self.assertEqual(
            device_status("AA:BB:CC:DD:EE:01", live, collector_running=True),
            STATUS_UNKNOWN,
        )

    def test_online_when_live_state_says_so(self) -> None:
        live = {"AA:BB:CC:DD:EE:01": DeviceState(address="AA:BB:CC:DD:EE:01", online=True)}
        self.assertEqual(
            device_status("AA:BB:CC:DD:EE:01", live, collector_running=True),
            STATUS_ONLINE,
        )

    def test_offline_when_live_state_says_so(self) -> None:
        live = {"AA:BB:CC:DD:EE:01": DeviceState(address="AA:BB:CC:DD:EE:01", online=False)}
        self.assertEqual(
            device_status("AA:BB:CC:DD:EE:01", live, collector_running=True),
            STATUS_OFFLINE,
        )


class DeviceRowTests(unittest.TestCase):
    def test_row_with_no_battery_reading_shows_a_placeholder(self) -> None:
        summary = _summary(last_battery_percent=None, last_battery_source=None)
        row = device_row(summary, {}, collector_running=False)
        self.assertEqual(row["battery"], "—")
        self.assertEqual(row["source"], "—")

    def test_row_formats_battery_percent_and_last_seen(self) -> None:
        summary = _summary()
        row = device_row(summary, {}, collector_running=False)
        self.assertEqual(row["battery"], "80%")
        self.assertEqual(row["last_seen"], "2026-09-19 10:00:00")
        self.assertEqual(row["source"], "ble")
        self.assertEqual(row["status"], STATUS_UNKNOWN)

    def test_row_prefers_live_name_over_history_name(self) -> None:
        summary = _summary(name="Old Name")
        live = {
            summary.address: DeviceState(address=summary.address, name="New Name", online=True)
        }
        row = device_row(summary, live, collector_running=True)
        self.assertEqual(row["name"], "New Name")
        self.assertEqual(row["status"], STATUS_ONLINE)

    def test_row_falls_back_to_history_name_when_live_state_has_none(self) -> None:
        summary = _summary(name="History Name")
        live = {summary.address: DeviceState(address=summary.address, online=True)}
        row = device_row(summary, live, collector_running=True)
        self.assertEqual(row["name"], "History Name")

    def test_row_falls_back_to_address_when_no_name_anywhere(self) -> None:
        summary = _summary(name=None)
        row = device_row(summary, {}, collector_running=False)
        self.assertEqual(row["name"], summary.address)


class BuildDeviceRowsTests(unittest.TestCase):
    def test_builds_one_row_per_summary_in_order(self) -> None:
        summaries = [
            _summary(address="AA:BB:CC:DD:EE:01", name="First"),
            _summary(address="AA:BB:CC:DD:EE:02", name="Second"),
        ]
        rows = build_device_rows(summaries, {}, collector_running=False)
        self.assertEqual([row["name"] for row in rows], ["First", "Second"])

    def test_empty_summaries_gives_empty_rows(self) -> None:
        self.assertEqual(build_device_rows([], {}, collector_running=True), [])


class DeviceOptionsTests(unittest.TestCase):
    def test_maps_address_to_name(self) -> None:
        summaries = [_summary(address="AA:BB:CC:DD:EE:01", name="Apple Mouse")]
        self.assertEqual(
            device_options(summaries), {"AA:BB:CC:DD:EE:01": "Apple Mouse"}
        )

    def test_falls_back_to_address_when_nameless(self) -> None:
        summaries = [_summary(address="AA:BB:CC:DD:EE:01", name=None)]
        self.assertEqual(
            device_options(summaries),
            {"AA:BB:CC:DD:EE:01": "AA:BB:CC:DD:EE:01"},
        )


class ChartSeriesTests(unittest.TestCase):
    def test_converts_points_to_iso_timestamp_value_pairs(self) -> None:
        points = [
            BatteryPoint(timestamp=datetime(2026, 9, 19, 9, 0, 0), battery_percent=90),
            BatteryPoint(timestamp=datetime(2026, 9, 19, 10, 0, 0), battery_percent=85),
        ]
        self.assertEqual(
            chart_series(points),
            [
                ["2026-09-19T09:00:00", 90],
                ["2026-09-19T10:00:00", 85],
            ],
        )

    def test_empty_points_gives_empty_series(self) -> None:
        self.assertEqual(chart_series([]), [])


if __name__ == "__main__":
    unittest.main()
