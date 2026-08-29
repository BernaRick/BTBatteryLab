import json
from datetime import datetime
from pathlib import Path

from btbatterylab.models.device_status import DeviceStatus


class BlePresenceMonitor:
    """
    Traduce gli eventi JSONL generati da BleMonitor
    in uno stato ONLINE/OFFLINE.
    """

    def __init__(self) -> None:
        self.status = DeviceStatus()

    def process_event(self, event: dict) -> None:
        """
        Processa un singolo evento JSON.
        """

        event_type = event.get("Event")
        connection_status = event.get("Status")

        if event_type not in ("Startup", "ConnectionStatusChanged"):
            return

        if connection_status == "Connected":
            self.status.online = True

        elif connection_status == "Disconnected":
            self.status.online = False

        else:
            return

        self.status.device_name = event.get("DeviceName")

        timestamp = event.get("Timestamp")

        if timestamp:
            try:
                self.status.last_change = datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                )
            except ValueError:
                self.status.last_change = datetime.now()

    def process_json_line(self, line: str) -> None:
        """
        Processa una singola riga JSONL.
        """

        line = line.strip()

        if not line:
            return

        event = json.loads(line)

        self.process_event(event)

    def load_file(self, file_path: str | Path) -> DeviceStatus:
        """
        Carica e processa un intero file JSONL.
        """

        path = Path(file_path)

        with path.open(
            mode="r",
            encoding="utf-8"
        ) as file:

            for line in file:
                self.process_json_line(line)

        return self.status

    @property
    def online(self) -> bool:
        return self.status.online

    @property
    def offline(self) -> bool:
        return not self.status.online