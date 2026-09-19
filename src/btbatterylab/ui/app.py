"""
The NiceGUI application - v0.2's UI, replacing both the console-only
collector and the originally-planned Streamlit dashboard (see
docs/roadmap.md, "UI Technology Decision: NiceGUI").

This first version is a minimal skeleton, on purpose: a status
label plus Start/Stop for the live collector control panel, and a
placeholder for the historical dashboard (device overview, battery
charts, ...) that will fill this same page in a later step. The goal
right now is to get the single-process architecture right - one
process running both the NiceGUI web server and UnifiedCollector (as
a background thread, via CollectorManager) - before building out the
rest of the UI on top of it.

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

_STATUS_COLORS = {
    STATUS_RUNNING: "positive",
    STATUS_ERROR: "negative",
}


def _build_page(manager: CollectorManager) -> None:
    ui.label("BTBatteryLab").classes("text-2xl font-bold")

    with ui.card():
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

    with ui.card():
        ui.label("Historical dashboard").classes("text-lg font-semibold")
        ui.label(
            "Coming soon: device overview, last known battery status, "
            "historical battery charts, device filtering, and "
            "online/offline indicators (see docs/roadmap.md, v0.2)."
        ).classes("text-sm text-grey")


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
        _build_page(manager)

    # Starts monitoring right away, same as running main.py used to -
    # the UI's Stop button is for pausing, not an opt-in step.
    manager.start()

    # reload=False: NiceGUI's auto-reload spawns a watcher subprocess
    # that re-imports this module, which doesn't play well with being
    # started from BluetoothWatcher.exe's background process (and
    # later, PyInstaller packaging - see docs/roadmap.md's still-open
    # question on how this fits build_exe.bat).
    ui.run(title="BTBatteryLab", reload=False, show=True)
