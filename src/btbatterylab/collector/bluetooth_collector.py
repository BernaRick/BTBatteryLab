import json
import re
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

# Matches the 12 hex-digit Bluetooth address embedded in a PnP InstanceId,
# e.g. "BTHENUM\DEV_50C275770AE8\..." or "BTHLE\DEV_50C275770AE8\...".
# The same physical device can show up as *two* separate PnP nodes (one
# classic BR/EDR under BTHENUM, one BLE under BTHLE) with two different
# InstanceIds but the same embedded address: extracting it lets us match
# a battery reading back to the device it actually belongs to.
_ADDRESS_PATTERN = re.compile(r"DEV_([0-9A-Fa-f]{12})")


def extract_address(instance_id: str | None) -> str | None:
    """
    Estrae l'indirizzo Bluetooth (12 cifre hex) da un InstanceId PnP di
    Windows. Restituisce None se il pattern non viene trovato.
    """

    if not instance_id:
        return None

    match = _ADDRESS_PATTERN.search(instance_id)

    if not match:
        return None

    return match.group(1).upper()


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
                    address=extract_address(instance_id),
                )
            )

        return devices

    def read_battery_levels(self) -> list[BatteryReading]:
        """
        Interroga ogni dispositivo Bluetooth per la percentuale di
        batteria riportata a Windows (quando disponibile).

        Restituisce una BatteryReading per ogni nodo PnP che espone
        davvero un valore di batteria: i dispositivi che non lo
        riportano (o non sono al momento connessi) vengono scartati
        anziche' produrre letture false.

        device_id qui e' l'indirizzo Bluetooth estratto dall'InstanceId
        (es. "50C275770AE8"), non l'InstanceId grezzo: un device
        "dual mode" (classico + BLE) puo' comparire come due nodi PnP
        diversi con InstanceId diversi ma stesso indirizzo, e la
        batteria spesso arriva dal nodo BLE mentre discover() elenca
        quello classico. Usare l'indirizzo permette di ricollegare la
        lettura al Device giusto (Device.address).
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
        seen_addresses = set()

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

            address = extract_address(instance_id)
            device_id = address or instance_id

            if device_id in seen_addresses:
                # Lo stesso device puo' avere piu' nodi PnP che
                # riportano tutti la batteria (raro ma possibile):
                # teniamo solo la prima lettura.
                continue

            seen_addresses.add(device_id)

            readings.append(
                BatteryReading(
                    device_id=device_id,
                    battery_percent=battery_percent,
                    timestamp=now,
                )
            )

        return readings


if __name__ == "__main__":
    collector = BluetoothCollector()

    devices = collector.discover()

    print("=== Dispositivi Bluetooth trovati ===")
    for device in devices:
        print(
            f"- {device.name} ({device.status}) "
            f"[addr={device.address}] [{device.id}]"
        )

    print()
    print("=== Livelli batteria disponibili ===")
    readings = collector.read_battery_levels()

    devices_by_address = {
        device.address: device
        for device in devices
        if device.address
    }

    if not readings:
        print("Nessun dispositivo ha riportato un livello di batteria.")
    else:
        for reading in readings:
            device = devices_by_address.get(reading.device_id)
            label = device.name if device else "(nome sconosciuto)"
            print(
                f"- {label} [{reading.device_id}]: "
                f"{reading.battery_percent}% "
                f"({reading.timestamp})"
            )
