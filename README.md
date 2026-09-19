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

BTBatteryLab now unifies two complementary data channels — real-time BLE presence/battery events and periodic PnP battery polling for classic (BR/EDR) devices — into a single collector, and persists every reading to a local SQLite database.

Validated scenario:

```text
Mouse OFF   → online=False
Mouse ON    → online=True, battery read live over BLE
Headset ON  → online=True, battery read within seconds via a
              triggered PnP poll (no BLE battery available)
```

Reference devices used during development:

```text
Logitech MX Master 2S (BLE, GATT Battery Service)
OPPO Enco Air2 (classic, PnP battery polling)
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

Planned as a single [NiceGUI](https://nicegui.io/)-based application
(decided 2026-09-19, replacing the Streamlit dashboard originally
planned here — see [docs/roadmap.md](./docs/roadmap.md) for the full
decision), covering two things at once:

- **Historical side**: current battery levels, runtime estimates,
  historical charts, multi-device overview, device health indicators,
  online/offline device status.
- **Live side**: a control panel for the running collector itself
  (start/stop, current status), replacing today's console
  window/log-file-only visibility into what the collector is doing.

Not started yet — technology decided, no code or architecture written.

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

The current implementation uses a dedicated presence-monitoring pipeline. `BluetoothWatcher` (C#) lives inside this same repository, under [`BluetoothWatcher/`](./BluetoothWatcher) (see [Getting Started](#getting-started)):

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

Device state mapping:

```text
Connected    → online=True
Disconnected → online=False
```

---

## Getting Started

BTBatteryLab has two parts that run side by side, both living in this one repository: a C# watcher that talks to the Windows Bluetooth APIs, and a Python collector that reads and combines the battery data.

### Prerequisites

- Windows 10/11
- [.NET 8 SDK](https://dotnet.microsoft.com/download) (for `BluetoothWatcher`)
- Python 3.11+ (for the collector)
- A virtual environment with the package installed: `python -m venv .venv` then `.venv\Scripts\pip install -e .`

### Quick start: `run.bat`

Once the `.venv` above is set up, double-click [`run.bat`](./run.bat) in the repo root. It starts the Python collector and `BluetoothWatcher` in the right order (see the tip below), each in its own console window.

### Standalone build: `build_exe.bat`

For a single double-click with only one console window, run [`build_exe.bat`](./build_exe.bat) (needs the `.venv` above, plus the .NET 8 SDK — it installs PyInstaller itself if missing). It packages the Python collector with PyInstaller and publishes `BluetoothWatcher` self-contained into `dist/release/`; the result, `dist/release/BluetoothWatcher.exe`, starts the Python collector for you in the background (no separate window) when you double-click it.

This has now been verified on real hardware: single console window, background collector startup, `collector.log` populated, and battery readings for classic devices arriving within seconds of connect. The data path is resolved automatically (see [Configuration](#configuration) below), so the build is no longer tied to one specific machine/user.

### Manual start (or if you want to see what `run.bat`/`build_exe.bat` do)

#### 1. Run the BLE/presence watcher (C#)

```powershell
cd BluetoothWatcher
dotnet run
```

This discovers your paired Bluetooth devices — both BLE and classic/BR-EDR — tracks their connection status in real time, and writes events to `Documents\BTBatteryLabData\ble-events.jsonl`.

#### 2. Run the collector (Python)

```powershell
.venv\Scripts\python.exe -m btbatterylab.main
```

This follows that same `ble-events.jsonl` file live, and polls Windows PnP in the background (every 5 minutes by default, or immediately after a classic device connects) to read battery levels for devices that don't expose them over BLE — earbuds and headsets, mostly.

> **Tip:** start the Python collector before `dotnet run` if you can. The collector only follows *new* lines written after it starts, so if the watcher's initial "device found" events are written first, that device's online/offline status stays unknown (`?`) until the next real connect/disconnect.

This is still an early-development project — `build_exe.bat` above gets you a single double-clickable `.exe`, verified on real hardware, and it now works from any Windows account without editing source (see [Configuration](#configuration)).

### Configuration

Both the collector and the analytics CLI read a small `config.json`
inside your data folder (`Documents\BTBatteryLabData\config.json` by
default — the real Windows "Documents" location is resolved
automatically, including when it's been moved or redirected, e.g. by
OneDrive). The file is created for you, with sensible defaults, the
first time you run either one — just open it and edit the values you
want to change, no restart tricks needed beyond starting the process
again. See [config.example.json](./config.example.json) for the full
list of keys and what each one does (`poll_interval_seconds`,
`min_poll_spacing_seconds`, `pnp_timeout_seconds`). A missing or
invalid key is never fatal — it just falls back to its default, with a
warning logged (see [Logging](#logging) below).

### Battery analytics: `python -m btbatterylab.analytics`

Once some history has been collected into `btbatterylab.db` (see [Historical Data](#historical-data)), run:

```powershell
.venv\Scripts\python.exe -m btbatterylab.analytics
```

for a per-device report over the last 30 days: reading count, min/max/average battery percent, drain rate (%/hour, from the discharge runs found in `battery_log`), an estimated remaining runtime projected from that rate, and any detected charge sessions. Useful flags: `--days N` to change the time window, `--device "name or address"` to filter to one device, and `--db path\to\btbatterylab.db` to point at a database anywhere other than the default data folder.

This is a plain projection from past history, not a live countdown — it has no idea whether a device is online or currently charging (that lives only in `UnifiedCollector`'s in-memory state while it's running).

### CSV export: `python -m btbatterylab.export`

Exports the raw `battery_log` history — every reading recorded from either channel (`ble`/`pnp`), not just the one that "wins" in the live view — to a CSV file, for spreadsheets or any tool outside BTBatteryLab:

```powershell
.venv\Scripts\python.exe -m btbatterylab.export
```

By default this writes `battery-log-<timestamp>.csv` into an `exports` subfolder of your data folder, covering the last 30 days. Same `--days N` and `--device "name or address"` filters as the analytics CLI, plus `--out path\to\file.csv` to choose the destination yourself and `--db` to point at a different database. Each row is `address,device_name,timestamp,battery_percent,source`.

### Logging

The collector (`main.py`) writes structured, leveled log records (INFO/WARNING/ERROR with a timestamp) to two places: the console, same as before, and a rotating log file at `Documents\BTBatteryLabData\logs\btbatterylab.log` (capped at 5 MB per file, keeping the 3 most recent — it will never grow without bound the way the old standalone-build `collector.log` could). This replaced the previous ad hoc `print()`-based output and the `line_buffering` workaround it needed to reach `collector.log` promptly when the process is started in the background (see [Standalone build](#standalone-build-build_exebat)) — a normal log handler flushes every record on its own.

The one-shot CLI report tools (`btbatterylab.analytics`, `btbatterylab.export`) are unaffected — their printed output is the actual report/result, not a diagnostic log, so they keep using plain `print()`.

### Automated tests

The Python side (`src/btbatterylab/`) has an automated test suite (`tests/`), built entirely on Python's standard `unittest` module — no extra install needed. It covers configuration, structured logging, SQLite storage, battery analytics (including regression tests for the two real-data drain-rate bugs described in the [roadmap](docs/roadmap.md)), CSV export, the unified collector's event-handling logic, and the JSONL tail monitor. `BluetoothCollector`'s PowerShell-dependent methods (`discover`/`read_battery_levels`) are tested by mocking `subprocess.run`, so the suite runs the same on any machine — no real Windows Bluetooth hardware or PowerShell required.

This is also the first thing to run if something isn't working and you're not sure why — a clean pass is a quick way to rule out a broken install before digging further.

**Easiest way to run it**: double-click `test.bat` at the repository root. It uses a friendlier console runner (`tests/run_tests.py`) than raw `unittest`: expected output from tests that deliberately trigger an error or warning path (there are a few, on purpose, to check those paths are handled correctly) is hidden unless that specific test actually fails, and the result is color-coded (green for pass, red for fail). At the end it prints a breakdown by area (configuration, battery analytics, CSV export, and so on) so you can see at a glance which part - if any - has a problem, followed by a one-line overall summary. Colors are automatically skipped when the output isn't a real terminal, so redirecting it to a file (e.g. to attach it when reporting a problem) always produces plain, readable text.

Equivalent from a terminal, from the repository root:

```powershell
.venv\Scripts\python.exe tests\run_tests.py
```

The plain `unittest` invocation still works if you'd rather have the raw output (e.g. for scripting):

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
```

(`BluetoothWatcher`, the C# BLE presence layer, has no automated tests yet.)

---

## Project Roadmap

### v0.1 Alpha

- Device discovery ✅
- BLE presence monitoring ✅
- Online/offline device state ✅
- JSONL event pipeline ✅
- Battery collection ✅
- SQLite database ✅
- Simplified startup (`run.bat`) ✅
- Standalone `.exe` packaging (single double-click, no console windows) ✅
- CSV export ✅
- Logging engine ✅

### v0.2

- NiceGUI-based application (replaces the originally-planned Streamlit dashboard) ⚪ Planned — see [docs/roadmap.md](./docs/roadmap.md)
- Device overview
- Live battery status
- History charts
- Live collector control panel (start/stop, current status)

### v0.3

- Runtime calculations ✅
- Battery drain metrics ✅
- Session detection ✅ (charge/discharge; daily stats and presence-aware analytics still open — see [docs/roadmap.md](./docs/roadmap.md))

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
