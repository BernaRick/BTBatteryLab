import json
import re
import subprocess
from datetime import datetime

from btbatterylab.models.device import Device
from btbatterylab.models.battery_reading import BatteryReading

# Undocumented but widely used Windows device property that exposes the
# battery level reported by a Bluetooth device once it has been surfaced
# by the driver. It is not part of the public PnP property set, so it is
# only present on the specific PnP node that actually tracks it - which
# varies by device: BLE mice/keyboards usually expose it on their BTHLE
# node, while classic audio devices (earbuds, headsets) expose it on
# their Hands-Free AudioGateway node (Class "System", *not* "Bluetooth").
# PID 2 is the level (0-100); PID 7 is the timestamp of the last update,
# which lets us know how stale a reading is instead of guessing.
BATTERY_LEVEL_KEY = "{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2"
BATTERY_UPDATED_KEY = "{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 7"

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
    Windows nel formato "classico" (...DEV_<address>...). Usata da
    discover(). Restituisce None se il pattern non viene trovato.
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
        Interroga i nodi PnP di tutti i dispositivi Bluetooth (non solo
        quelli in Class='Bluetooth': un device classico come cuffie/
        auricolari riporta spesso la batteria sul suo nodo Hands-Free
        AudioGateway, che e' Class='System') per trovare chi espone
        davvero un valore di batteria a Windows.

        Restituisce una BatteryReading per ogni indirizzo Bluetooth che
        riporta un valore, con il timestamp REALE dell'ultimo
        aggiornamento visto da Windows (non "adesso"): per un device
        classico non connesso al momento della query, questo valore
        puo' risalire a minuti o ore prima, ed e' corretto che il dato
        lo rifletta invece di spacciarlo per una lettura fresca.

        device_id e' l'indirizzo Bluetooth (via DEVPKEY_Bluetooth_
        DeviceAddress, piu' affidabile di un parsing dell'InstanceId
        visto quanto sono eterogenei i formati tra i vari nodi), cosi'
        da ricollegare la lettura al Device giusto (Device.address)
        anche quando arriva da un nodo diverso da quello scoperto in
        discover().
        """

        command = (
            "Get-PnpDevice | "
            "Where-Object "
            "{$_.Class -eq 'Bluetooth' -or $_.Service -eq 'BthHFEnum'} | "
            "ForEach-Object {"
            "    $address = (Get-PnpDeviceProperty "
            "        -InstanceId $_.InstanceId "
            "        -KeyName 'DEVPKEY_Bluetooth_DeviceAddress' "
            "        -ErrorAction SilentlyContinue"
            "    ).Data;"
            "    $level = (Get-PnpDeviceProperty "
            "        -InstanceId $_.InstanceId "
            f"        -KeyName '{BATTERY_LEVEL_KEY}' "
            "        -ErrorAction SilentlyContinue"
            "    ).Data;"
            "    $updatedRaw = (Get-PnpDeviceProperty "
            "        -InstanceId $_.InstanceId "
            f"        -KeyName '{BATTERY_UPDATED_KEY}' "
            "        -ErrorAction SilentlyContinue"
            "    ).Data;"
            "    $updated = if ($updatedRaw) "
            "        { $updatedRaw.ToString('yyyy-MM-ddTHH:mm:ss.ffffffK') } "
            "        else { $null };"
            "    if ($level -ne $null) {"
            "        [PSCustomObject]@{"
            "            FriendlyName   = $_.FriendlyName;"
            "            InstanceId     = $_.InstanceId;"
            "            Address        = $address;"
            "            BatteryLevel   = $level;"
            "            BatteryUpdated = $updated"
            "        }"
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

        stdout = result.stdout.strip()
        raw_items = json.loads(stdout) if stdout else []

        # "ForEach-Object" senza nessun oggetto emesso produce $null,
        # che ConvertTo-Json serializza come la stringa "null" (non
        # una stringa vuota): nessun device ha riportato batteria.
        if raw_items is None:
            raw_items = []

        if isinstance(raw_items, dict):
            raw_items = [raw_items]

        now = datetime.now()

        readings: list[BatteryReading] = []
        seen_addresses = set()

        for item in raw_items:

            instance_id = item.get("InstanceId")
            battery_level = item.get("BatteryLevel")
            address = item.get("Address")
            updated_raw = item.get("BatteryUpdated")

            if instance_id is None or battery_level is None:
                continue

            try:
                battery_percent = int(battery_level)
            except (TypeError, ValueError):
                continue

            device_id = address or instance_id

            if device_id in seen_addresses:
                # Lo stesso device puo' avere piu' nodi PnP che
                # riportano tutti la batteria: teniamo solo il primo.
                continue

            seen_addresses.add(device_id)

            timestamp = now

            if updated_raw:
                try:
                    # normalizza "Z" in "+00:00": alcune versioni di
                    # Python precedenti alla 3.11 non accettano "Z" in
                    # fromisoformat().
                    normalized = updated_raw.replace("Z", "+00:00")
                    timestamp = datetime.fromisoformat(normalized)
                except ValueError:
                    timestamp = now

            readings.append(
                BatteryReading(
                    device_id=device_id,
                    battery_percent=battery_percent,
                    timestamp=timestamp,
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
        now = datetime.now()

        for reading in readings:
            device = devices_by_address.get(reading.device_id)
            label = device.name if device else "(nome sconosciuto)"

            age_minutes = (now - reading.timestamp).total_seconds() / 60
            freshness = (
                "live/recente"
                if age_minutes < 2
                else f"vecchia di {age_minutes:.0f} min"
            )

            print(
                f"- {label} [{reading.device_id}]: "
                f"{reading.battery_percent}% "
                f"({reading.timestamp}, {freshness})"
            )
