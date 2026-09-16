# BTBatteryLab Architecture

## Overview

BTBatteryLab is designed as a modular platform.

Each component has a single responsibility and can evolve independently.

The platform combines Bluetooth telemetry collection, device presence monitoring, historical storage, analytics, and visualization.

---

# High-Level Architecture

```text
Bluetooth Devices
        |
        v
+-------------------+
| BLE Presence Layer|
+-------------------+
        |
        v
+-------------------+
|     Collector     |
+-------------------+
        |
        v
+-------------------+
|      Storage      |
+-------------------+
        |
        v
+-------------------+
|     Analytics     |
+-------------------+
        |
        v
+-------------------+
|     Dashboard     |
+-------------------+
```

---

# Components

## BLE Presence Layer

Responsibilities:

- Monitor device availability
- Detect connection state changes
- Generate online/offline events
- Provide real-time device status

Implementation:

```text
BluetoothLEDevice
ConnectionStatusChanged
```

Architecture:

```text
MX Master 2S
        |
        v
BluetoothWatcher (C#)
        |
        v
ble-events.jsonl
        |
        v
JsonlTailMonitor
        |
        v
BlePresenceMonitor
        |
        v
DeviceStatus
```

Device state mapping:

```text
Connected    → online=True
Disconnected → online=False
```

Output:

```python
DeviceStatus(
    online=True,
    last_change=datetime(...)
)
```

---

## Collector

Responsibilities:

- Discover Bluetooth devices
- Read battery information
- Normalize device data
- Generate telemetry events

Input:

- Windows Bluetooth APIs
- DeviceStatus

Collection rules:

```text
Device online
        ↓
Collect battery data

Device offline
        ↓
Skip collection
```

Output:

```python
{
    "device_id": "...",
    "device_name": "...",
    "battery_percent": 80,
    "timestamp": "..."
}
```

---

## Storage

Responsibilities:

- Store devices
- Store battery history
- Persist telemetry

Technology:

- SQLite

Tables:

### devices

```sql
id
name
address
type
first_seen
last_seen
```

### battery_log

```sql
id
device_id
timestamp
battery_percent
```

---

## Analytics

Responsibilities:

- Runtime estimation
- Drain rate calculation
- Battery health scoring
- Historical analysis

Example metrics:

- % per hour
- estimated runtime
- charge duration
- battery degradation

---

## Dashboard

Responsibilities:

- Device overview
- Battery visualization
- Historical charts
- Analytics display
- Online/offline status display

Technology:

- Streamlit

---

## Notifications

Responsibilities:

- Alert generation
- Battery warnings
- Notification delivery

Examples:

- Battery under 20%
- Battery under 10%
- Critical battery event
- Device unexpectedly offline

---

# Design Principles

## Privacy First

All data remains local.

No cloud infrastructure is required.

---

## Vendor Neutral

The platform should support any Bluetooth device exposing battery information.

Examples:

- Earbuds
- Headsets
- Keyboards
- Mouse devices
- Controllers

---

## Modular

Every component should be independently testable and replaceable.

The BLE monitoring layer is intentionally decoupled from battery collection.

---

## Event Driven

Device presence is propagated through events rather than periodic polling.

```text
ConnectionStatusChanged
        ↓
JSONL Event
        ↓
DeviceStatus Update
```

---

## Data Driven

All analytics are generated from collected telemetry rather than static estimates.

---

# Current Status

```text
Phase 1 - Foundation
    ├── BLE Presence Monitoring     ✅
    ├── Device Availability Model   ✅
    ├── JSONL Event Pipeline        ✅
    ├── Battery Collection          🔄
    ├── SQLite Storage              ⏳
    └── Analytics                   ⏳
```
