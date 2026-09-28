"""
The NiceGUI application - v0.2's UI, replacing both the console-only
collector and the originally-planned Streamlit dashboard (see
docs/roadmap.md, "UI Technology Decision: NiceGUI").

Two parts on one page, top to bottom: a header (title, collector
status/Start/Stop, a manual Refresh button, and an Exit button that
stops everything - see _exit_app), and the historical dashboard - a
device overview table (with a name/address filter and an online/
offline status filter), a device/time-window picker, a battery-history
chart, and an Analysis card (drain rate, estimated remaining runtime,
battery range, session counts) for whichever device/window is picked,
side by side for easier reading. Built on top of
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
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from nicegui import app, ui

logger = logging.getLogger(__name__)

# How long _exit_app() waits for NiceGUI's own app.shutdown() to end
# the process cleanly before forcing it with os._exit() - a safety
# net, not the normal path: Test.txt feedback (2026-09-28) reported
# Exit not actually closing the app. app.shutdown()'s behavior varies
# across NiceGUI versions/native-vs-browser modes (see the comment on
# result/inspect.isawaitable below), so rather than chase every
# version's exact behavior, this guarantees the process ends either
# way.
_HARD_EXIT_GRACE_SECONDS = 3.0

# How long _exit_app() waits for the goodbye-page JavaScript (below) to
# reach the browser before moving on to app.shutdown(). Test.txt
# feedback (2026-09-28, round 2) reported the Exit button still leaves
# the dashboard tab open - expected (browsers only let a script close a
# tab it opened itself, see _exit_app's docstring), but the tab was
# then left showing a dead/disconnected page once the server process
# ended, instead of something that tells the user it's done and safe to
# close by hand. This timeout bounds how long that one best-effort
# round-trip is allowed to take.
_EXIT_JS_TIMEOUT_SECONDS = 1.5

# Replaces the whole page with a plain "it's safe to close this tab"
# message - the fallback for when window.close() (tried first, also
# best-effort) does nothing. Deliberately plain inline HTML/CSS rather
# than another NiceGUI element: by the time this runs the app is
# already shutting down, so it can't depend on anything else in the
# page still working.
_EXIT_PAGE_JS = """
try { window.close(); } catch (e) {}
document.body.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:center;
                height:100vh;margin:0;font-family:sans-serif;
                background:#1a1a1a;color:#e0e0e0;text-align:center;">
      <div>
        <h2 style="margin-bottom:8px;">BTBatteryLab has closed</h2>
        <p style="color:#999;margin:0;">It's safe to close this tab now.</p>
      </div>
    </div>
