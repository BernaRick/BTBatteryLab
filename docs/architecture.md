# BTBatteryLab Architecture

## Overview

BTBatteryLab is designed as a modular platform.

Each component has a single responsibility and can evolve independently.

---

# High-Level Architecture

```text
Bluetooth Devices
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

## Collector

Responsibilities:

- Discover Bluetooth devices
- Read battery information
- Normalize device data
- Generate telemetry events

Input:

- Windows Bluetooth APIs

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

---

## Data Driven

All analytics are generated from collected telemetry rather than static estimates.
