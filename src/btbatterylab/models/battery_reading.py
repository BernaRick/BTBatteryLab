from dataclasses import dataclass
from datetime import datetime


@dataclass
class BatteryReading:
    device_id: str
    battery_percent: int
    timestamp: datetime