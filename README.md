<img width="250" height="250" alt="1" src="https://github.com/user-attachments/assets/dea32260-bf35-4caf-b551-b6876902d595" />

# BTBatteryLab

BTBatteryLab is an open-source Bluetooth battery monitoring and analytics platform for Windows.

The goal of the project is simple:

> Transform Bluetooth battery data into meaningful insights.

Instead of only displaying a battery percentage, BTBatteryLab collects historical battery information, stores it locally, and provides analytics about battery health, runtime, charging behavior, and device trends.

---

## Current Status

Early development (Alpha)

The project originated from a real-world investigation into abnormal battery drain of Bluetooth devices and evolved into a generic Bluetooth battery analytics platform.

### Latest Milestone ✅

BTBatteryLab now supports real-time Bluetooth device presence detection using native Windows BLE APIs.

Validated scenario:

```text
Mouse OFF  → online=False
Mouse ON   → online=True
```

Current reference device:

```text
Logitech MX Master 2S
```

---

## Why BTBatteryLab?

Windows can display the current battery level of some Bluetooth devices, but it does not provide:

- Battery history
- Runtime estimation
- Battery drain analysis
- Charging statistics
- Battery health trends
- Multi-device monitoring
- Device presence history
- Online/offline tracking

BTBatteryLab fills that gap.

---

## Features

### BLE Presence Monitoring ✅

Monitor Bluetooth device availability in real time.

Implemented using:

```text
BluetoothLEDevice
ConnectionStatusChanged
```

Capabilities:

- Real-time online detection
- Real-time offline detection
- Event-based architecture
- JSONL event pipeline

Example:

```text
Connected    → online=True
Disconnected → online=False
```

---

### Device Discovery

Automatically discover Bluetooth devices that expose battery information.

Supported device categories include:

- Wireless earbuds
- Headphones
- Mouse devices
- Keyboards
- Game controllers
- Stylus devices
- Bluetooth peripherals

---

### Battery Collection

Collect battery telemetry over time.

Example:

```text
2026-08-28 15:00
OPPO Enco Air2
Battery: 80%

2026-08-28 15:05
OPPO Enco Air2
Battery: 78%
```

---

### Historical Data

Store battery information locally using SQLite.

No cloud services.

No external telemetry.

Your data remains on your machine.

---

### Battery Analytics

Analyze:

- Battery drain rate
- Estimated runtime
- Charging speed
- Charge/discharge sessions
- Battery degradation trends

---

### Dashboard

Planned dashboard features:

- Current battery levels
- Runtime estimates
- Historical charts
- Multi-device overview
- Device health indicators
- Online/offline device status

---

## Architecture

BTBatteryLab follows a modular architecture.

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

### BLE Presence Layer

The current implementation uses a dedicated BLE monitoring pipeline:

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
BTBatteryLab (Python)
        |
        v
DeviceStatus
```

Device state mapping:

```text
Connected    → online=True
Disconnected → online=False
```

---

## Project Roadmap

### v0.1 Alpha

- Device discovery ✅
- BLE presence monitoring ✅
- Online/offline device state ✅
- JSONL event pipeline ✅
- Battery collection 🔄
- SQLite database
- CSV export
- Logging engine

### v0.2

- Streamlit dashboard
- Device overview
- Live battery status
- History charts

### v0.3

- Runtime calculations
- Battery drain metrics
- Session detection

### v0.4

- Battery health analytics
- Degradation metrics
- Trend analysis

### v0.5

- Notifications
- Low battery alerts
- Offline device alerts

### v1.0

- Stable release
- Dashboard
- Analytics engine
- Multi-device support
- Documentation

---

## Principles

### Open Source

The project is fully open source and community driven.

### Privacy First

All data is stored locally.

### Vendor Neutral

BTBatteryLab is not tied to any manufacturer.

The goal is to support any Bluetooth device exposing battery information through Windows.

Examples:

- Earbuds
- Headsets
- Mice
- Keyboards
- Controllers

### Modular

Every component should be independently testable and replaceable.

### Event Driven

Device presence is propagated through events instead of periodic polling.

### Data Driven

All analytics are based on collected telemetry rather than static estimates.

---

## Contributing

Contributions, feature suggestions, bug reports, and device compatibility reports are welcome.

---

## License

MIT License
