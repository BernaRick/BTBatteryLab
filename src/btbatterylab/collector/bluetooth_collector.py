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
    Extracts the Bluetooth address (12 hex digits) from a Windows PnP
    InstanceId in the "classic" format (...DEV_<address>...). Used by
    discover(). Returns None if the pattern isn't found.
    """

    if not instance_id:
        return None

    match = _ADDRESS_PATTERN.search(instance_id)

    if not match:
        return None

    return match.group(1).upper()


class BluetoothCollector:

    def __init__(self, pnp_timeout_seconds: float = 60.0) -> None:
        # How long a single PnP battery poll (read_battery_levels) is
        # allowed to run before we give up on it - overridable, see
        # btbatterylab.config. Deliberately does NOT affect discover(),
        # which is a separate, much quicker PowerShell query with its
        # own fixed 15s timeout.
        self._pnp_timeout_seconds = pnp_timeout_seconds

    def discover(self):
        command = (
            "Get-PnpDevice | "
            "Where-Object {$_.Class -eq 'Bluetooth'} | "
            "Select-Object FriendlyName, Status, InstanceId | "
            "ConvertTo-Json -Depth 3"
        )


        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    command,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired as ex:
            raise RuntimeError(
                "Discovery via PowerShell too slow (over 15s)."
            ) from ex

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
        Queries the PnP nodes of all Bluetooth devices (not only the ones
        in Class='Bluetooth': a classic device like earbuds/headsets
        often reports its battery on its Hands-Free AudioGateway node,
        which is Class='System') to find who actually exposes a battery
        value to Windows.

        Returns a BatteryReading for every Bluetooth address that
        reports a value, with the REAL timestamp of the last update seen
        by Windows (not "now"): for a classic device not connected at
        query time, this value can go back minutes or hours, and it's
        correct for the data to reflect that instead of passing it off
        as a fresh reading.

        device_id is the Bluetooth address (via DEVPKEY_Bluetooth_
        DeviceAddress, more reliable than parsing the InstanceId given
        how inconsistent the formats are across nodes), so the reading
        can be matched back to the right Device (Device.address) even
        when it comes from a different node than the one discovered in
        discover().
        """

        command = (
            "Get-PnpDevice | "
            "Where-Object "
            "{$_.Class -eq 'Bluetooth' -or $_.Service -eq 'BthHFEnum'} | "
            "ForEach-Object {"
            "    $properties = Get-PnpDeviceProperty "
            "        -InstanceId $_.InstanceId "
            "        -ErrorAction SilentlyContinue;"
            "    $address = ($properties | "
            "        Where-Object KeyName -eq "
            "        'DEVPKEY_Bluetooth_DeviceAddress').Data;"
            "    $level = ($properties | "
            f"        Where-Object KeyName -eq '{BATTERY_LEVEL_KEY}'"
            "    ).Data;"
            "    $updatedRaw = ($properties | "
            f"        Where-Object KeyName -eq '{BATTERY_UPDATED_KEY}'"
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

        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    command,
                ],
                capture_output=True,
                text=True,
                timeout=self._pnp_timeout_seconds,
            )
        except subprocess.TimeoutExpired as ex:
            raise RuntimeError(
                "Battery query via PowerShell too slow "
                f"(over {self._pnp_timeout_seconds:.0f}s): can happen if a "
                "device is connecting/disconnecting right at that moment "
                "(slows down the driver stack). If it persists with all "
                "devices stable, the filter might need to be narrowed "
                "further, or pnp_timeout_seconds raised in config.json."
            ) from ex

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        stdout = result.stdout.strip()
        raw_items = json.loads(stdout) if stdout else []

        # "ForEach-Object" with no object emitted produces $null, which
        # ConvertTo-Json serializes as the string "null" (not an empty
        # string): no device reported a battery value.
        if raw_items is None:
            raw_items = []

        if isinstance(raw_items, dict):
            raw_items = [raw_items]

        now = datetime.now()

        # The same device can have multiple PnP nodes each reporting a
        # battery value (e.g. the Hands-Free node and another
        # BLE-related node), not always in agreement - and Windows
        # sometimes writes the address with different casing depending
        # on the node. We group by normalized address and for each one
        # keep the reading with the most recent timestamp, instead of
        # whichever comes first in the (arbitrary) order Get-PnpDevice
        # returns the nodes.
        best_by_device: dict[str, tuple[int, datetime]] = {}

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

            device_id = address.upper() if address else instance_id

            timestamp = now

            if updated_raw:
                try:
                    # normalize "Z" to "+00:00": some Python versions
                    # before 3.11 don't accept "Z" in fromisoformat().
                    normalized = updated_raw.replace("Z", "+00:00")
                    parsed = datetime.fromisoformat(normalized)

                    if parsed.tzinfo is not None:
                        # Convert back to "naive" local time, consistent
                        # with datetime.now() used elsewhere (e.g. the
                        # fallback above, or the comparison in the
                        # __main__ block): without this, subtracting an
                        # "aware" timestamp from a "naive" one raises
                        # TypeError.
                        parsed = parsed.astimezone().replace(tzinfo=None)

                    timestamp = parsed
                except ValueError:
                    timestamp = now

            current_best = best_by_device.get(device_id)

            if current_best is None or timestamp > current_best[1]:
                best_by_device[device_id] = (battery_percent, timestamp)

        return [
            BatteryReading(
                device_id=device_id,
                battery_percent=battery_percent,
                timestamp=timestamp,
            )
            for device_id, (battery_percent, timestamp)
            in best_by_device.items()
        ]


if __name__ == "__main__":
    # Manual, human-run diagnostic entry point (python -m
    # btbatterylab.collector.bluetooth_collector): its printed output
    # *is* the thing being read, directly off the terminal, so it keeps
    # using print() rather than the logging engine - same reasoning as
    # the analytics/export CLI tools, see btbatterylab.logging_setup.
    collector = BluetoothCollector()

    devices = collector.discover()

    print("=== Bluetooth devices found ===")
    for device in devices:
        print(
            f"- {device.name} ({device.status}) "
            f"[addr={device.address}] [{device.id}]"
        )

    print()
    print("=== Available battery levels ===")
    readings = collector.read_battery_levels()

    devices_by_address = {
        device.address: device
        for device in devices
        if device.address
    }

    if not readings:
        print("No device reported a battery level.")
    else:
        now = datetime.now()

        for reading in readings:
            device = devices_by_address.get(reading.device_id)
            label = device.name if device else "(unknown name)"

            age_minutes = (now - reading.timestamp).total_seconds() / 60
            freshness = (
                "live/recent"
                if age_minutes < 2
                else f"stale by {age_minutes:.0f} min"
            )

            print(
                f"- {label} [{reading.device_id}]: "
                f"{reading.battery_percent}% "
                f"({reading.timestamp}, {freshness})"
            )
