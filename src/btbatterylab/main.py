import logging

from btbatterylab.config import load_config
from btbatterylab.logging_setup import configure_logging, ensure_console_streams

# Must run before importing btbatterylab.ui.app just below, which pulls in
# nicegui: under pythonw.exe (see run.bat), sys.stdout/sys.stderr are both
# None, and nicegui/uvicorn touch one or the other during their own
# startup - without this, that crashes the whole process silently before
# the dashboard's browser tab ever opens. See ensure_console_streams()'s
# own docstring for the full story; it's a no-op under a real console
# (python.exe), so this doesn't change anything there.
ensure_console_streams()

from btbatterylab.ui.app import run_app  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> None:
    config = load_config()

    # Sets up the logging engine (see btbatterylab.logging_setup): a
    # console handler plus a rotating file under
    # <data_dir>/logs/btbatterylab.log. This also makes the old
    # sys.stdout.reconfigure(line_buffering=True) workaround
    # unnecessary - logging.StreamHandler flushes its stream after
    # every record, regardless of whether stdout is a real console or
    # a pipe (as when BluetoothWatcher.exe starts this process in the
    # background and redirects its output to collector.log).
    log_path = configure_logging(config.data_dir)

    logger.info(f"Data folder: {config.data_dir}")
    logger.info(f"Config file: {config.config_path}")
    logger.info(f"Log file: {log_path}")

    # v0.2: this used to construct and start UnifiedCollector directly
    # (blocking on it, with a KeyboardInterrupt handler calling
    # collector.stop()). Now the NiceGUI app owns that lifecycle
    # instead - see btbatterylab.ui.app and
    # btbatterylab.ui.collector_manager - so the collector can be
    # started/stopped from its Start/Stop buttons rather than only by
    # killing the whole process.
    run_app(config)


if __name__ == "__main__":
    main()
