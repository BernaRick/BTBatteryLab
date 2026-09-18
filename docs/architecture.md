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

In the current implementation, the **BLE Presence Layer** and
**Collector** layers below are one and the same component,
`UnifiedCollector` — it doesn't just consume presence events, it also
owns the PnP polling channel and the merge logic. They're kept as
separate boxes in the diagram above because they're separate
*responsibilities*, and could be split into separate classes later if
either grows enough to warrant it.

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
UnifiedCollector (_handle_ble_event)
        |
        v
DeviceState (in-memory) + SqliteStorage
```

`BluetoothWatcher` lives in this same repository under [`BluetoothWatcher/`](../BluetoothWatcher) — it used to be a separate repo, but was folded in (with its full commit history) so there is a single project to build and run. See [Getting Started](../README.md#getting-started) in the root README for how to run it.

An earlier, BLE-only prototype (`monitoring/ble_presence_monitor.py`,
`BlePresenceMonitor` + `DeviceStatus`) existed at this stage but was
never wired into `main.py` — it was superseded by `UnifiedCollector`,
which folds presence tracking and battery collection (both channels)
into one component, and was removed as dead code during the v0.1
Alpha cleanup (2026-09-18). See [Collector](#collector) below for the
actual implementation.

Device state mapping:

```text
Connected    → online=True
Disconnected → online=False
```

---

## Collector

Implemented as `UnifiedCollector`
(`src/btbatterylab/collector/unified_collector.py`), which combines
two complementary, non-overlapping data channels into one per-device
view (`DeviceState`):

- **`ble`** — real-time push events from `BluetoothWatcher`, tailed
  from `ble-events.jsonl` via `JsonlTailMonitor`. Covers presence
  (online/offline) for every paired BLE device, plus live battery for
  the ones exposing a GATT Battery Service (e.g. mice, keyboards).
- **`pnp`** — periodic polling via PowerShell/PnP
  (`BluetoothCollector.discover()` /
  `BluetoothCollector.read_battery_levels()`, in
  `collector/bluetooth_collector.py`). The only way today to read
  battery for classic (BR/EDR) devices — earbuds, headsets — that
  don't expose it over BLE. Slower (tens of seconds with several
  paired devices), so it runs on its own thread on a timer
  (`poll_interval_seconds`, 5 minutes by default) instead of in real
  time.

Responsibilities:

- Discover Bluetooth devices (via the `pnp` channel)
- Read battery information (from either channel)
- Merge both channels into a single live view per device
- Persist every reading to SQLite (see [Storage](#storage))

Merge rule: when both channels have a battery value for the same
address, the live view (`DeviceState`, used for the console output)
keeps whichever has the more recent timestamp. This only affects the
live view — every raw reading from both channels is still written to
`battery_log` regardless of which one "wins", so no historical data
is lost.

Wake-on-connect: a classic device can't report its own battery over
BLE, so its `Connected` event always arrives with no battery value.
Instead of waiting up to `poll_interval_seconds` to find out, that
event triggers an immediate PnP poll — throttled by
`MIN_POLL_SPACING_SECONDS` (15s) so several devices connecting close
together (e.g. powering on more than one headset in a row) don't each
trigger their own PowerShell poll.

Output (one row per raw reading — see [Storage](#storage) for the
actual schema):

```python
{
    "address": "FF8EDDAAF1CD",
    "device_name": "MX Master 2S",
    "battery_percent": 90,
    "timestamp": "...",
    "source": "ble",  # o "pnp"
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
DeviceState Update
```

---

## Data Driven

All analytics are generated from collected telemetry rather than static estimates.

---

# Current Status

```text
Phase 1 - Foundation
    ├── Device Presence Monitoring (BLE + classic)  ✅
    ├── Device Availability Model                   ✅
    ├── JSONL Event Pipeline                        ✅
    ├── Battery Collection (BLE + PnP, unified)     ✅
    ├── SQLite Storage                              ✅
    ├── Simplified Startup (run.bat)                ✅
    └── Analytics                                   ⏳
```
