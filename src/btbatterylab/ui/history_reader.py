"""
Read-only queries over the battery_log/devices tables for the NiceGUI
historical dashboard (see docs/roadmap.md, v0.2).

Deliberately plain functions taking an already-open sqlite3.Connection,
the same pattern already used by btbatterylab.export.csv_export and
btbatterylab.analytics.battery_analytics, rather than a class owning
the connection - keeps this module trivially testable (see
tests/test_history_reader.py) and easy to reuse from a script later if
needed. The caller (btbatterylab.ui.app) is what opens a short-lived
connection per dashboard refresh - simple, and safe to do concurrently
with UnifiedCollector's own writer connection, since SqliteStorage
already turns on WAL mode (which supports one writer plus any number
of readers on the same database file).

This module has no idea whether a device is currently online - that
live state only exists in UnifiedCollector's in-memory DeviceState
while it's running (see btbatterylab.ui.collector_manager), never
persisted to SQLite. The UI layer is what combines this module's
last-known-from-history view with the live snapshot, when there is
one.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_WINDOW_DAYS = 7


@dataclass
class DeviceSummary:
    address: str
    name: str | None
    last_seen: datetime
    last_battery_percent: int | None
    last_battery_source: str | None
    last_battery_timestamp: datetime | None


@dataclass
class BatteryPoint:
    timestamp: datetime
    battery_percent: int


def _matches(name_filter: str, address: str, name: str | None) -> bool:
    """
    Same case-insensitive substring match on name or address already
    used by btbatterylab.export.csv_export's device_filter.
    """

    needle = name_filter.lower()
    return needle in address.lower() or bool(name and needle in name.lower())


def list_devices(
    connection: sqlite3.Connection, name_filter: str | None = None
) -> list[DeviceSummary]:
    """
    Every known device (ever seen, not just currently online), each
    with its last known battery reading if it has one - ordered by
    name (falling back to address for devices with no name yet), so
    the dashboard's device list has a stable, predictable order.
    """

    rows = connection.execute(
        """
        SELECT
            devices.address,
            devices.name,
            devices.last_seen,
            latest.battery_percent,
            latest.source,
            latest.timestamp
        FROM devices
        LEFT JOIN battery_log AS latest
            ON latest.address = devices.address
            AND latest.timestamp = (
                SELECT MAX(timestamp) FROM battery_log
                WHERE battery_log.address = devices.address
            )
        ORDER BY COALESCE(devices.name, devices.address) COLLATE NOCASE
        """
    ).fetchall()

    summaries = [
        DeviceSummary(
            address=address,
            name=name,
            last_seen=datetime.fromisoformat(last_seen),
            last_battery_percent=battery_percent,
            last_battery_source=source,
            last_battery_timestamp=(
                datetime.fromisoformat(timestamp) if timestamp else None
            ),
        )
        for address, name, last_seen, battery_percent, source, timestamp in rows
    ]

    if name_filter:
        summaries = [
            summary
            for summary in summaries
            if _matches(name_filter, summary.address, summary.name)
        ]

    return summaries


def battery_history(
    connection: sqlite3.Connection,
    address: str,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> list[BatteryPoint]:
    """
    Every battery_log reading for one device within the last
    window_days days, oldest first - the raw series a chart plots
    directly, with no smoothing or session grouping (that's what
    btbatterylab.analytics.battery_analytics is for).
    """

    since = (datetime.now() - timedelta(days=window_days)).isoformat(
        timespec="microseconds"
    )

    rows = connection.execute(
        """
        SELECT timestamp, battery_percent
        FROM battery_log
        WHERE address = ? AND timestamp >= ?
        ORDER BY timestamp
        """,
        (address, since),
    ).fetchall()

    return [
        BatteryPoint(
            timestamp=datetime.fromisoformat(timestamp),
            battery_percent=battery_percent,
        )
        for timestamp, battery_percent in rows
    ]


def connect_readonly(db_path: str | Path) -> sqlite3.Connection | None:
    """
    Opens the database for the dashboard to read, or returns None if
    it doesn't exist yet (a fresh install, or the collector has never
    been started) - not an error, just "nothing to show yet".
    """

    db_path = Path(db_path)

    if not db_path.exists():
        return None

    return sqlite3.connect(str(db_path))
