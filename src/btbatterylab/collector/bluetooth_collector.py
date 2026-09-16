import json
import subprocess
from datetime import datetime

from btbatterylab.models.device import Device
from btbatterylab.models.battery_reading import BatteryReading

# Undocumented but widely used Windows device property that exposes the
# battery level reported by a Bluetooth device (classic and BLE) once it
# has been surfaced by the driver. It is not part of the public PnP
# property set, so it is only present on devices that actually report a
# battery level to Windows.
BATTERY_PROPERTY_KEY = "{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2"

EXCLUDED_KEYWORDS = [
    "Generic Attribute",
    "Generic Access",
    "Enumerator",
    "RFCOMM",
    "Transport",
    "Service",
    "Wireless Bluetooth",
]


class BluetoothCollector:

    def discover(self):
        command = (
            "Get-PnpDevice | "
            "Where-Object {$_.Class -eq 'Bluetooth'} | "
            "Select-Object FriendlyName, Status, InstanceId | "
            "ConvertTo-Json -Depth 3"
        )


        result = subprocess.run(
            [
                "powershell",
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        raw_devices = json.loads(result.stdout)

        if isinstance(raw_devices, dict):
            raw_devices = [raw_devices]

        devices: list[Device] = []

        seen_names = set()

        for item in raw_devices:

            name = item.get("FriendlyName")
            status = item.get("Status")
            instance_id = item.get("InstanceId")

            if not name:
                continue

            if any(
                keyword.lower() in name.lower()
                for keyword in EXCLUDED_KEYWORDS
            ):
                continue

            if name in seen_names:
                continue

            seen_names.add(name)

            devices.append(
                Device(
                    id=instance_id,
                    name=name,
                    status=status,
                )
            )

        return devices

    def read_battery_levels(self) -> list[BatteryReading]:
        """
        Interroga ogni dispositivo Bluetooth per la percentuale di
        batteria riportata a Windows (quando disponibile).

        Restituisce una BatteryReading per ogni dispositivo che espone
        davvero un valore di batteria: i dispositivi che non lo
        riportano (o non sono al momento connessi) vengono scartati
        anziche' produrre letture false.
        """

        command = (
            "Get-PnpDevice | "
            "Where-Object {$_.Class -eq 'Bluetooth'} | "
            "ForEach-Object {"
            "    $level = (Get-PnpDeviceProperty "
            f"        -InstanceId $_.InstanceId "
            f"        -KeyName '{BATTERY_PROPERTY_KEY}' "
            "        -ErrorAction SilentlyContinue"
            "    ).Data;"
            "    [PSCustomObject]@{"
            "        FriendlyName = $_.FriendlyName;"
            "        InstanceId   = $_.InstanceId;"
            "        BatteryLevel = $level"
            "    }"
            "} | "
            "ConvertTo-Json -Depth 3"
        )

        result = subprocess.run(
            [
                "powershell",
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        raw_items = json.loads(result.stdout)

        if isinstance(raw_items, dict):
            raw_items = [raw_items]

        now = datetime.now()

        readings: list[BatteryReading] = []

        for item in raw_items:

            name = item.get("FriendlyName")
            instance_id = item.get("InstanceId")
            battery_level = item.get("BatteryLevel")

            if not name or instance_id is None:
                continue

            if any(
                keyword.lower() in name.lower()
                for keyword in EXCLUDED_KEYWORDS
            ):
                continue

            if battery_level is None:
                # Property not present for this device: it does not
                # report battery, or it is not currently connected.
                continue

            try:
                battery_percent = int(battery_level)
            except (TypeError, ValueError):
                continue

            readings.append(
                BatteryReading(
                    device_id=instance_id,
                    battery_percent=battery_percent,
                    timestamp=now,
                )
            )

        return readings


if __name__ == "__main__":
    collector = BluetoothCollector()

    print("=== Dispositivi Bluetooth trovati ===")
    for device in collector.discover():
        print(f"- {device.name} ({device.status}) [{device.id}]")

    print()
    print("=== Livelli batteria disponibili ===")
    readings = collector.read_battery_levels()

    if not readings:
        print("Nessun dispositivo ha riportato un livello di batteria.")
    else:
        for reading in readings:
            print(
                f"- {reading.device_id}: "
                f"{reading.battery_percent}% "
                f"({reading.timestamp})"
            )
