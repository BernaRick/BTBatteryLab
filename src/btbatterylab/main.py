'''
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
        print(f"  Satus: {device.status}")


if __name__ == "__main__":
    main()
'''

from btbatterylab.tools.property_explorer import PropertyExplorer


def main():

    explorer = PropertyExplorer()

    explorer.export_all_properties()


if __name__ == "__main__":
    main()