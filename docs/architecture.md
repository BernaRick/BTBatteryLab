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
Bluetooth device (BLE or classic)
        |
        v
BluetoothWatcher (C#, ./BluetoothWatcher)
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

`BluetoothWatcher` lives in this same repository under [`BluetoothWatcher/`](../BluetoothWatcher) — it used to be a separate repo, but was folded in (with its full commit history) so there is a single project to build and run. See [Getting Started](../README.md#getting-started) in the root README for how to run it.

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

- SQLite (`src/btbatterylab/storage/sqlite_storage.py`, `SqliteStorage`)

By default the database file lives next to `ble-events.jsonl`
(`Documents/BTBatteryLabData/btbatterylab.db`), one connection shared
across threads (WAL mode + an internal lock), since `UnifiedCollector`
writes from both the JSONL-tailing thread and the PnP polling thread.

Every battery reading observed by either channel is recorded as-is —
not just the one that "wins" the live in-memory view in
`UnifiedCollector` — so `battery_log` keeps the full raw history
needed later for drain rate / runtime / trend analysis.

Tables (actual schema, address is the primary key — a device's
Bluetooth address, uppercase hex with no separators, e.g.
`FF8EDDAAF1CD`):

### devices

```sql
CREATE TABLE devices (
    address     TEXT PRIMARY KEY,
    name        TEXT,
    first_seen  TEXT NOT NULL,  -- ISO 8601
    last_seen   TEXT NOT NULL   -- ISO 8601, never moves backwards
)
```

### battery_log

```sql
CREATE TABLE battery_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    address          TEXT NOT NULL REFERENCES devices(address),
    timestamp        TEXT NOT NULL,  -- ISO 8601
    battery_percent  INTEGER NOT NULL,
    source           TEXT NOT NULL,  -- "ble" o "pnp"
    UNIQUE(address, timestamp, source)
)
```

A `type` column (ble / classic / dual) is a natural future addition
once device-type classification exists somewhere in the collector —
not populated today.

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
    ├── Battery Collection          ✅
    ├── SQLite Storage              ✅
    └── Analytics                   ⏳
```
