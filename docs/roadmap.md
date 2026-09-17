# BTBatteryLab Roadmap

## Vision

BTBatteryLab aims to become a complete Bluetooth battery monitoring and analytics platform for Windows.

The project focuses on collecting battery telemetry, storing historical data, and generating useful insights about battery health and device usage.

---

# Phase 1 - Foundation

## Version 0.1 Alpha

Goal:

Create a functional replacement for manual PowerShell battery logging.

### Features

- Bluetooth device discovery ✅
- Battery information collection ✅
- Local SQLite database ✅
- Simplified startup (`run.bat`) ✅
- Standalone `.exe` packaging (single double-click, no console windows)
- CSV export
- Configuration system
- Logging engine

### Step 2.1 - BLE Presence Monitoring ✅

Objective:

Implement reliable Bluetooth device presence detection.

Implemented:

- BluetoothLEDevice integration
- ConnectionStatusChanged monitoring
- JSONL event logging
- DeviceStatus model
- BlePresenceMonitor
- JsonlTailMonitor
- End-to-end validation between BluetoothWatcher and BTBatteryLab

Validated scenario:

```text
Mouse OFF  → online=False
Mouse ON   → online=True
```

Architecture:

```text
MX Master 2S
    ↓
BluetoothLEDevice
    ↓
ConnectionStatusChanged
    ↓
JSONL
    ↓
BTBatteryLab
    ↓
DeviceStatus
```

> **Update:** this step has since been extended to cover classic
> (BR/EDR) devices too, and its implementation was folded into
> `UnifiedCollector` together with battery collection — see
> **Step 2.2** below, which replaces the original "Battery Collection
> Gating" plan with what was actually built.

### Step 2.2 - Unified Battery Collection ✅

Objective:

Collect battery information from every paired device, BLE and
classic (BR/EDR) alike, without relying on a single "online → collect,
offline → skip" rule — BLE devices report presence but not always
battery, and classic devices report neither over BLE.

Implemented:

- `UnifiedCollector`, combining two channels into one per-device view
- `ble` channel: presence + battery (when available) over BLE, pushed in real time from `BluetoothWatcher`
- `pnp` channel: periodic PowerShell/PnP polling (`BluetoothCollector`), the only way to read battery for classic devices that don't expose it over BLE
- Freshest-timestamp-wins merge when both channels report a battery value for the same device
- Wake-on-connect: a classic device's `Connected` event (no battery over BLE) triggers an immediate PnP poll instead of waiting for the next scheduled one, throttled so several devices connecting close together don't each trigger their own poll
- Every raw reading from both channels persisted to SQLite (see Step 2.3), independent of the in-memory merge

Validated scenario:

```text
OPPO Enco Air2 (classic) connects
    ↓
BluetoothWatcher logs "Connected", no battery
    ↓
UnifiedCollector triggers an immediate PnP poll
    ↓
Battery percentage available within seconds, instead of up to
poll_interval_seconds later
```

### Step 2.3 - SQLite Storage ✅

Objective:

Persist every battery reading and known device locally, so later
phases (analytics, dashboard) have real historical data to work with.

Implemented:

- `SqliteStorage`, one shared connection (WAL mode) across the JSONL-tailing and PnP-polling threads
- `devices` table: address as primary key, name, first/last seen (upsert keeps the best known name, `last_seen` never regresses)
- `battery_log` table: every raw reading from either channel, deduplicated only on exact repeats
- Database file stored alongside `ble-events.jsonl`, outside the git repository (see [Getting Started](../README.md#getting-started))

See [docs/architecture.md](./architecture.md#storage) for the full schema.

### Step 2.4 - Repository Consolidation & Simplified Startup ✅

Objective:

Keep the C# watcher and the Python collector in one place, with one
easy way to start both.

Implemented:

- `BluetoothWatcher` folded into this repository under `BluetoothWatcher/`, full commit history preserved via `git subtree`
- `run.bat` starts both processes, in the right order, from one double-click

Planned:

- Real standalone `.exe` packaging, so running BTBatteryLab doesn't require a Python/`.NET` dev setup at all (tracked in the Features list above)

### Status

🟡 In Progress — presence, unified battery collection, and storage
are done; CSV export, the configuration system, the logging engine,
and standalone `.exe` packaging are still open.

---

# Phase 2 - Visualization

## Version 0.2

### Features

- Streamlit dashboard
- Device overview page
- Live battery status
- Historical battery charts
- Device filtering
- Online/offline device indicators

### Status

⚪ Planned

---

# Phase 3 - Analytics

## Version 0.3

### Features

- Drain rate calculation
- Runtime estimation
- Charge session detection
- Discharge session detection
- Daily statistics
- Presence-aware analytics

### Status

⚪ Planned

---

# Phase 4 - Battery Health

## Version 0.4

### Features

- Battery health scoring
- Battery degradation detection
- Long-term trend analysis
- Anomaly detection

### Status

⚪ Planned

---

# Phase 5 - Notifications

## Version 0.5

### Features

- Low battery alerts
- Desktop notifications
- Critical battery warnings
- Configurable thresholds
- Offline device alerts

### Status

⚪ Planned

---

# Phase 6 - Production Release

## Version 1.0

### Features

- Stable API
- Full dashboard
- Multi-device management
- Historical analytics
- Documentation
- Public release

### Status

⚪ Planned

---

# Long-Term Goals

Future research areas:

- System tray application
- Vendor-specific integrations
- Battery charge cycle tracking
- Device benchmarking
- Advanced battery health models
- Multi-vendor support
- Cross-platform support
- Plugin system
- Device telemetry APIs
