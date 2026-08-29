from dataclasses import dataclass
from datetime import datetime


@dataclass
class DeviceStatus:
    """
    Stato corrente del dispositivo Bluetooth.
    """

    online: bool = False
    last_change: datetime | None = None
    device_name: str | None = None