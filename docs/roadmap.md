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

- Bluetooth device discovery
- Battery information collection
- Local SQLite database
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

### Step 2.2 - Battery Collection Gating

Objective:

Collect battery information only when the device is online.

Planned:

```text
Device online
        ↓
Collect battery data

Device offline
        ↓
Skip collection
```

### Status

🟡 In Progress

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
