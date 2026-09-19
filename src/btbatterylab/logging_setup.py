"""
Structured logging for the long-running collector service.

Before this module, the collector (main.py, UnifiedCollector,
BluetoothCollector, SqliteStorage, config) only had print(), with a
workaround in main.py (sys.stdout.reconfigure(line_buffering=True)) to
make sure output reached BluetoothWatcher.exe's redirected
collector.log file promptly even though a pipe isn't a real terminal
and Python normally block-buffers it in that case.

configure_logging() replaces that with the standard logging module:
- Every record gets a level (INFO/WARNING/ERROR) and a real timestamp,
  instead of ad hoc "[Component] " string prefixes.
- A RotatingFileHandler under the data directory (logs/btbatterylab.log)
  gives a real, bounded-size, persistent log independent of whatever
  process happens to be redirecting stdout - this is what "logging
  engine" in the roadmap actually refers to, as opposed to the JSONL
  event pipeline (raw BLE events, a different concern) or the ad hoc
  collector.log (still produced too, since the console handler below
  still writes to stdout, which BluetoothWatcher.exe still redirects
  there in the standalone build - nothing about that changes).
- logging.StreamHandler.emit() flushes its stream after every record,
  which is what actually made the line_buffering workaround in main.py
  unnecessary once every print() there was replaced with a logger call
  - not a separate fix, a side effect of using the standard handler
  instead of building output through print()/sys.stdout directly.

Deliberately NOT used for the CLI report tools (btbatterylab.analytics,
btbatterylab.export): their printed output *is* the product (a report,
a CSV path confirmation), not a diagnostic log, so it keeps using
plain print() - adding timestamps/levels there would just be noise in
something meant to be read directly off the terminal.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

LOG_FILENAME = "btbatterylab.log"
LOG_SUBDIR = "logs"

# 5 MiB per file, keep the 3 most recent rotated files - a few tens of
# MB at most, never left to grow unbounded like collector.log always
# has.
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3

_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured_path: Path | None = None


def configure_logging(data_dir: Path | str, level: int = logging.INFO) -> Path:
    """
    Configures the root logger with a rotating file handler under
    <data_dir>/logs/btbatterylab.log, plus a console handler too -
    unless there is no console to write to (see the sys.stderr check
    below, added when run.bat/pythonw.exe made that a real case
    instead of a hypothetical one). Returns the resolved log file
    path.

    Safe to call more than once (e.g. from tests) - only the first
    call actually installs the handlers. A later call with a
    *different* data_dir does NOT move the log file: it's a no-op that
    returns the path actually in use (from the first call), not one
    computed from the data_dir just passed in - returning the latter
    would silently lie about where logging is actually going.
    """

    global _configured_path

    if _configured_path is not None:
        return _configured_path

    log_dir = Path(data_dir) / LOG_SUBDIR
    log_path = log_dir / LOG_FILENAME

    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(fmt=_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)

    # sys.stderr is None when this runs under pythonw.exe (run.bat
    # now starts the collector that way - see its own comments - so
    # there is never a console to write to): logging.StreamHandler()
    # defaults to sys.stderr, and adding one backed by None would
    # make every log call raise inside logging's own error handling
    # instead of just logging quietly to the file. Skipping it here
    # is a no-op for anyone still running python.exe in a real
    # terminal (sys.stderr is a real stream there, so the console
    # handler is still added) - only the headless case changes.
    if sys.stderr is not None:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    _configured_path = log_path

    return log_path
