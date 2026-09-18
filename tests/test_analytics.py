"""
Tests for btbatterylab.analytics.battery_analytics.

Two of these are explicit regression tests for real bugs found against
real device data (see docs/roadmap.md, Step 3.1): a noisy ~2-minute
glitch inflating the drain rate to 300+%/h, and a ~50-minute session
long enough to survive the duration filter alone but still physically
implausible (48.5%/h). Both fixes are constants
(MIN_SESSION_DURATION_HOURS, MAX_PLAUSIBLE_DISCHARGE_RATE_PERCENT_PER_HOUR)
that a future change could easily weaken without realizing it - these
tests exist to catch that.
"""

import sqlite3
import unittest
from datetime import datetime, timedelta

from btbatterylab.analytics.battery_analytics import (
    build_all_reports,
    build_device_report,
    format_hours,
)

ADDRESS = "AA:BB:CC:DD:EE:01"
NAME = "Test Device"


def _make_db() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE devices (address TEXT PRIMARY KEY, name TEXT, "
        "first_seen TEXT NOT NULL, last_seen TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE battery_log (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "address TEXT NOT NULL, timestamp TEXT NOT NULL, "
        "battery_percent INTEGER NOT NULL, source TEXT NOT NULL, "
        "UNIQUE(address, timestamp, source))"
    )
    return connection


def _insert_device(connection: sqlite3.Connection, address: str, name: str, seen: datetime) -> None:
    ts = seen.isoformat(timespec="microseconds")
    connection.execute(
        "INSERT INTO devices VALUES (?, ?, ?, ?)", (address, name, ts, ts)
    )


def _insert_readings(
    connection: sqlite3.Connection,
    address: str,
    readings: list[tuple[datetime, int]],
    source: str = "pnp",
) -> None:
    for timestamp, percent in readings:
        connection.execute(
            "INSERT INTO battery_log (address, timestamp, battery_percent, source) "
            "VALUES (?, ?, ?, ?)",
            (address, timestamp.isoformat(timespec="microseconds"), percent, source),
        )


class NoDataTests(unittest.TestCase):
    def test_no_readings_reports_no_data(self) -> None:
        connection = _make_db()
        now = datetime.now()
        _insert_device(connection, ADDRESS, NAME, now)

        report = build_device_report(connection, ADDRESS, NAME, window_days=30)

        self.assertEqual(report.reading_count, 0)
        self.assertIsNone(report.drain_rate_percent_per_hour)
        self.assertIsNone(report.estimated_runtime_hours)
        self.assertEqual(report.charge_sessions, [])
        self.assertIsNone(report.min_percent)
        self.assertIsNone(report.last_percent)


class DrainRateAndRuntimeTests(unittest.TestCase):
    def test_clean_discharge_produces_expected_drain_rate_and_runtime(self) -> None:
        connection = _make_db()
        now = datetime.now()
        _insert_device(connection, ADDRESS, NAME, now)

        # A clean 24h discharge from 100% to 40%, one reading/hour:
        # 60 percentage points over 24 hours = 2.5%/h.
        readings = [
            (now - timedelta(hours=24 - i), 100 - i * (60 / 24))
            for i in range(25)
        ]
        readings = [(t, round(p)) for t, p in readings]
        _insert_readings(connection, ADDRESS, readings)

        report = build_device_report(connection, ADDRESS, NAME, window_days=30)

        self.assertIsNotNone(report.drain_rate_percent_per_hour)
        self.assertAlmostEqual(report.drain_rate_percent_per_hour, 2.5, delta=0.2)
        self.assertEqual(report.discharge_session_count, 1)
        self.assertIsNotNone(report.estimated_runtime_hours)
        # last_percent / drain_rate
        self.assertAlmostEqual(
            report.estimated_runtime_hours,
            report.last_percent / report.drain_rate_percent_per_hour,
        )

    def test_charge_session_is_detected_separately_from_discharge(self) -> None:
        connection = _make_db()
        now = datetime.now()
        _insert_device(connection, ADDRESS, NAME, now)

        readings = [
            (now - timedelta(hours=5), 40),
            (now - timedelta(hours=4), 30),  # discharge
            (now - timedelta(hours=3), 60),  # charge
            (now - timedelta(hours=2), 90),  # charge (continues)
            (now - timedelta(hours=1), 90),  # flat: extends, no new session
        ]
        _insert_readings(connection, ADDRESS, readings)

        report = build_device_report(connection, ADDRESS, NAME, window_days=30)

        self.assertEqual(len(report.charge_sessions), 1)
        charge = report.charge_sessions[0]
        self.assertEqual(charge.start_percent, 30)
        self.assertEqual(charge.end_percent, 90)
        # The flat reading at the end extended the session's end_time
        # without starting a new one.
        self.assertEqual(charge.end_time, now - timedelta(hours=1))


