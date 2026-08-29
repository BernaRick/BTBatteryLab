import json
import subprocess

from btbatterylab.models.device import Device


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

        excluded_keywords = [
            "Generic Attribute",
            "Generic Access",
            "Enumerator",
            "RFCOMM",
            "Transport",
            "Service",
            "Wireless Bluetooth",
        ]

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
                for keyword in excluded_keywords
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