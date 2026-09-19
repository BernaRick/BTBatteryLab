"""
Tests for btbatterylab.ui.history_reader.

Uses a real temp-file SQLite database (not ":memory:") for
connect_readonly's own tests, since it specifically checks
Path.exists() - an in-memory database has no path to check. The query
functions themselves (list_devices/battery_history) are tested against
a plain in-memory connection instead, the same pattern already used by
tests/test_export.py, since they only need an already-open connection.
"""

import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from btbatterylab.ui.history_reader import (
    battery_history,
    connect_readonly,
    list_devices,
)


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


class ListDevicesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = _make_db()
        self.addCleanup(self.connection.close)

    def test_device_with_no_battery_readings_has_none_fields(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, 0)
        self.connection.execute(
            "INSERT INTO devices VALUES (?, ?, ?, ?)",
            ("AA:BB:CC:DD:EE:01", "Silent Mouse", now.isoformat(), now.isoformat()),
        )

        summaries = list_devices(self.connection)

        self.assertEqual(len(summaries), 1)
        summary = summaries[0]
        self.assertEqual(summary.name, "Silent Mouse")
        self.assertIsNone(summary.last_battery_percent)
        self.assertIsNone(summary.last_battery_source)
        self.assertIsNone(summary.last_battery_timestamp)

    def test_last_battery_reading_is_the_most_recent_one(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, 0)
        self.connection.execute(
            "INSERT INTO devices VALUES (?, ?, ?, ?)",
            ("AA:BB:CC:DD:EE:01", "Mouse", now.isoformat(), now.isoformat()),
        )
        for i, percent in enumerate([90, 85, 80]):
            ts = now + timedelta(hours=i)
            self.connection.execute(
                "INSERT INTO battery_log (address, timestamp, battery_percent, source) "
                "VALUES (?, ?, ?, ?)",
                ("AA:BB:CC:DD:EE:01", ts.isoformat(timespec="microseconds"), percent, "ble"),
            )

        summaries = list_devices(self.connection)

        self.assertEqual(summaries[0].last_battery_percent, 80)

    def test_devices_are_ordered_by_name_falling_back_to_address(self) -> None:
        # "Charlie Mouse" and "bravo Headset" deliberately mix case, to
        # confirm the ordering is case-insensitive (COLLATE NOCASE) -
        # without it, every uppercase letter would sort before every
        # lowercase one, putting "Charlie" before "bravo" regardless of
        # their actual alphabetical order.
        now = datetime(2026, 1, 1, 12, 0, 0)
        self.connection.execute(
            "INSERT INTO devices VALUES (?, ?, ?, ?)",
            ("AA:BB:CC:DD:EE:02", "Charlie Mouse", now.isoformat(), now.isoformat()),
        )
        self.connection.execute(
            "INSERT INTO devices VALUES (?, ?, ?, ?)",
            ("AA:BB:CC:DD:EE:01", "bravo Headset", now.isoformat(), now.isoformat()),
        )
        self.connection.execute(
            "INSERT INTO devices VALUES (?, ?, ?, ?)",
            ("AA:BB:CC:DD:EE:03", None, now.isoformat(), now.isoformat()),
        )

        summaries = list_devices(self.connection)

        # No-name device falls back to its address ("AA:BB:CC:DD:EE:03"),
        # which sorts before both names here alphabetically.
        self.assertEqual(
            [s.address for s in summaries],
            ["AA:BB:CC:DD:EE:03", "AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"],
        )

    def test_name_filter_matches_name_case_insensitively(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, 0)
        self.connection.execute(
            "INSERT INTO devices VALUES (?, ?, ?, ?)",
            ("AA:BB:CC:DD:EE:01", "OPPO Enco Air2", now.isoformat(), now.isoformat()),
        )
        self.connection.execute(
            "INSERT INTO devices VALUES (?, ?, ?, ?)",
            ("AA:BB:CC:DD:EE:02", "MX Master 2S", now.isoformat(), now.isoformat()),
        )

        summaries = list_devices(self.connection, name_filter="oppo")

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].address, "AA:BB:CC:DD:EE:01")

    def test_name_filter_matches_address_substring(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, 0)
        self.connection.execute(
            "INSERT INTO devices VALUES (?, ?, ?, ?)",
            ("AA:BB:CC:DD:EE:01", "Mouse", now.isoformat(), now.isoformat()),
        )
        self.connection.execute(
            "INSERT INTO devices VALUES (?, ?, ?, ?)",
            ("11:22:33:44:55:66", "Headset", now.isoformat(), now.isoformat()),
        )

        summaries = list_devices(self.connection, name_filter="EE:01")

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].name, "Mouse")

    def test_empty_database_returns_empty_list(self) -> None:
        self.assertEqual(list_devices(self.connection), [])


class BatteryHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = _make_db()
        self.addCleanup(self.connection.close)
        self.connection.execute(
            "INSERT INTO devices VALUES (?, ?, ?, ?)",
            (
                "AA:BB:CC:DD:EE:01",
                "Mouse",
                datetime(2026, 1, 1).isoformat(),
                datetime(2026, 1, 1).isoformat(),
            ),
        )

    def _insert_reading(self, address: str, when: datetime, percent: int) -> None:
        self.connection.execute(
            "INSERT INTO battery_log (address, timestamp, battery_percent, source) "
            "VALUES (?, ?, ?, ?)",
            (address, when.isoformat(timespec="microseconds"), percent, "ble"),
        )

    def test_returns_points_within_the_window_ordered_by_time(self) -> None:
        now = datetime.now()
        self._insert_reading("AA:BB:CC:DD:EE:01", now - timedelta(hours=2), 70)
        self._insert_reading("AA:BB:CC:DD:EE:01", now - timedelta(hours=1), 65)
        self._insert_reading("AA:BB:CC:DD:EE:01", now, 60)

        points = battery_history(self.connection, "AA:BB:CC:DD:EE:01", window_days=7)

        self.assertEqual([p.battery_percent for p in points], [70, 65, 60])

    def test_readings_outside_the_window_are_excluded(self) -> None:
        now = datetime.now()
        self._insert_reading("AA:BB:CC:DD:EE:01", now - timedelta(days=10), 99)
        self._insert_reading("AA:BB:CC:DD:EE:01", now, 50)

        points = battery_history(self.connection, "AA:BB:CC:DD:EE:01", window_days=7)

        self.assertEqual([p.battery_percent for p in points], [50])

    def test_other_devices_readings_are_excluded(self) -> None:
        now = datetime.now()
        self._insert_reading("AA:BB:CC:DD:EE:01", now, 50)
        self._insert_reading("11:22:33:44:55:66", now, 99)

        points = battery_history(self.connection, "AA:BB:CC:DD:EE:01", window_days=7)

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].battery_percent, 50)

    def test_device_with_no_readings_returns_empty_list(self) -> None:
        self.assertEqual(
            battery_history(self.connection, "AA:BB:CC:DD:EE:01", window_days=7), []
        )


class ConnectReadonlyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="btb_history_reader_"))
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

    def test_missing_database_returns_none(self) -> None:
        missing_path = self.tmp_dir / "does-not-exist.db"
        self.assertIsNone(connect_readonly(missing_path))

    def test_existing_database_returns_a_working_connection(self) -> None:
        db_path = self.tmp_dir / "btbatterylab.db"
        setup_connection = sqlite3.connect(db_path)
        setup_connection.execute(
            "CREATE TABLE devices (address TEXT PRIMARY KEY, name TEXT, "
            "first_seen TEXT NOT NULL, last_seen TEXT NOT NULL)"
        )
        setup_connection.commit()
        setup_connection.close()

        connection = connect_readonly(db_path)

        try:
            self.assertIsNotNone(connection)
            rows = connection.execute("SELECT * FROM devices").fetchall()
            self.assertEqual(rows, [])
        finally:
            if connection is not None:
                connection.close()


if __name__ == "__main__":
    unittest.main()
