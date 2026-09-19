import logging

from btbatterylab.config import load_config
from btbatterylab.logging_setup import configure_logging
from btbatterylab.ui.app import run_app

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
