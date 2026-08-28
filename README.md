# BTBatteryLab

BTBatteryLab is an open-source Bluetooth battery monitoring and analytics platform for Windows.

The goal of the project is simple:

> Transform Bluetooth battery data into meaningful insights.

Instead of only displaying a battery percentage, BTBatteryLab collects historical battery information, stores it locally, and provides analytics about battery health, runtime, charging behavior, and device trends.

---

## Why BTBatteryLab?

Windows can display the current battery level of some Bluetooth devices, but it does not provide:

- Battery history
- Runtime estimation
- Battery drain analysis
- Charging statistics
- Battery health trends
- Multi-device monitoring

BTBatteryLab fills that gap.

---

## Features

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

2026-08-28 15:00
OPPO Enco Air2
Battery: 80%

2026-08-28 15:05
OPPO Enco Air2
Battery: 78%

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
- Battery health indicators

---

## Architecture

BTBatteryLab consists of five main components:

BTBatteryLab

├── collector
├── storage
├── analytics
├── dashboard
├── notifications

### Collector

Discovers Bluetooth devices and collects battery information.

### Storage

Persists device and battery telemetry.

### Analytics

Generates runtime and health metrics.

### Dashboard

Visualizes battery data and device status.

### Notifications

Provides battery alerts and warnings.

---

## Project Roadmap

### v0.1 Alpha

- Device discovery
- Battery collection
- SQLite database
- CSV export
- Logging engine

### v0.2

- Streamlit dashboard
- Device overview
- History charts

### v0.3

- Runtime calculations
- Battery drain metrics
- Session detection

### v0.4

- Notifications
- Low battery alerts
- Device health metrics

### v1.0

- Stable release
- Dashboard
- Analytics engine
- Multi-device support

---

## Principles

### Open Source

The project is fully open source and community driven.

### Privacy First

All data is stored locally.

### Vendor Neutral

BTBatteryLab is not tied to any manufacturer.

The goal is to support any Bluetooth device exposing battery information through Windows.

### Data Driven

All analytics are based on collected telemetry rather than static estimates.

---

## Status

Current status:

Early development (Alpha)

The project originated from a real-world investigation into abnormal battery drain of Bluetooth earbuds and evolved into a generic Bluetooth battery analytics platform.

---

## Contributing

Contributions, feature suggestions, bug reports, and device compatibility reports are welcome.

---

## License

MIT License
