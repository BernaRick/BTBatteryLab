"""
The NiceGUI application - v0.2's UI, replacing both the console-only
collector and the originally-planned Streamlit dashboard (see
docs/roadmap.md, "UI Technology Decision: NiceGUI").

Two halves on one page: the live control panel (Start/Stop, status)
built first as a minimal skeleton to get the single-process
architecture right, and the historical dashboard added here - a
device overview table, a filter, a device/time-window picker, and a
battery-history line chart - built on top of btbatterylab.ui.history_reader
(the read-only SQLite queries) and btbatterylab.ui.dashboard_data (the
nicegui-free formatting helpers; see that module's docstring for why
the split, and tests/test_dashboard_data.py for its tests - this
module itself stays untested, the same "UI layer isn't automated" gap
already documented for BluetoothWatcher's C# side).

Single-process design (decided 2026-09-19): main.py calls run_app()
below instead of constructing/starting UnifiedCollector directly.
Starting the app starts the collector automatically, matching today's
behavior (double-click and it's already monitoring) - Stop is there
for pausing without closing the window, not for opting out of
monitoring by default.
"""

from __future__ import annotations

from nicegui import ui

from btbatterylab.collector.unified_collector import UnifiedCollector
from btbatterylab.config import Config
from btbatterylab.ui.collector_manager import (
    STATUS_ERROR,
    STATUS_RUNNING,
    CollectorManager,
)
from btbatterylab.ui.dashboard_data import (
    DEFAULT_WINDOW_LABEL,
    WINDOW_OPTIONS,
    build_device_rows,
    chart_series,
    device_options,
)
from btbatterylab.ui.history_reader import battery_history, connect_readonly, list_devices

_STATUS_COLORS = {
    STATUS_RUNNING: "positive",
    STATUS_ERROR: "negative",
}

_DEVICE_COLUMNS = [
    {"name": "name", "label": "Device", "field": "name", "align": "left", "sortable": True},
    {"name": "address", "label": "Address", "field": "address", "align": "left"},
    {"name": "battery", "label": "Battery", "field": "battery", "align": "right", "sortable": True},
    {"name": "source", "label": "Source", "field": "source", "align": "left"},
    {"name": "status", "label": "Status", "field": "status", "align": "left", "sortable": True},
    {"name": "last_seen", "label": "Last seen", "field": "last_seen", "align": "left", "sortable": True},
]

# Refresh cadence for the historical dashboard: it re-reads SQLite, so
# it's deliberately slower than the live control panel's 1s status
# poll (that one only reads in-memory state).
_DASHBOARD_REFRESH_SECONDS = 5.0


def _build_control_panel(manager: CollectorManager) -> None:
    with ui.card().classes("w-full"):
        ui.label("Collector").classes("text-lg font-semibold")

        status_badge = ui.badge("").props("rounded")
        error_label = ui.label("").classes("text-negative text-sm")

        with ui.row():
            start_button = ui.button("Start", on_click=lambda: manager.start())
            stop_button = ui.button("Stop", on_click=lambda: manager.stop())

        def refresh() -> None:
            status = manager.status
            status_badge.text = status
            status_badge.props(
                f"color={_STATUS_COLORS.get(status, 'grey')}"
            )
            start_button.set_enabled(status != STATUS_RUNNING)
            stop_button.set_enabled(status != "stopped")

            error = manager.error_message
            error_label.text = error or ""
            error_label.set_visibility(bool(error))

        ui.timer(1.0, refresh)
        refresh()


