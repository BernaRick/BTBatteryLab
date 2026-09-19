"""
Nicegui-free helpers for the historical dashboard (see
btbatterylab.ui.app), split out of app.py for the same reason
btbatterylab.ui.collector_manager has no nicegui import: it keeps this
logic unit-testable (see tests/test_dashboard_data.py) without a
running NiceGUI server or the nicegui package installed at all - app.py
itself is intentionally left untested, the same "UI layer isn't
automated" gap already documented for BluetoothWatcher's C# side and
for collector_manager's own NiceGUI wiring.

This module has two jobs: turning a btbatterylab.ui.history_reader
DeviceSummary (last-known-from-history) plus an optional live
UnifiedCollector.DeviceState (only available while the collector is
running) into one table row for the device overview, and turning a
list of BatteryPoint readings into the (x, y) series a chart plots.
"""

from __future__ import annotations

from btbatterylab.collector.unified_collector import DeviceState
from btbatterylab.ui.history_reader import BatteryPoint, DeviceSummary

# Label shown in the dashboard's time-window selector, mapped to the
# window_days argument btbatterylab.ui.history_reader.battery_history()
# expects. Dict order is display order.
WINDOW_OPTIONS: dict[str, int] = {
    "Last 24 hours": 1,
    "Last 7 days": 7,
    "Last 30 days": 30,
    "Last 90 days": 90,
}

DEFAULT_WINDOW_LABEL = "Last 7 days"

STATUS_ONLINE = "Online"
STATUS_OFFLINE = "Offline"
STATUS_UNKNOWN = "Unknown"


def device_status(
    address: str,
    live_snapshot: dict[str, DeviceState],
    collector_running: bool,
) -> str:
    """
    Online/offline is live-only state (see history_reader's module
    docstring) - it only means anything while the collector is
    actually running, and even then only once that device has been
    observed at least once this run.
    """

    if not collector_running:
        return STATUS_UNKNOWN

    live_state = live_snapshot.get(address)
    if live_state is None or live_state.online is None:
        return STATUS_UNKNOWN

    return STATUS_ONLINE if live_state.online else STATUS_OFFLINE


def device_row(
    summary: DeviceSummary,
    live_snapshot: dict[str, DeviceState],
    collector_running: bool,
) -> dict:
    """
    One btbatterylab.ui.app device-table row, as plain field->value
    pairs matching the column definitions there (name, address,
    battery, source, last_seen, status - all display strings, so the
    table needs no per-cell formatting logic of its own).
    """

    live_state = live_snapshot.get(summary.address)
    # A device can be renamed between runs (Windows reports whatever
    # name it currently has); the live name, when there is one, is
    # more current than history's.
    name = (live_state.name if live_state else None) or summary.name or summary.address

    if summary.last_battery_percent is None:
        battery = "—"  # em dash: never seen a battery reading
    else:
        battery = f"{summary.last_battery_percent}%"

    return {
        "address": summary.address,
        "name": name,
        "battery": battery,
        "source": summary.last_battery_source or "—",
        "last_seen": summary.last_seen.strftime("%Y-%m-%d %H:%M:%S"),
        "status": device_status(summary.address, live_snapshot, collector_running),
    }


def build_device_rows(
    summaries: list[DeviceSummary],
    live_snapshot: dict[str, DeviceState],
    collector_running: bool,
) -> list[dict]:
    return [
        device_row(summary, live_snapshot, collector_running)
        for summary in summaries
    ]


def device_options(summaries: list[DeviceSummary]) -> dict[str, str]:
    """
    address -> display label, in the same order as summaries (already
    sorted by history_reader.list_devices()), for the dashboard's
    device-picker ui.select - NiceGUI's ui.select takes exactly this
    {value: label} shape as its options.
    """

    return {
        summary.address: (summary.name or summary.address) for summary in summaries
    }


def chart_series(points: list[BatteryPoint]) -> list[list]:
    """
    [[timestamp_iso, battery_percent], ...] - the shape ECharts wants
    for a line series on a "time" x-axis (see btbatterylab.ui.app's
    ui.echart options), oldest first since that's how
    history_reader.battery_history() already returns them.
    """

    return [[point.timestamp.isoformat(), point.battery_percent] for point in points]
