from btbatterylab.monitoring.ble_presence_monitor import (
    BlePresenceMonitor,
)
from btbatterylab.monitoring.tail_monitor import (
    JsonlTailMonitor,
)


def main() -> None:
    monitor = BlePresenceMonitor()

    tail = JsonlTailMonitor(
        path=r"C:\Users\PatrickBernardoni\OneDrive - Patrick Bernardoni\Documents\BTBatteryLabData\ble-events.jsonl",
        consumer=monitor,
    )

    try:
        tail.start()

    except KeyboardInterrupt:
        tail.stop()


if __name__ == "__main__":
    main()