import sqlite3
import threading
from datetime import datetime
from pathlib import Path


class SqliteStorage:
    """
    Local SQLite persistence for the device and battery history.

    Two tables, as described in docs/architecture.md:

    - devices: one row per device (key = Bluetooth address), with the
      best known name and the first/last time we learned anything
      about it (presence or battery).
    - battery_log: one row per battery reading observed from either
      channel (ble/pnp) - raw history, not filtered by the
      "freshest wins" rule used for the live view in UnifiedCollector,
      so there's enough data in the future for drain rate, runtime
      estimation, and degradation trends.

    A single, shared connection, with an internal lock: UnifiedCollector
    writes from two different threads (JSONL tail on the main thread,
    PnP polling on a background thread).

    SQLite errors are caught and printed instead of crashing the
    collector: persistence is a useful side-effect but must never
    interrupt live monitoring.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            self.db_path, check_same_thread=False
        )
        self._connection.execute("PRAGMA journal_mode=WAL;")
        self._connection.execute("PRAGMA foreign_keys=ON;")

        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    address TEXT PRIMARY KEY,
                    name TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                )
                """
            )

            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS battery_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    address TEXT NOT NULL REFERENCES devices(address),
                    timestamp TEXT NOT NULL,
                    battery_percent INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    UNIQUE(address, timestamp, source)
                )
                """
            )

            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_battery_log_address_ts
                ON battery_log(address, timestamp)
                """
            )

    @staticmethod
    def _format_timestamp(timestamp: datetime) -> str:
        return timestamp.isoformat(timespec="microseconds")

    def record_device_seen(
        self,
        address: str,
        name: str | None,
        timestamp: datetime,
    ) -> None:
        """
        Creates the device if it doesn't exist (first_seen = last_seen
        = timestamp), otherwise updates the name (if known) and moves
        last_seen forward - never backward, in case events arrive out
        of order.
        """

        ts = self._format_timestamp(timestamp)

        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO devices (address, name, first_seen, last_seen)
                    VALUES (:address, :name, :ts, :ts)
                    ON CONFLICT(address) DO UPDATE SET
                        name = COALESCE(excluded.name, devices.name),
                        last_seen = MAX(devices.last_seen, excluded.last_seen)
                    """,
                    {"address": address, "name": name, "ts": ts},
                )
        except sqlite3.Error as ex:
            print(f"[SqliteStorage] Error in record_device_seen: {ex}")

    def record_battery(
        self,
        address: str,
        battery_percent: int,
        timestamp: datetime,
        source: str,
    ) -> None:
        """
        Records a raw battery reading. Exact duplicates (same device,
        same timestamp, same source - typical of a PnP poll that finds
        the same BatteryUpdated as before because the device hasn't
        refreshed its estimate) are silently discarded by the UNIQUE
        constraint.
        """

        ts = self._format_timestamp(timestamp)

        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO battery_log
                        (address, timestamp, battery_percent, source)
                    VALUES (?, ?, ?, ?)
                    """,
                    (address, ts, battery_percent, source),
                )
        except sqlite3.Error as ex:
            print(f"[SqliteStorage] Error in record_battery: {ex}")

    def close(self) -> None:
        with self._lock:
            self._connection.close()
