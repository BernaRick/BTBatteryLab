from dataclasses import dataclass


@dataclass
class Device:
    id: str
    name: str
    status: str | None = None
    device_type: str | None = None
    vendor: str | None = None