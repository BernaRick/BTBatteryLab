import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from btbatterylab.storage.sqlite_storage import SqliteStorage


class SqliteStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="btb_storage_"))
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.db_path = self.tmp_dir / "sub" / "btbatterylab.db"
        self.storage = SqliteStorage(self.db_path)
        self.addCleanup(self.storage.close)

    def test_creates_parent_directory_and_schema(self) -> None:
        self.assertTrue(self.db_path.parent.is_dir())

        raw = sqlite3.connect(self.db_path)
        tables = {
            row[0]
            for row in raw.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        raw.close()
        self.assertIn("devices", tables)
        self.assertIn("battery_log", tables)

    def test_record_device_seen_creates_device(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, 0)
        self.storage.record_device_seen("AA:BB:CC:DD:EE:FF", "Test Mouse", now)

        row = self.storage._connection.execute(
            "SELECT name, first_seen, last_seen FROM devices WHERE address = ?",
            ("AA:BB:CC:DD:EE:FF",),
        ).fetchone()
        self.assertIsNotNone(row)
        name, first_seen, last_seen = row
        self.assertEqual(name, "Test Mouse")
        self.assertEqual(first_seen, last_seen)

    def test_record_device_seen_moves_last_seen_forward_not_backward(self) -> None:
        base = datetime(2026, 1, 1, 12, 0, 0)
        self.storage.record_device_seen("AA:BB:CC:DD:EE:FF", "Test Mouse", base)

        # An earlier timestamp arriving late (e.g. an out-of-order
        # event) must not move last_seen backward.
        self.storage.record_device_seen(
            "AA:BB:CC:DD:EE:FF", "Test Mouse", base - timedelta(hours=1)
        )
        _, first_seen, last_seen = self.storage._connection.execute(
            "SELECT name, first_seen, last_seen FROM devices WHERE address = ?",
            ("AA:BB:CC:DD:EE:FF",),
        ).fetchone()
        self.assertEqual(last_seen, base.isoformat(timespec="microseconds"))
        self.assertEqual(first_seen, base.isoformat(timespec="microseconds"))

        # A later timestamp does move it forward.
        later = base + timedelta(hours=2)
        self.storage.record_device_seen("AA:BB:CC:DD:EE:FF", "Test Mouse", later)
        _, _, last_seen = self.storage._connection.execute(
            "SELECT name, first_seen, last_seen FROM devices WHERE address = ?",
            ("AA:BB:CC:DD:EE:FF",),
        ).fetchone()
        self.assertEqual(last_seen, later.isoformat(timespec="microseconds"))

    def test_record_device_seen_keeps_existing_name_when_new_name_is_none(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, 0)
        self.storage.record_device_seen("AA:BB:CC:DD:EE:FF", "Test Mouse", now)
        self.storage.record_device_seen("AA:BB:CC:DD:EE:FF", None, now + timedelta(minutes=1))

        name, = self.storage._connection.execute(
            "SELECT name FROM devices WHERE address = ?", ("AA:BB:CC:DD:EE:FF",)
        ).fetchone()
        self.assertEqual(name, "Test Mouse")

    def test_record_battery_inserts_reading(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, 0)
        self.storage.record_device_seen("AA:BB:CC:DD:EE:FF", "Test Mouse", now)
        self.storage.record_battery("AA:BB:CC:DD:EE:FF", 77, now, source="ble")

        row = self.storage._connection.execute(
            "SELECT battery_percent, source FROM battery_log WHERE address = ?",
            ("AA:BB:CC:DD:EE:FF",),
        ).fetchone()
        self.assertEqual(row, (77, "ble"))

    def test_record_battery_exact_duplicate_is_ignored(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, 0)
        self.storage.record_device_seen("AA:BB:CC:DD:EE:FF", "Test Mouse", now)
        self.storage.record_battery("AA:BB:CC:DD:EE:FF", 77, now, source="pnp")
        self.storage.record_battery("AA:BB:CC:DD:EE:FF", 77, now, source="pnp")

        count, = self.storage._connection.execute(
            "SELECT COUNT(*) FROM battery_log WHERE address = ?",
            ("AA:BB:CC:DD:EE:FF",),
        ).fetchone()
        self.assertEqual(count, 1)

    def test_record_battery_same_reading_different_source_is_kept(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, 0)
        self.storage.record_device_seen("AA:BB:CC:DD:EE:FF", "Test Mouse", now)
        self.storage.record_battery("AA:BB:CC:DD:EE:FF", 77, now, source="ble")
        self.storage.record_battery("AA:BB:CC:DD:EE:FF", 77, now, source="pnp")

        count, = self.storage._connection.execute(
            "SELECT COUNT(*) FROM battery_log WHERE address = ?",
            ("AA:BB:CC:DD:EE:FF",),
        ).fetchone()
        self.assertEqual(count, 2)

    def test_record_device_seen_error_is_caught_not_raised(self) -> None:
        self.storage._connection = MagicMock()
        self.storage._connection.execute.side_effect = sqlite3.Error("boom")

        try:
            self.storage.record_device_seen("AA:BB:CC:DD:EE:FF", "Test Mouse", datetime.now())
        except sqlite3.Error:
            self.fail("record_device_seen must not let a sqlite3.Error escape")

    def test_record_battery_error_is_caught_not_raised(self) -> None:
        self.storage._connection = MagicMock()
        self.storage._connection.execute.side_effect = sqlite3.Error("boom")

        try:
            self.storage.record_battery("AA:BB:CC:DD:EE:FF", 50, datetime.now(), source="ble")
        except sqlite3.Error:
            self.fail("record_battery must not let a sqlite3.Error escape")


if __name__ == "__main__":
    unittest.main()
