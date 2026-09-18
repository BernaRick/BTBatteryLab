"""
CSV export of the raw battery_log history.

Exports every battery reading recorded in battery_log - not the
"freshest wins" live view used by UnifiedCollector, but the full raw
history recorded by SqliteStorage.record_battery for every reading
observed on either channel ("ble" or "pnp") - for a given time window,
optionally restricted to devices whose name or address contains a
given text (same matching used by btbatterylab.analytics).

Kept separate from btbatterylab.analytics.battery_analytics on
purpose: this module deals in raw rows for spreadsheet/reporting use,
not the derived sessions/drain-rate/runtime metrics.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_WINDOW_DAYS = 30

CSV_HEADER = ["address", "device_name", "timestamp", "battery_percent", "source"]


def _matching_addresses(
    connection: sqlite3.Connection, device_filter: str | None
) -> set[str] | None:
    """
    Returns the set of device addresses matching device_filter (by
    address or name, case-insensitive substring), or None if
    device_filter is falsy - meaning "no filtering, every device".
    """

    if not device_filter:
        return None

    needle = device_filter.lower()

    rows = connection.execute("SELECT address, name FROM devices").fetchall()

    return {
        address
        for address, name in rows
        if needle in address.lower() or (name and needle in name.lower())
    }


def export_battery_log(
    connection: sqlite3.Connection,
    csv_path: str | Path,
    window_days: int = DEFAULT_WINDOW_DAYS,
    device_filter: str | None = None,
) -> int:
    """
    Writes every battery_log row within the last window_days days
    (optionally restricted to devices matching device_filter) to
    csv_path, one row per reading, oldest first. Returns the number of
    rows written (can be 0 - the file is still created, with just the
    header, so a scripted caller always gets a valid CSV to read).
    """

    since = datetime.now() - timedelta(days=window_days)
    since_str = since.isoformat(timespec="microseconds")

    matching = _matching_addresses(connection, device_filter)

    rows = connection.execute(
        """
        SELECT battery_log.address, devices.name, battery_log.timestamp,
               battery_log.battery_percent, battery_log.source
        FROM battery_log
        JOIN devices ON devices.address = battery_log.address
        WHERE battery_log.timestamp >= ?
        ORDER BY battery_log.address, battery_log.timestamp
        """,
        (since_str,),
    ).fetchall()

    if matching is not None:
        rows = [row for row in rows if row[0] in matching]

    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open(mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)

    return len(rows)
