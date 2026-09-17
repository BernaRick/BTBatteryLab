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
- Standalone `.exe` packaging (single double-click, no console windows) ✅
- Configuration system ✅
- CSV export
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

Implemented and verified on real hardware:

- `btbatterylab.spec`: PyInstaller spec that packages the Python collector (`--onedir`, no third-party dependencies to bundle)
- `BluetoothWatcher/Program.cs`: looks for the packaged collector next to itself at startup and, if found, launches it in the background (`CreateNoWindow`, output redirected to `collector.log`) instead of requiring a second console window — falls back to the old dev behavior (nothing launched, use `run.bat`) if it's not there
- `build_exe.bat`: builds both and assembles them into `dist/release/`, so the whole thing is one double-click (`BluetoothWatcher.exe`); PyInstaller's own intermediate output is built under `%TEMP%` rather than inside the repo, to avoid `Access is denied` errors from OneDrive syncing files mid-build
- Confirmed on real hardware: single console window, "Python collector started in the background" message, `collector.log` populated (line-buffered stdout), classic-device battery arriving within seconds of connect via the wake-on-connect PnP poll, and the collector process actually terminating (checked in Task Manager) when `BluetoothWatcher.exe` is closed with ENTER

Known limitation, now resolved (see Step 2.5 below): the build used to bake in a data path hardcoded for one specific machine/user.

### Step 2.5 - Configuration System ✅

Objective:

Remove the data path hardcoded for one specific machine (it named the
developer's own Windows username and OneDrive folder), and make the
handful of tuning knobs that used to be Python constants (poll
interval, minimum PnP poll spacing, PnP timeout) adjustable without
editing source.

Implemented:

- `btbatterylab.config`: resolves the real Windows "Documents" folder
  the same way `BluetoothWatcher/Program.cs` already did
  (`Environment.SpecialFolder.MyDocuments`, i.e. the
  `...\Explorer\User Shell Folders\Personal` registry value) - correct
  even when Documents has been moved or redirected, e.g. by OneDrive.
  `BTBatteryLabData` under that folder is the data directory, same as
  before, just no longer hardcoded to one specific path.
- `config.json`, created automatically inside the data directory (with
  documented defaults) the first time the collector or the analytics
  CLI runs, if it doesn't already exist. Editable at any time; a
  missing, malformed, or partially-filled file never blocks startup -
  any invalid or missing key just falls back to its default, with a
  warning printed for whatever was ignored. See
  [config.example.json](../config.example.json) at the repo root for
  the schema (reference only, not read at runtime).
- Configurable keys: `poll_interval_seconds` (was hardcoded to 300 in
  `main.py`), `min_poll_spacing_seconds` (was the module constant
  `MIN_POLL_SPACING_SECONDS` in `unified_collector.py`, 15), and
  `pnp_timeout_seconds` (was hardcoded to 60 inside
  `BluetoothCollector.read_battery_levels`).
- `main.py` and `analytics/__main__.py` (`--db`'s default) both now
  derive their paths from this shared config instead of a literal
  string each.
- `BluetoothWatcher/Program.cs` did **not** need a change here: it was
  already computing its data directory dynamically via
  `Environment.SpecialFolder.MyDocuments` rather than a hardcoded
  path - the earlier docs describing it as hardcoded too were
  inaccurate. Only the Python side had the real portability bug.

Not covered by this step: relocating the data directory itself to a
non-default location isn't supported yet (nothing asked for it) -
`config.json` only tunes the numeric knobs above, and always lives
inside the default data directory.

### Status

🟡 In Progress — presence, unified battery collection, storage,
standalone `.exe` packaging, and the configuration system are done and
verified; CSV export and the logging engine are still open.

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

- Drain rate calculation ✅
- Runtime estimation ✅
- Charge session detection ✅
- Discharge session detection ✅
- Daily statistics
- Presence-aware analytics

### Step 3.1 - Battery Analytics over `battery_log` ✅

Objective:

Turn the raw per-reading history already persisted by `SqliteStorage`
(Step 2.3) into per-device insight, without needing the dashboard
(Phase 2) to exist first.

Implemented:

- `src/btbatterylab/analytics/battery_analytics.py`: reads
  `battery_log` for a device within a time window and groups
  consecutive readings into `BatterySession`s — a run that's all
  decreasing (discharge) or all increasing (charge); a flat reading
  extends the current session instead of splitting it
- Drain rate: percent-per-hour, weighted by each discharge session's
  duration (so one short, noisy run doesn't skew the result as much
  as a long, representative one)
- Estimated runtime: the device's last known battery percent divided
  by that drain rate — a projection from past behavior, not a live
  countdown (this module has no access to `UnifiedCollector`'s live
  in-memory state, only finished history)
- Charge sessions: the increasing runs, with start/end time and
  percent gained
- Per-device summary: reading count, min/max/average percent over
  the window, last known percent/timestamp/source
- `python -m btbatterylab.analytics` CLI (`--days`, `--device`,
  `--db`) prints a report for every device, or a filtered subset —
  see [Getting Started](../README.md#battery-analytics-python--m-btbatterylabanalytics)

Not yet implemented: daily statistics and presence-aware analytics
(cross-referencing drain rate against online/offline periods).

### Status

🟡 In Progress — drain rate, runtime estimation, and charge/discharge
session detection are implemented as a CLI report over `battery_log`;
daily statistics and presence-aware analytics are still open.

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