class ReliabilityFilterRegressionTests(unittest.TestCase):
    """
    Locks in the two real-data fixes from Step 3.1 of the roadmap.
    """

    def test_short_glitch_session_is_dropped(self) -> None:
        # Two readings ~2 minutes apart implying ~300%/h - shorter
        # than MIN_SESSION_DURATION_HOURS (10 minutes), must not
        # affect the drain rate or show up as a session at all.
        connection = _make_db()
        now = datetime.now()
        _insert_device(connection, ADDRESS, NAME, now)

        readings = [
            (now - timedelta(minutes=2), 90),
            (now, 80),
        ]
        _insert_readings(connection, ADDRESS, readings)

        report = build_device_report(connection, ADDRESS, NAME, window_days=30)

        self.assertIsNone(report.drain_rate_percent_per_hour)
        self.assertEqual(report.discharge_session_count, 0)

    def test_long_but_implausibly_fast_discharge_is_dropped(self) -> None:
        # ~50 minutes (passes the duration filter on its own) but a
        # drop from 90% to 50% implies ~48%/h, above
        # MAX_PLAUSIBLE_DISCHARGE_RATE_PERCENT_PER_HOUR (40%/h) - this
        # is the MX Master 2S regression case from the roadmap.
        connection = _make_db()
        now = datetime.now()
        _insert_device(connection, ADDRESS, NAME, now)

        readings = [
            (now - timedelta(minutes=50), 90),
            (now, 50),
        ]
        _insert_readings(connection, ADDRESS, readings)

        report = build_device_report(connection, ADDRESS, NAME, window_days=30)

        self.assertIsNone(report.drain_rate_percent_per_hour)
        self.assertEqual(report.discharge_session_count, 0)

    def test_implausible_filter_does_not_apply_to_charge_sessions(self) -> None:
        # A quick-charging earbud case going from 0% to 100% in 20
        # minutes (300%/h) must still be reported - the discharge-only
        # plausibility cap must not reject fast charge sessions.
        connection = _make_db()
        now = datetime.now()
        _insert_device(connection, ADDRESS, NAME, now)

        readings = [
            (now - timedelta(minutes=20), 0),
            (now, 100),
        ]
        _insert_readings(connection, ADDRESS, readings)

        report = build_device_report(connection, ADDRESS, NAME, window_days=30)

        self.assertEqual(len(report.charge_sessions), 1)
        self.assertEqual(report.charge_sessions[0].delta_percent, 100)

    def test_long_enough_and_plausible_discharge_survives(self) -> None:
        # Sanity check that the filters aren't so strict they drop a
        # perfectly normal session: 3 hours, 15 points -> 5%/h, well
        # under the 40%/h cap and well over the 10-minute floor.
        connection = _make_db()
        now = datetime.now()
        _insert_device(connection, ADDRESS, NAME, now)

        readings = [
            (now - timedelta(hours=3), 100),
            (now, 85),
        ]
        _insert_readings(connection, ADDRESS, readings)

        report = build_device_report(connection, ADDRESS, NAME, window_days=30)

        self.assertIsNotNone(report.drain_rate_percent_per_hour)
        self.assertAlmostEqual(report.drain_rate_percent_per_hour, 5.0, delta=0.1)
        self.assertEqual(report.discharge_session_count, 1)


class DeviceFilterTests(unittest.TestCase):
    def test_build_all_reports_filters_by_name_and_address_substring(self) -> None:
        connection = _make_db()
        now = datetime.now()
        _insert_device(connection, "AA:BB:CC:DD:EE:01", "OPPO Enco Air2", now)
        _insert_device(connection, "AA:BB:CC:DD:EE:02", "MX Master 2S", now)

        by_name = build_all_reports(connection, device_filter="oppo")
        self.assertEqual([r.address for r in by_name], ["AA:BB:CC:DD:EE:01"])

        by_address = build_all_reports(connection, device_filter="EE:02")
        self.assertEqual([r.address for r in by_address], ["AA:BB:CC:DD:EE:02"])

        no_filter = build_all_reports(connection)
        self.assertEqual(len(no_filter), 2)

        no_match = build_all_reports(connection, device_filter="nonexistent")
        self.assertEqual(no_match, [])


class FormatHoursTests(unittest.TestCase):
    def test_minutes_only(self) -> None:
        self.assertEqual(format_hours(0.5), "30m")

    def test_hours_and_minutes(self) -> None:
        self.assertEqual(format_hours(13.4), "13h 24m")

    def test_days_and_hours(self) -> None:
        self.assertEqual(format_hours(51), "2d 3h")

    def test_zero(self) -> None:
        self.assertEqual(format_hours(0), "0m")


if __name__ == "__main__":
    unittest.main()
