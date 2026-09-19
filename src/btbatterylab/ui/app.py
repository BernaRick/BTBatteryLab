"""
The NiceGUI application - v0.2's UI, replacing both the console-only
collector and the originally-planned Streamlit dashboard (see
docs/roadmap.md, "UI Technology Decision: NiceGUI").

Three parts on one page, top to bottom: a header (title, a manual
Refresh button, an Exit button that stops everything - see below),
the live control panel (Start/Stop, status), and the historical
dashboard - a device overview table, a filter, a device/time-window
picker, a battery-history chart, and an Analysis card (drain rate,
estimated remaining runtime, battery range, session counts) for
whichever device/window is picked. Built on top of
btbatterylab.ui.history_reader (read-only SQLite queries),
btbatterylab.analytics.battery_analytics (the same drain-rate/runtime/
session-detection logic the `analytics` CLI already uses), and
btbatterylab.ui.dashboard_data (nicegui-free formatting - see that
module's docstring for why the split, and tests/test_dashboard_data.py
for its tests - this module itself stays untested, the same "UI layer
isn't automated" gap already documented for BluetoothWatcher's C#
side).

Styling follows the project's own data-viz guidance: status
information (battery level, online/offline) uses Quasar's reserved
"positive"/"warning"/"negative"/"grey" roles consistently, always as a
labeled badge rather than color alone; the battery-history chart uses
one sequential hue for the line plus shaded bands at the same 20%/50%
thresholds the table's badges use, so a "low battery" period is
visible on the chart, not just in the table.

Single-process design (decided 2026-09-19): main.py calls run_app()
below instead of constructing/starting UnifiedCollector directly.
Starting the app starts the collector automatically, matching today's
behavior (double-click and it's already monitoring) - Stop is there
for pausing without closing the window, not for opting out of
monitoring by default. Exit (added 2026-09-19, alongside run.bat/
BluetoothWatcher now starting without visible windows - see
docs/roadmap.md) is for closing the whole app: with no console window
to Ctrl+C anymore, this is the only way to stop the Python side short
of Task Manager.
"""

from __future__ import annotations

import inspect
from datetime import datetime
from typing import Callable

from nicegui import app, ui