`;
"""

# taskkill's own timeout is generous enough that this never needs a
# long wait - it either finds the process and kills it, or (already
# not running) returns almost immediately.
_TASKKILL_TIMEOUT_SECONDS = 10.0

# Same reasoning as bluetooth_collector._CREATE_NO_WINDOW: only
# meaningful on Windows, a harmless 0 (no-op) everywhere else,
# including in this module's own tests.
_CREATE_NO_WINDOW = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
)

# Optional replacement for the "BTBatteryLab" text in the header - drop
# a logo image at this path (any name, .png/.jpg/.svg all work with
# ui.image) and _build_header() picks it up automatically, no code
# change needed. Absent by default (nothing is committed here yet):
# Patrick offered to provide one (Test.txt, 2026-09-28: "aggiungere un
# logo, che ho io, al posto della scritta 'BTBatteryLab'") but hasn't
# sent the file yet, so this stays a graceful fallback to the icon +
# text label rather than a hard dependency.
_LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"


def _kill_bluetooth_watcher() -> None:
    """
    Same mechanism as stop.bat (see build_exe.bat/stop.bat):
    `taskkill /F /IM BluetoothWatcher.exe /T` - kills BluetoothWatcher
    and, since it can run the Python collector as its own background
    child process (see docs/roadmap.md), that whole process tree too.
    A no-op (logged, not raised) if it isn't running or this isn't
    Windows - Exit must still close the rest of the app either way.
    """

    if sys.platform != "win32":
        return

    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "BluetoothWatcher.exe", "/T"],
            capture_output=True,
            text=True,
            timeout=_TASKKILL_TIMEOUT_SECONDS,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception as ex:
        # Most likely: BluetoothWatcher.exe wasn't running at all
        # (taskkill's own "not found" case is a non-zero exit code,
        # not an exception, so this is for the rarer failure to even
        # launch taskkill) - never let this block the rest of Exit.
        logger.warning(f"Could not stop BluetoothWatcher.exe: {ex}")


async def _exit_app(manager: CollectorManager) -> None:
    """
    Exit is meant to be a single button that leaves nothing running -
    the collector, BluetoothWatcher.exe, and this app's own process
    (Test.txt feedback, 2026-09-28: it previously stopped only the
    collector). The browser tab itself is the one part genuinely out
    of this app's control: browsers only let a script close a tab it
    opened itself, so the best this can do is ask (window.close() is a
    no-op in most browsers for a tab the user opened by hand) - the
    dialog text sets that expectation instead of promising it.
    """

    manager.stop()
    _kill_bluetooth_watcher()

    # A hard failsafe: if app.shutdown() doesn't actually end the
    # process (see _HARD_EXIT_GRACE_SECONDS above), this guarantees it
    # does anyway. Started before the JS round-trip below so a stuck or
    # refused run_javascript() call can never prevent the process from
    # ending - it runs on its own daemon thread, independent of the
    # async path here.
    def _force_exit_if_still_running() -> None:
        os._exit(0)

    threading.Timer(_HARD_EXIT_GRACE_SECONDS, _force_exit_if_still_running).start()

    # Best-effort, and *awaited* (unlike a fire-and-forget call, which
    # never actually reaches the browser since nothing drives the
    # coroutine): tries window.close() first, then - since that's a
    # no-op in most browsers for a tab the user opened by hand, see the
    # docstring above - rewrites the page to a plain "safe to close"
    # message instead, so that's the last thing left on screen rather
    # than a dead connection once the server process below ends.
    try:
        await ui.run_javascript(_EXIT_PAGE_JS, timeout=_EXIT_JS_TIMEOUT_SECONDS)
    except Exception:
        pass

    # app.shutdown() has been sync in some NiceGUI versions and a
    # coroutine in others - this awaits it only if it actually
    # returned something awaitable, so this keeps working either way
    # without pinning to one exact NiceGUI release.
    result = app.shutdown()
    if inspect.isawaitable(result):
        await result

from btbatterylab.analytics.battery_analytics import build_device_report
from btbatterylab.collector.unified_collector import UnifiedCollector
from btbatterylab.config import Config
from btbatterylab.ui.collector_manager import (
    STATUS_ERROR,
    STATUS_RUNNING,
    STATUS_STOPPED,
    CollectorManager,
)
from btbatterylab.ui.dashboard_data import (
    BATTERY_GOOD_THRESHOLD,
    BATTERY_WARNING_THRESHOLD,
    DEFAULT_WINDOW_LABEL,
    STATUS_OFFLINE,
    STATUS_ONLINE,
    STATUS_UNKNOWN,
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

# "All" plus the three device_status() outcomes (see
# dashboard_data.py) - a user-selectable filter alongside the existing
# name/address text filter, per Test.txt feedback (2026-09-28).
_STATUS_FILTER_ALL = "All"
_STATUS_FILTER_OPTIONS = [
    _STATUS_FILTER_ALL,
    STATUS_ONLINE,
    STATUS_OFFLINE,
    STATUS_UNKNOWN,
]

_DEVICE_COLUMNS = [
    {"name": "name", "label": "Device", "field": "name", "align": "left", "sortable": True},
    {"name": "address", "label": "Address", "field": "address", "align": "left"},
    {"name": "battery", "label": "Battery", "field": "battery", "align": "right", "sortable": True},
    {"name": "status", "label": "Status", "field": "status", "align": "left", "sortable": True},
    {"name": "last_seen", "label": "Last seen", "field": "last_seen", "align": "left", "sortable": True},
    # Last column, per Test.txt feedback (2026-09-28) - the least
    # frequently-needed field at a glance.
    {"name": "source", "label": "Source", "field": "source", "align": "left"},
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
    """
    Title, collector status/controls, last-updated time, and the
    Refresh/Exit actions, all in one compact row - restyled
    2026-09-28 (Test.txt feedback: "review the top-right buttons, more
    minimal and visually uniform") to a single row of small flat/dense
    icon controls plus one small colored status dot, instead of mixing
    a solid colored status badge and a separator line in with them.
    """

    with ui.row().classes("w-full items-center justify-between"):
        with ui.row().classes("items-center gap-2"):
            if _LOGO_PATH.exists():
                ui.image(str(_LOGO_PATH)).classes("h-8 w-auto")
            else:
                ui.icon("bluetooth").classes("text-3xl text-primary")
                ui.label("BTBatteryLab").classes("text-2xl font-bold")

        with ui.row().classes("items-center gap-1"):
            status_dot = ui.icon("circle").props("size=10px").classes("mx-1")
            with status_dot:
                status_tooltip = ui.tooltip("")

            start_button = ui.button(on_click=lambda: manager.start()).props(
                "flat round dense icon=play_arrow"
            ).tooltip("Start collector")
            stop_button = ui.button(on_click=lambda: manager.stop()).props(
                "flat round dense icon=stop"
            ).tooltip("Stop collector")

            last_updated_label = ui.label("").classes("text-xs text-grey mx-2")

            with ui.dialog() as exit_dialog, ui.card():
                ui.label("Exit BTBatteryLab?").classes("text-lg font-semibold")
                ui.label(
                    "This stops the collector, closes BluetoothWatcher, "
                    "and closes this app completely. The dashboard tab "
                    "itself can't be closed automatically (browsers "
                    "only allow that for a tab a script opened itself) "
                    "- it'll show a \"safe to close\" message here once "
                    "everything's stopped."
                ).classes("text-sm text-grey")
                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Cancel", on_click=exit_dialog.close).props("flat")
                    ui.button("Exit", color="negative", on_click=lambda: _exit_app(manager))

            ui.button(on_click=lambda: on_refresh_click()).props(
                "flat round dense icon=refresh"
            ).tooltip("Refresh now")
            ui.button(on_click=exit_dialog.open).props(
                "flat round dense icon=power_settings_new color=negative"
            ).tooltip("Exit BTBatteryLab")

    def refresh_status() -> None:
        status = manager.status
        status_dot.props(f"color={_STATUS_COLORS.get(status, 'grey')}")
        start_button.set_enabled(status != STATUS_RUNNING)
        stop_button.set_enabled(status != STATUS_STOPPED)

        error = manager.error_message
        status_tooltip.text = error or status.capitalize()

    ui.timer(1.0, refresh_status)
    refresh_status()

    return last_updated_label


def _build_dashboard(
    manager: CollectorManager, config: Config, on_refresh: Callable[[], None]
) -> Callable[[], None]:
    with ui.card().classes("w-full"):
        ui.label("Devices").classes("text-lg font-semibold")

        # debounce=300: re-querying SQLite on every keystroke would be
        # wasteful (and, on a slow disk, briefly janky) - this waits
        # for a short pause in typing instead, same idea as a
        # search-as-you-type field anywhere else.
        with ui.row().classes("w-full items-center gap-4"):
            filter_input = (
                ui.input("Filter by name or address")
                .classes("flex-grow")
                .props("debounce=300 clearable")
            )
            status_filter_select = ui.select(
                options=_STATUS_FILTER_OPTIONS,
                value=_STATUS_FILTER_ALL,
                label="Status",
            ).classes("min-w-32")

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
        empty_label = ui.label("").classes("text-sm text-grey")

    # Side by side (wraps to stacked on narrow screens) per Test.txt
    # feedback (2026-09-28): "easier to read the data" next to each
    # other, rather than one long vertical scroll.
    with ui.row().classes("w-full gap-4 items-stretch"):
        with ui.card().classes("flex-[2] min-w-[420px]"):
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
                            # Per Test.txt feedback (2026-09-28): visible
                            # markers on each actual battery_log reading,
                            # not just a smooth line between them.
                            "showSymbol": True,
                            "symbolSize": 6,
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

        with ui.card().classes("flex-1 min-w-[300px]"):
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
            # Per Test.txt feedback (2026-09-28): drain rate/runtime
            # often can't be computed yet on a short window (1 hour/24
            # hours) - not a bug, just not enough readings/sessions -
            # shown only then, not alongside every "not enough data".
            short_window_hint = ui.label(
                "Not enough measurements in this window yet for a "
                "reliable drain rate or runtime - a longer window "
                "(7/30/90 days) usually has more to work with."
            ).classes("text-xs text-grey mt-1")
            short_window_hint.set_visibility(False)

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

        status_filter = status_filter_select.value
        if status_filter and status_filter != _STATUS_FILTER_ALL:
            rows = [row for row in rows if row["status"] == status_filter]
            empty_label.text = f"No {status_filter.lower()} devices right now."
        else:
            empty_label.text = (
                "No devices seen yet - once the collector spots one, it "
                "shows up here."
            )

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
            chart_empty_label.text = "Pick a device above to see its battery history."
            chart_empty_label.set_visibility(True)
            analysis_empty_label.set_visibility(True)
            short_window_hint.set_visibility(False)
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
        # Per Test.txt feedback (2026-09-28): a device selected but
        # offline for the whole window (e.g. offline 7 days, 7-day
        # window picked) used to show the same "pick a device above"
        # text as no selection at all - misleading, since one *is*
        # picked, there's just nothing in this window for it.
        if not points:
            chart_empty_label.text = (
                "No battery readings in this time window for this "
                "device - try a longer window above."
            )
        chart_empty_label.set_visibility(not points)

        summary = analysis_summary(report)
        analysis_empty_label.set_visibility(False)
        drain_rate_label.text = summary["drain_rate"]
        runtime_label.text = summary["estimated_runtime"]
        range_label.text = f"{summary['battery_range']} (avg {summary['average_battery']})"
        sessions_label.text = (
            f"{summary['charge_session_count']} / {summary['discharge_session_count']}"
        )
        short_window_hint.set_visibility(summary["needs_longer_window"])

    def refresh_all() -> None:
        refresh_devices()
        refresh_selected()
        on_refresh()

    def handle_device_row_click(event) -> None:
        # Per Test.txt feedback (2026-09-28): "(if possible) selecting
        # a device in the table shows its data in Battery history and
        # Analysis" - args is [click_event, row_dict, row_index] for
        # Quasar's rowClick, see NiceGUI's ui.table events.
        row = event.args[1]
        address = row.get("address")
        if address and address != device_select.value:
            device_select.value = address
        # device_select.value's own on_value_change already calls
        # refresh_all() when the value actually changes - but clicking
        # the already-selected row wouldn't trigger that, so refresh
        # unconditionally here too (a harmless extra refresh otherwise).
        refresh_all()

    device_table.on("rowClick", handle_device_row_click)

    filter_input.on_value_change(lambda _: refresh_all())
    status_filter_select.on_value_change(lambda _: refresh_all())
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
