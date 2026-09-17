import sys

from btbatterylab.collector.unified_collector import UnifiedCollector
from btbatterylab.config import load_config


def main() -> None:
    # When this process is started in the background by
    # BluetoothWatcher.exe (standalone build, see build_exe.bat)
    # instead of in an interactive console, stdout/stderr are no
    # longer a terminal but a pipe: Python automatically switches from
    # line-buffering to block-buffering, so print() output stays stuck
    # in an internal buffer until it fills up or the process ends -
    # with only a few lines per minute, effectively never. This is why
    # the log ended up empty (or never even created), not because of a
    # problem in the data collection logic. We always force
    # line-buffering, so every printed line reaches whoever is reading
    # stdout right away, whether that's a real console or
    # BluetoothWatcher.exe's log file.
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    config = load_config()

    print(f"Data folder: {config.data_dir}")
    print(f"Config file: {config.config_path}")

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
