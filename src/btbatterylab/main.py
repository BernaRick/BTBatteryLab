import logging

from btbatterylab.collector.unified_collector import UnifiedCollector
from btbatterylab.config import load_config
from btbatterylab.logging_setup import configure_logging

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

    collector = UnifiedCollector(
        jsonl_path=config.jsonl_path,
        db_path=config.db_path,
        poll_interval_seconds=config.poll_interval_seconds,
        min_poll_spacing_seconds=config.min_poll_spacing_seconds,
        pnp_timeout_seconds=config.pnp_timeout_seconds,
    )

    try:
        collector.start()

    except KeyboardInterrupt:
        collector.stop()


if __name__ == "__main__":
    main()
