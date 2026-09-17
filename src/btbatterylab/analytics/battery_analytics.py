"""
Analytics over the raw battery_log/devices history stored by
SqliteStorage.

Both collection channels ("ble" and "pnp", see UnifiedCollector) write
every observed battery reading to battery_log, not just the one that
"wins" for the live view - that raw history is what this module mines
for:

- drain rate: how fast a device's battery drops, in percent per hour,
  based on the discharge runs found in the window.
- estimated remaining runtime: a projection of how long the device's
  last known battery percentage would last at its recent average
  drain rate.
- charge sessions: periods where the battery percentage goes up
  instead of down, i.e. the device was charging.
- per-device summary: min/max/average percent, reading count, and
  last known status, over the window.

This module only reads finished history from SQLite - it has no idea
whether a device is online or charging right now (that live state
lives in UnifiedCollector's in-memory DeviceState, not persisted
separately), so "estimated runtime" is a plain projection from past
behavior, not a live countdown.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

DEFAULT_WINDOW_DAYS = 30


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass
class BatterySession:
    """
    A run of consecutive battery_log readings for one device that all
    move in the same direction (all decreasing = discharge, all
    increasing = charge). A flat reading (same percent as the previous
    one) doesn't start a new session - it just extends the current
    one's end time, since it isn't evidence of the device changing
    direction.
    """

    direction: str  # "discharge" or "charge"
    start_time: datetime
    start_percent: int
    end_time: datetime
    end_percent: int

    @property
    def duration_hours(self) -> float:
        return (self.end_time - self.start_time).total_seconds() / 3600.0

    @property
    def delta_percent(self) -> int:
        return self.end_percent - self.start_percent

    @property
    def rate_percent_per_hour(self) -> float | None:
        if self.duration_hours <= 0:
            return None
        return abs(self.delta_percent) / self.duration_hours


@dataclass
class DeviceReport:
    address: str
    name: str | None
    window_days: int
    reading_count: int
    min_percent: int | None
    max_percent: int | None
    avg_percent: float | None
    last_percent: int | None
    last_timestamp: datetime | None
    last_source: str | None
    drain_rate_percent_per_hour: float | None
    discharge_session_count: int
    estimated_runtime_hours: float | None
    charge_sessions: list[BatterySession]


def _fetch_devices(
    connection: sqlite3.Connection, device_filter: str | None
) -> list[tuple[str, str | None]]:
    """
    Returns (address, name) pairs, optionally filtered to devices
    whose address or name contains device_filter (case-insensitive
    substring match) - convenient for "just this one device" without
    having to know its exact MAC address.
    """

    rows = connection.execute(
        "SELECT address, name FROM devices ORDER BY name, address"
    ).fetchall()

    if not device_filter:
        return rows

    needle = device_filter.lower()
    return [
        (address, name)
        for address, name in rows
        if needle in address.lower() or (name and needle in name.lower())
    ]


def _fetch_readings(
    connection: sqlite3.Connection, address: str, since: datetime
) -> list[tuple[datetime, int, str]]:
    rows = connection.execute(
        """
        SELECT timestamp, battery_percent, source
        FROM battery_log
        WHERE address = ? AND timestamp >= ?
        ORDER BY timestamp ASC
        """,
        (address, since.isoformat(timespec="microseconds")),
    ).fetchall()

    return [
        (_parse_timestamp(ts), percent, source) for ts, percent, source in rows
    ]


def _build_sessions(
    readings: list[tuple[datetime, int, str]]
) -> list[BatterySession]:
    sessions: list[BatterySession] = []
    current: BatterySession | None = None

    for i in range(1, len(readings)):
        prev_time, prev_percent, _ = readings[i - 1]
        time, percent, _ = readings[i]

        if percent < prev_percent:
            direction = "discharge"
        elif percent > prev_percent:
            direction = "charge"
        else:
            # Flat reading: extends the current session (if any)
            # without starting a new one - not evidence of a change
            # of direction.
            if current is not None:
                current.end_time = time
            continue

        if current is not None and current.direction == direction:
            current.end_time = time
            current.end_percent = percent
        else:
            if current is not None:
                sessions.append(current)
            current = BatterySession(
                direction=direction,
                start_time=prev_time,
                start_percent=prev_percent,
                end_time=time,
                end_percent=percent,
            )

    if current is not None:
        sessions.append(current)

    return sessions


def _weighted_drain_rate(sessions: list[BatterySession]) -> float | None:
    """
    Percent per hour, weighted by session duration rather than a plain
    average of per-session rates, so one very short (and noisy) run
    doesn't skew the result as much as a long, representative one.
    """

    discharge_sessions = [s for s in sessions if s.direction == "discharge"]

    total_hours = sum(s.duration_hours for s in discharge_sessions)
    total_percent = sum(abs(s.delta_percent) for s in discharge_sessions)

    if total_hours <= 0:
        return None

    return total_percent / total_hours


def build_device_report(
    connection: sqlite3.Connection,
    address: str,
    name: str | None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> DeviceReport:
    since = datetime.now() - timedelta(days=window_days)
    readings = _fetch_readings(connection, address, since)

    percents = [p for _, p, _ in readings]
    sessions = _build_sessions(readings)
    discharge_sessions = [s for s in sessions if s.direction == "discharge"]
    charge_sessions = [s for s in sessions if s.direction == "charge"]

    drain_rate = _weighted_drain_rate(sessions)

    last_percent = percents[-1] if percents else None
    last_time = readings[-1][0] if readings else None
    last_source = readings[-1][2] if readings else None

    estimated_runtime_hours = None
    if drain_rate and drain_rate > 0 and last_percent is not None:
        estimated_runtime_hours = last_percent / drain_rate

    return DeviceReport(
        address=address,
        name=name,
        window_days=window_days,
        reading_count=len(readings),
        min_percent=min(percents) if percents else None,
        max_percent=max(percents) if percents else None,
        avg_percent=(sum(percents) / len(percents)) if percents else None,
        last_percent=last_percent,
        last_timestamp=last_time,
        last_source=last_source,
        drain_rate_percent_per_hour=drain_rate,
        discharge_session_count=len(discharge_sessions),
        estimated_runtime_hours=estimated_runtime_hours,
        charge_sessions=charge_sessions,
    )


def build_all_reports(
    connection: sqlite3.Connection,
    window_days: int = DEFAULT_WINDOW_DAYS,
    device_filter: str | None = None,
) -> list[DeviceReport]:
    devices = _fetch_devices(connection, device_filter)

    return [
        build_device_report(connection, address, name, window_days)
        for address, name in devices
    ]


def format_hours(hours: float) -> str:
    """Compact human-readable duration, e.g. "13h 24m" or "2d 3h"."""

    total_minutes = round(hours * 60)
    days, remainder_minutes = divmod(total_minutes, 24 * 60)
    hrs, minutes = divmod(remainder_minutes, 60)

    if days > 0:
        return f"{days}d {hrs}h"
    if hrs > 0:
        return f"{hrs}h {minutes}m"
    return f"{minutes}m"