def _build_dashboard(manager: CollectorManager, config: Config) -> None:
    with ui.card().classes("w-full"):
        ui.label("Devices").classes("text-lg font-semibold")

        # debounce=300: re-querying SQLite on every keystroke would
        # be wasteful (and, on a slow disk, briefly janky) - this
        # waits for a short pause in typing instead, same idea as a
        # search-as-you-type field anywhere else.
        filter_input = ui.input("Filter by name or address").classes("w-full").props("debounce=300")
        device_table = ui.table(
            columns=_DEVICE_COLUMNS, rows=[], row_key="address"
        ).classes("w-full")
        empty_label = ui.label(
            "No devices seen yet - once the collector spots one, it "
            "shows up here."
        ).classes("text-sm text-grey")

    with ui.card().classes("w-full"):
        ui.label("Battery history").classes("text-lg font-semibold")

        with ui.row().classes("items-center"):
            device_select = ui.select(options={}, label="Device").classes("min-w-64")
            window_select = ui.select(
                options=list(WINDOW_OPTIONS.keys()),
                value=DEFAULT_WINDOW_LABEL,
                label="Window",
            ).classes("min-w-40")

        chart = ui.echart(
            {
                "xAxis": {"type": "time"},
                "yAxis": {"type": "value", "min": 0, "max": 100, "name": "%"},
                "series": [{"type": "line", "name": "Battery", "data": []}],
                "tooltip": {"trigger": "axis"},
            }
        ).classes("w-full h-64")
        chart_empty_label = ui.label(
            "Pick a device above to see its battery history."
        ).classes("text-sm text-grey")

    def refresh_table() -> None:
        connection = connect_readonly(config.db_path)
        if connection is None:
            device_table.rows = []
            device_table.set_visibility(False)
            empty_label.set_visibility(True)
            device_select.set_options({})
            return

        try:
            summaries = list_devices(connection, name_filter=filter_input.value or None)
        finally:
            connection.close()

        live_snapshot = manager.snapshot()
        collector_running = manager.status == STATUS_RUNNING

        rows = build_device_rows(summaries, live_snapshot, collector_running)
        device_table.rows = rows
        device_table.set_visibility(bool(rows))
        empty_label.set_visibility(not rows)

        options = device_options(summaries)
        device_select.set_options(options)
        # An address the filter has just hidden, or that no longer
        # exists, would otherwise leave a stale selection the chart
        # can't refresh - drop it instead of showing a picker with
        # nothing behind it.
        if device_select.value not in options:
            device_select.value = None

    def refresh_chart() -> None:
        address = device_select.value
        if not address:
            chart.options["series"][0]["data"] = []
            chart.update()
            chart_empty_label.set_visibility(True)
            return

        connection = connect_readonly(config.db_path)
        if connection is None:
            return

        try:
            window_days = WINDOW_OPTIONS.get(window_select.value, WINDOW_OPTIONS[DEFAULT_WINDOW_LABEL])
            points = battery_history(connection, address, window_days=window_days)
        finally:
            connection.close()

        chart.options["series"][0]["data"] = chart_series(points)
        chart.update()
        chart_empty_label.set_visibility(not points)

    def refresh_all() -> None:
        refresh_table()
        refresh_chart()

    filter_input.on_value_change(lambda _: refresh_table())
    device_select.on_value_change(lambda _: refresh_chart())
    window_select.on_value_change(lambda _: refresh_chart())

    ui.timer(_DASHBOARD_REFRESH_SECONDS, refresh_all)
    refresh_all()


def _build_page(manager: CollectorManager, config: Config) -> None:
    ui.label("BTBatteryLab").classes("text-2xl font-bold")

    _build_control_panel(manager)
    _build_dashboard(manager, config)


def run_app(config: Config) -> None:
    """
    Builds the single page above and starts the NiceGUI web server -
    blocking, same as UnifiedCollector.start() was before this change.
    Opens the user's default browser automatically (show=True), so
    double-clicking the app still needs no extra step.
    """

    def _new_collector() -> UnifiedCollector:
        return UnifiedCollector(
            jsonl_path=config.jsonl_path,
            db_path=config.db_path,
            poll_interval_seconds=config.poll_interval_seconds,
            min_poll_spacing_seconds=config.min_poll_spacing_seconds,
            pnp_timeout_seconds=config.pnp_timeout_seconds,
        )

    manager = CollectorManager(collector_factory=_new_collector)

    @ui.page("/")
    def index() -> None:
        _build_page(manager, config)

    # Starts monitoring right away, same as running main.py used to -
    # the UI's Stop button is for pausing, not an opt-in step.
    manager.start()

    # reload=False: NiceGUI's auto-reload spawns a watcher subprocess
    # that re-imports this module, which doesn't play well with being
    # started from BluetoothWatcher.exe's background process (and
    # later, PyInstaller packaging - see docs/roadmap.md's still-open
    # question on how this fits build_exe.bat).
    ui.run(title="BTBatteryLab", reload=False, show=True)
