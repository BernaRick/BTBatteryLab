"""
Start/stop lifecycle wrapper around UnifiedCollector, for the NiceGUI
app's live control panel.

Deliberately has no import of nicegui: it's framework-agnostic on
purpose, so it can be unit-tested the same way as the rest of this
project (see tests/test_collector_manager.py) without needing a
running NiceGUI server, and so the UI layer (btbatterylab.ui.app)
stays a thin wrapper around this instead of growing its own state
machine.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from btbatterylab.collector.unified_collector import UnifiedCollector

logger = logging.getLogger(__name__)

# The three states the UI's status label/buttons need to know about.
STATUS_STOPPED = "stopped"
STATUS_RUNNING = "running"
STATUS_ERROR = "error"


class CollectorManager:
    """
    UnifiedCollector.start() is a blocking call (it follows the JSONL
    file on the calling thread until stop()), which doesn't fit a
    single-process NiceGUI app where the main thread is busy running
    the web server (ui.run()). This class runs it on a background
    thread instead, and exposes a simple status a UI can poll and a
    couple of buttons can call - the same one instance is meant to
    live for the whole lifetime of the app.

    A stopped UnifiedCollector can't be restarted in place - stop()
    closes its database connection, and its internal stop Event, once
    set, never clears - so start() always builds a fresh instance via
    the injected factory rather than trying to reuse the previous one.
    """

    def __init__(self, collector_factory: Callable[[], UnifiedCollector]) -> None:
        # Takes no arguments, returns a new UnifiedCollector each call.
        # Injected (rather than this class building one itself from a
        # Config) so it can be unit-tested with a fake factory, the
        # same pattern already used for BluetoothCollector/SqliteStorage
        # elsewhere in this project.
        self._collector_factory = collector_factory

        self._lock = threading.Lock()
        self._collector: UnifiedCollector | None = None
        self._thread: threading.Thread | None = None
        self._error: str | None = None

    @property
    def status(self) -> str:
        with self._lock:
            if self._error is not None:
                return STATUS_ERROR
            if self._collector is not None:
                return STATUS_RUNNING
            return STATUS_STOPPED

    @property
    def error_message(self) -> str | None:
        with self._lock:
            return self._error

    def start(self) -> None:
        """
        No-op if already running (or in the error state - press Stop
        first to clear it). Otherwise builds a fresh UnifiedCollector
        and starts following/polling on a background thread.
        """

        with self._lock:
            if self._collector is not None:
                return

            collector = self._collector_factory()
            self._collector = collector
            self._error = None

        def _run() -> None:
            try:
                collector.start()
            except Exception as ex:
                logger.error(
                    f"Collector stopped unexpectedly: {ex}", exc_info=True
                )
                with self._lock:
                    # Only replace the current state if this thread's
                    # collector is still the active one - a stale
                    # thread from a collector that was already stop()ed
                    # must not clobber a newer start().
                    if self._collector is collector:
                        self._error = str(ex)
                        self._collector = None

        thread = threading.Thread(target=_run, daemon=True)
        self._thread = thread
        thread.start()

    def stop(self) -> None:
        """
        No-op if already stopped. Also clears the error state, so
        Stop doubles as "acknowledge the error" before the next Start.
        """

        with self._lock:
            collector = self._collector
            self._collector = None
            self._error = None

        if collector is not None:
            collector.stop()

    def snapshot(self) -> dict:
        """
        The current per-device view (see UnifiedCollector.snapshot()),
        or empty when not running - never raises just because the
        collector happens to be stopped.
        """

        with self._lock:
            collector = self._collector

        if collector is None:
            return {}

        return collector.snapshot()