from btbatterylab.analytics.battery_analytics import build_device_report
from btbatterylab.collector.unified_collector import UnifiedCollector
from btbatterylab.config import Config
from btbatterylab.ui.collector_manager import (
    STATUS_ERROR,
    STATUS_RUNNING,
    CollectorManager,
)
from btbatterylab.ui.dashboard_data import (
    BATTERY_GOOD_THRESHOLD,
    BATTERY_WARNING_THRESHOLD,
    DEFAULT_WINDOW_LABEL,
    WINDOW_OPTIONS,
    analysis_summary,
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

# Sequential blue (mid step) for the battery-history line, plus the
# same warning/critical hues used for the table's status badges, so a
# low-battery stretch stands out on the chart the same way it does in
# the table - see btbatterylab.ui.dashboard_data's BATTERY_*_THRESHOLD/
# BATTERY_STATUS_COLOR for the shared thresholds these bands match.
_CHART_LINE_COLOR = "#256abf"
_CHART_WARNING_BAND_COLOR = "#fab219"
_CHART_CRITICAL_BAND_COLOR = "#d03b3b"

# Refresh cadence for the historical dashboard: it re-reads SQLite, so
# it's deliberately slower than the live control panel's 1s status
# poll (that one only reads in-memory state). A manual Refresh button
# next to it covers "I just want to see it right now".
_DASHBOARD_REFRESH_SECONDS = 5.0


def _stat_tile(title: str) -> ui.label:
    """
    One "big number, small caption" tile for the Analysis card -
    returns the value label so the caller can update it later. Plain
    ink colors throughout (no status coloring): these are magnitudes
    from btbatterylab.analytics, not a good/bad state, so tinting them
    red/green would claim a judgment the numbers themselves don't make.
    """

    with ui.column().classes("items-start gap-0 min-w-44"):
        ui.label(title).classes("text-xs text-grey uppercase tracking-wide")
        value_label = ui.label("—").classes("text-2xl font-bold")
    return value_label


def _build_header(
    manager: CollectorManager, on_refresh_click: Callable[[], None]
) -> ui.label:
    with ui.row().classes("w-full items-center justify-between"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("bluetooth").classes("text-3xl text-primary")
            ui.label("BTBatteryLab").classes("text-2xl font-bold")

        with ui.row().classes("items-center gap-2"):
            last_updated_label = ui.label("").classes("text-xs text-grey")

            with ui.dialog() as exit_dialog, ui.card():
                ui.label("Exit BTBatteryLab?").classes("text-lg font-semibold")
                ui.label(
                    "This stops the collector and closes this app "
                    "completely - not just the dashboard tab."
                ).classes("text-sm text-grey")
                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Cancel", on_click=exit_dialog.close).props("flat")

                    async def _exit_app() -> None:
                        manager.stop()
                        # app.shutdown() has been sync in some
                        # NiceGUI versions and a coroutine in
                        # others - this awaits it only if it
                        # actually returned something awaitable,
                        # so this keeps working either way without
                        # pinning to one exact NiceGUI release.
                        result = app.shutdown()
                        if inspect.isawaitable(result):
                            await result

                    ui.button("Exit", color="negative", on_click=_exit_app)

            ui.button(on_click=lambda: on_refresh_click()).props(
                "flat round icon=refresh"
            ).tooltip("Refresh now")
            ui.button(on_click=exit_dialog.open).props(
                "flat round icon=power_settings_new color=negative"
            ).tooltip("Exit BTBatteryLab")

    return last_updated_label


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


def _build_dashboard(
    manager: CollectorManager, config: Config, on_refresh: Callable[[], None]
) -> Callable[[], None]:
    with ui.card().classes("w-full"):
        ui.label("Devices").classes("text-lg font-semibold")

        # debounce=300: re-querying SQLite on every keystroke would be
        # wasteful (and, on a slow disk, briefly janky) - this waits
        # for a short pause in typing instead, same idea as a
        # search-as-you-type field anywhere else.
        filter_input = (
            ui.input("Filter by name or address")
            .classes("w-full")
            .props("debounce=300 clearable")
        )
        device_table = ui.table(
            columns=_DEVICE_COLUMNS, rows=[], row_key="address"
        ).classes("w-full")
        device_table.add_slot(
            "body-cell-battery",
            r"""
            <q-td :props="props">
                <q-badge
                    :color="props.row.battery_color"
                    :text-color="props.row.battery_color === 'warning' ? 'black' : 'white'"
                >{{ props.value }}</q-badge>
            </q-td>
            """,
        )
        device_table.add_slot(
            "body-cell-status",
            r"""
            <q-td :props="props">
                <q-badge
                    :color="props.row.status_color"
                    :text-color="props.row.status_color === 'warning' ? 'black' : 'white'"
                >{{ props.value }}</q-badge>
            </q-td>
            """,
        )
        empty_label = ui.label(
            "No devices seen yet - once the collector spots one, it "
            "shows up here."
        ).classes("text-sm text-grey")

    with ui.card().classes("w-full"):
        ui.label("Battery history").classes("text-lg font-semibold")

        with ui.row().classes("items-center gap-4"):
            device_select = ui.select(options={}, label="Device").classes("min-w-64")
            window_select = ui.select(
                options=list(WINDOW_OPTIONS.keys()),
                value=DEFAULT_WINDOW_LABEL,
                label="Window",
            ).classes("min-w-40")

        chart = ui.echart(
            {
                "grid": {"left": 45, "right": 20, "top": 20, "bottom": 30},
                "xAxis": {"type": "time"},
                "yAxis": {
                    "type": "value",
                    "min": 0,
                    "max": 100,
                    "name": "%",
                    "axisLabel": {"formatter": "{value}%"},
                },
                "tooltip": {"trigger": "axis"},
                "series": [
                    {
                        "type": "line",
                        "name": "Battery",
                        "showSymbol": False,
                        "lineStyle": {"width": 2, "color": _CHART_LINE_COLOR},
                        "itemStyle": {"color": _CHART_LINE_COLOR},
                        "areaStyle": {"opacity": 0.08, "color": _CHART_LINE_COLOR},
                        "data": [],
                        # Shades the same warning/critical battery bands
                        # the device table's badges use (see
                        # dashboard_data.BATTERY_*_THRESHOLD), so a low
                        # stretch is visible on the chart too, not just
                        # in the table.
                        "markArea": {
                            "silent": True,
                            "itemStyle": {"opacity": 0.12},
                            "data": [
                                [
                                    {
                                        "yAxis": 0,
                                        "itemStyle": {"color": _CHART_CRITICAL_BAND_COLOR},
                                    },
                                    {"yAxis": BATTERY_WARNING_THRESHOLD},
                                ],
                                [
                                    {
                                        "yAxis": BATTERY_WARNING_THRESHOLD,
                                        "itemStyle": {"color": _CHART_WARNING_BAND_COLOR},
                                    },
                                    {"yAxis": BATTERY_GOOD_THRESHOLD},
                                ],
                            ],
                        },
                    }
                ],
            }
        ).classes("w-full h-64")
        chart_empty_label = ui.label(
            "Pick a device above to see its battery history."
        ).classes("text-sm text-grey")

    with ui.card().classes("w-full"):
        ui.label("Analysis").classes("text-lg font-semibold")
        ui.label(
            "Same device and time window as above."
        ).classes("text-xs text-grey mb-2")

        with ui.row().classes("w-full flex-wrap gap-6"):
            drain_rate_label = _stat_tile("Drain rate")
            runtime_label = _stat_tile("Estimated runtime left")
            range_label = _stat_tile("Battery range (avg)")
            sessions_label = _stat_tile("Charge / discharge sessions")

        analysis_empty_label = ui.label(
            "Pick a device above to see its analysis."
        ).classes("text-sm text-grey")

    def refresh_devices() -> None:
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
        # and analysis card can't refresh - drop it instead of
        # showing a picker with nothing behind it.
        if device_select.value not in options:
            device_select.value = None

    def refresh_selected() -> None:
        address = device_select.value

        if not address:
            chart.options["series"][0]["data"] = []
            chart.update()
            chart_empty_label.set_visibility(True)
            analysis_empty_label.set_visibility(True)
            for label in (drain_rate_label, runtime_label, range_label, sessions_label):
                label.text = "—"
            return

        connection = connect_readonly(config.db_path)
        if connection is None:
            return

        try:
            window_days = WINDOW_OPTIONS.get(
                window_select.value, WINDOW_OPTIONS[DEFAULT_WINDOW_LABEL]
            )
            points = battery_history(connection, address, window_days=window_days)
            report = build_device_report(
                connection, address, name=None, window_days=window_days
            )
        finally:
            connection.close()

        chart.options["series"][0]["data"] = chart_series(points)
        chart.update()
        chart_empty_label.set_visibility(not points)

        summary = analysis_summary(report)
        analysis_empty_label.set_visibility(False)
        drain_rate_label.text = summary["drain_rate"]
        runtime_label.text = summary["estimated_runtime"]
        range_label.text = f"{summary['battery_range']} (avg {summary['average_battery']})"
        sessions_label.text = (
            f"{summary['charge_session_count']} / {summary['discharge_session_count']}"
        )

    def refresh_all() -> None:
        refresh_devices()
        refresh_selected()
        on_refresh()

    filter_input.on_value_change(lambda _: refresh_all())
    device_select.on_value_change(lambda _: refresh_all())
    window_select.on_value_change(lambda _: refresh_all())

    ui.timer(_DASHBOARD_REFRESH_SECONDS, refresh_all)
    refresh_all()

    return refresh_all


def _build_page(manager: CollectorManager, config: Config) -> None:
    with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4"):
        # The header's Refresh button needs to trigger the dashboard's
        # refresh_all(), but the dashboard (and that function) doesn't
        # exist until _build_dashboard() runs, further down the page -
        # this holder lets the button close over a name that's filled
        # in a few lines later, instead of the two functions needing
        # to know about each other's internals.
        refresh_holder: dict[str, Callable[[], None]] = {"refresh": lambda: None}
        last_updated_label = _build_header(
            manager, on_refresh_click=lambda: refresh_holder["refresh"]()
        )
        _build_control_panel(manager)

        def update_last_updated() -> None:
            last_updated_label.text = f"Updated {datetime.now().strftime('%H:%M:%S')}"

        refresh_holder["refresh"] = _build_dashboard(
            manager, config, on_refresh=update_last_updated
        )


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
