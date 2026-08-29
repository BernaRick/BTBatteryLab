import json
import subprocess

from btbatterylab.models.device import Device


class BluetoothCollector:

    def discover(self) -> list[Device]:

        command = (
            "Get-PnPDevice | "
            "Where-Object {$_.Class -eq 'Bluetooth'} | "
            "Select-Object FriendlyName, InstanceId | "
            "ConvertTo-Json"
        )

        print("COMMAND:")
        print(command)
        print()

        result = subprocess.run(
            [
                "powershell",
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
        )

        print("STDOUT:")
        print(result.stdout)
        print()

        print("STDERR:")
        print(result.stderr)
        print()

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        raw_devices = json.loads(result.stdout)

        if isinstance(raw_devices, dict):
            raw_devices = [raw_devices]

        devices: list[Device] = []

        for item in raw_devices:

            name = item.get("FriendlyName")
            instance_id = item.get("InstanceId")

            if not name:
                continue

            devices.append(
                Device(
                    id=instance_id,
                    name=name,
                )
            )

        return devices