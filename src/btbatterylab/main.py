from btbatterylab.collector.bluetooth_collector import BluetoothCollector


def main() -> None:

    print("BTBatteryLab")
    print("----------------")

    collector = BluetoothCollector()

    devices = collector.discover()

    print()
    print(f"Found {len(devices)} Bluetooth devices")
    print()

    for device in devices:
        print(f"- {device.name}")


if __name__ == "__main__":
    main()