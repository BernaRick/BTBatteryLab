import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from btbatterylab.export.csv_export import CSV_HEADER, export_battery_log


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

    now = datetime.now()

    connection.execute(
        "INSERT INTO devices VALUES (?, ?, ?, ?)",
        ("AA:BB:CC:DD:EE:01", "OPPO Enco Air2", now.isoformat(), now.isoformat()),
    )
    connection.execute(
        "INSERT INTO devices VALUES (?, ?, ?, ?)",
        ("AA:BB:CC:DD:EE:02", "MX Master 2S", now.isoformat(), now.isoformat()),
    )

    for i in range(5):
        connection.execute(
            "INSERT INTO battery_log (address, timestamp, battery_percent, source) "
            "VALUES (?, ?, ?, ?)",
            (
                "AA:BB:CC:DD:EE:01",
                (now - timedelta(hours=i)).isoformat(timespec="microseconds"),
                90 - i,
                "pnp",
            ),
        )

    for i in range(3):
        connection.execute(
            "INSERT INTO battery_log (address, timestamp, battery_percent, source) "
            "VALUES (?, ?, ?, ?)",
            (
                "AA:BB:CC:DD:EE:02",
                (now - timedelta(hours=i)).isoformat(timespec="microseconds"),
                70 - i,
                "ble",
            ),
        )

    return connection


class ExportBatteryLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="btb_export_test_"))
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.connection = _make_db()
        self.addCleanup(self.connection.close)

    def test_full_window_exports_every_row(self) -> None:
        out_path = self.tmp_dir / "out.csv"
        count = export_battery_log(self.connection, out_path, window_days=30)

        self.assertEqual(count, 8)
        lines = out_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(lines[0], ",".join(CSV_HEADER))
        self.assertEqual(len(lines) - 1, 8)

    def test_zero_day_window_yields_empty_but_valid_csv(self) -> None:
        out_path = self.tmp_dir / "out.csv"
        count = export_battery_log(self.connection, out_path, window_days=0)

        self.assertEqual(count, 0)
        self.assertTrue(out_path.exists())
        content = out_path.read_text(encoding="utf-8").strip()
        self.assertEqual(content, ",".join(CSV_HEADER))

    def test_device_filter_by_name_substring(self) -> None:
        out_path = self.tmp_dir / "out.csv"
        count = export_battery_log(
            self.connection, out_path, window_days=30, device_filter="oppo"
        )

        self.assertEqual(count, 5)
        lines = out_path.read_text(encoding="utf-8").strip().splitlines()[1:]
        self.assertTrue(all(line.startswith("AA:BB:CC:DD:EE:01,") for line in lines))

    def test_device_filter_by_address_substring_matches_name_filter(self) -> None:
        out_path_name = self.tmp_dir / "by_name.csv"
        out_path_addr = self.tmp_dir / "by_addr.csv"

        count_name = export_battery_log(
            self.connection, out_path_name, window_days=30, device_filter="Master"
        )
        count_addr = export_battery_log(
            self.connection, out_path_addr, window_days=30, device_filter="EE:02"
        )

        self.assertEqual(count_name, count_addr)
        self.assertEqual(count_name, 3)

    def test_non_matching_filter_yields_zero_rows_without_raising(self) -> None:
        out_path = self.tmp_dir / "out.csv"
        count = export_battery_log(
            self.connection, out_path, window_days=30, device_filter="nonexistent-xyz"
        )
        self.assertEqual(count, 0)
        self.assertTrue(out_path.exists())

    def test_creates_destination_directory_if_missing(self) -> None:
        out_path = self.tmp_dir / "nested" / "dir" / "out.csv"
        export_battery_log(self.connection, out_path, window_days=30)
        self.assertTrue(out_path.exists())

    def test_rows_are_ordered_by_address_then_timestamp(self) -> None:
        out_path = self.tmp_dir / "out.csv"
        export_battery_log(self.connection, out_path, window_days=30)

        lines = out_path.read_text(encoding="utf-8").strip().splitlines()[1:]
        addresses = [line.split(",")[0] for line in lines]
        self.assertEqual(addresses, sorted(addresses))


if __name__ == "__main__":
    unittest.main()
