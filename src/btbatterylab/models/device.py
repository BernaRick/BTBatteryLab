from dataclasses import dataclass


@dataclass
class Device:
    id: str
    name: str
    device_type: str | None = None
    vendor: str | None = None