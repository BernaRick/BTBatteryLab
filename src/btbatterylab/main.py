import sys

from btbatterylab.collector.unified_collector import UnifiedCollector


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

    collector = UnifiedCollector(
        jsonl_path=(
            r"C:\Users\PatrickBernardoni\OneDrive - Patrick Bernardoni"
            r"\Documents\BTBatteryLabData\ble-events.jsonl"
        ),
        # PnP polling is slow (tens of seconds with 5 paired devices):
        # every 5 minutes is a reasonable trade-off for now, to be
        # revisited once there's a configuration system.
        poll_interval_seconds=300.0,
    )

    try:
        collector.start()

    except KeyboardInterrupt:
        collector.stop()


if __name__ == "__main__":
    main()
