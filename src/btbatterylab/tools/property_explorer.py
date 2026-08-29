import json
import subprocess
from pathlib import Path


class PropertyExplorer:

    def export_all_properties(self, output_file: str = "bluetooth_properties.json") -> None:

        command = r"""
        Get-PnpDevice |
        Where-Object {$_.Class -eq 'Bluetooth'} |
        ForEach-Object {

            $props = Get-PnpDeviceProperty `
                -InstanceId $_.InstanceId `
                -ErrorAction SilentlyContinue

            [PSCustomObject]@{
                FriendlyName = $_.FriendlyName
                Class        = $_.Class
                Status       = $_.Status
                InstanceId   = $_.InstanceId
                Properties   = $props
            }
        } |
        ConvertTo-Json -Depth 10
        """

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

        data = json.loads(result.stdout)

        output_path = Path(output_file)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False,
            )

        print(f"Export completed: {output_path}")