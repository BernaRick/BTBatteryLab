"""
Tests for btbatterylab.ui.dashboard_data - the nicegui-free helpers
behind the historical dashboard. See tests/test_collector_manager.py
and tests/test_history_reader.py for the same "no nicegui import"
testing pattern this mirrors.
"""

from __future__ import annotations

import unittest
from datetime import datetime

from btbatterylab.analytics.battery_analytics import BatterySession, DeviceReport
from btbatterylab.collector.unified_collector import DeviceState
from btbatterylab.ui.dashboard_data import (
    STATUS_OFFLINE,
    STATUS_ONLINE,
    STATUS_UNKNOWN,
    analysis_summary,
    battery_level_status,
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
        self.assertEqual(row["battery_color"], "positive")
        self.assertEqual(row["last_seen"], "2026-09-19 10:00:00")
        self.assertEqual(row["source"], "ble")
        self.assertEqual(row["status"], STATUS_UNKNOWN)
        self.assertEqual(row["status_color"], "grey")

    def test_row_prefers_live_name_over_history_name(self) -> None:
        summary = _summary(name="Old Name")
        live = {
            summary.address: DeviceState(address=summary.address, name="New Name", online=True)
        }
        row = device_row(summary, live, collector_running=True)
        self.assertEqual(row["name"], "New Name")
        self.assertEqual(row["status"], STATUS_ONLINE)
        self.assertEqual(row["status_color"], "positive")

    def test_row_falls_back_to_history_name_when_live_state_has_none(self) -> None:
        summary = _summary(name="History Name")
        live = {summary.address: DeviceState(address=summary.address, online=True)}
        row = device_row(summary, live, collector_running=True)
        self.assertEqual(row["name"], "History Name")

    def test_row_falls_back_to_address_when_no_name_anywhere(self) -> None:
        summary = _summary(name=None)
        row = device_row(summary, {}, collector_running=False)
        self.assertEqual(row["name"], summary.address)


class BatteryLevelStatusTests(unittest.TestCase):
    def test_no_reading_is_unknown(self) -> None:
        self.assertEqual(battery_level_status(None), "unknown")

    def test_below_20_is_critical(self) -> None:
        self.assertEqual(battery_level_status(19), "critical")
        self.assertEqual(battery_level_status(0), "critical")

    def test_20_to_49_is_warning(self) -> None:
        self.assertEqual(battery_level_status(20), "warning")
        self.assertEqual(battery_level_status(49), "warning")

    def test_50_and_above_is_good(self) -> None:
        self.assertEqual(battery_level_status(50), "good")
        self.assertEqual(battery_level_status(100), "good")


class DeviceRowBatteryColorTests(unittest.TestCase):
    def test_critical_battery_maps_to_negative(self) -> None:
        row = device_row(_summary(last_battery_percent=5), {}, collector_running=False)
        self.assertEqual(row["battery_color"], "negative")

    def test_warning_battery_maps_to_warning(self) -> None:
        row = device_row(_summary(last_battery_percent=30), {}, collector_running=False)
        self.assertEqual(row["battery_color"], "warning")

    def test_no_battery_reading_maps_to_grey(self) -> None:
        row = device_row(
            _summary(last_battery_percent=None), {}, collector_running=False
        )
        self.assertEqual(row["battery_color"], "grey")

    def test_offline_status_maps_to_grey(self) -> None:
        summary = _summary()
        live = {summary.address: DeviceState(address=summary.address, online=False)}
        row = device_row(summary, live, collector_running=True)
        self.assertEqual(row["status"], STATUS_OFFLINE)
        self.assertEqual(row["status_color"], "grey")


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


def _report(
    *,
    drain_rate_percent_per_hour=None,
    estimated_runtime_hours=None,
    avg_percent=None,
    min_percent=None,
    max_percent=None,
    reading_count=0,
    discharge_session_count=0,
    charge_sessions=None,
) -> DeviceReport:
    return DeviceReport(
        address="AA:BB:CC:DD:EE:01",
        name="Apple Mouse",
        window_days=7,
        reading_count=reading_count,
        min_percent=min_percent,
        max_percent=max_percent,
        avg_percent=avg_percent,
        last_percent=None,
        last_timestamp=None,
        last_source=None,
        drain_rate_percent_per_hour=drain_rate_percent_per_hour,
        discharge_session_count=discharge_session_count,
        estimated_runtime_hours=estimated_runtime_hours,
        charge_sessions=charge_sessions or [],
    )


class AnalysisSummaryTests(unittest.TestCase):
    def test_no_drain_rate_says_not_enough_data(self) -> None:
        summary = analysis_summary(_report(drain_rate_percent_per_hour=None))
        self.assertEqual(summary["drain_rate"], "Not enough data")

    def test_drain_rate_is_formatted_to_one_decimal(self) -> None:
        summary = analysis_summary(_report(drain_rate_percent_per_hour=3.456))
        self.assertEqual(summary["drain_rate"], "3.5%/h")

    def test_no_estimated_runtime_says_unknown(self) -> None:
        summary = analysis_summary(_report(estimated_runtime_hours=None))
        self.assertEqual(summary["estimated_runtime"], "Unknown")

    def test_estimated_runtime_uses_format_hours(self) -> None:
        summary = analysis_summary(_report(estimated_runtime_hours=13.4))
        self.assertEqual(summary["estimated_runtime"], "13h 24m")

    def test_no_average_battery_shows_a_placeholder(self) -> None:
        summary = analysis_summary(_report(avg_percent=None))
        self.assertEqual(summary["average_battery"], "\u2014")

    def test_average_battery_is_rounded(self) -> None:
        summary = analysis_summary(_report(avg_percent=72.6))
        self.assertEqual(summary["average_battery"], "73%")

    def test_no_min_or_max_shows_a_placeholder_range(self) -> None:
        summary = analysis_summary(_report(min_percent=None, max_percent=None))
        self.assertEqual(summary["battery_range"], "\u2014")

    def test_min_and_max_form_a_range(self) -> None:
        summary = analysis_summary(_report(min_percent=40, max_percent=90))
        self.assertEqual(summary["battery_range"], "40%\u201390%")

    def test_session_counts_pass_through(self) -> None:
        charge_sessions = [
            BatterySession(
                direction="charge",
                start_time=datetime(2026, 9, 19, 8, 0, 0),
                start_percent=10,
                end_time=datetime(2026, 9, 19, 9, 0, 0),
                end_percent=100,
            )
        ]
        summary = analysis_summary(
            _report(discharge_session_count=3, charge_sessions=charge_sessions)
        )
        self.assertEqual(summary["discharge_session_count"], 3)
        self.assertEqual(summary["charge_session_count"], 1)

    def test_reading_count_passes_through(self) -> None:
        summary = analysis_summary(_report(reading_count=42))
        self.assertEqual(summary["reading_count"], 42)


if __name__ == "__main__":
    unittest.main()
