from dataclasses import dataclass
from datetime import datetime


@dataclass
class DeviceStatus:
    """
    Current status of the Bluetooth device.
    """

    online: bool = False
    last_change: datetime | None = None
    device_name: str | None = None