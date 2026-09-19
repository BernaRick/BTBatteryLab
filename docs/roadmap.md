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
- CSV export ✅
- Logging engine ✅

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
> Gating" plan with what was actually built. The `DeviceStatus`
> model and `BlePresenceMonitor` listed above were never wired into
> `main.py` and were removed as dead code during the v0.1 Alpha
> cleanup (2026-09-18).

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

### Step 2.6 - CSV Export ✅

Objective:

Give a way to get the raw battery history out of SQLite into a
format usable by spreadsheets or other tools, without writing SQL.

Implemented:

- New package `btbatterylab.export`: `csv_export.export_battery_log()`
  does the work (joins `battery_log` with `devices`, filters by time
  window and an optional device name/address substring, writes one
  CSV row per raw reading - not the "freshest wins" merged view used
  by `UnifiedCollector`, the full history), `__main__.py` is the CLI
  (`python -m btbatterylab.export`).
- Same `--days`/`--device`/`--db` flags as `btbatterylab.analytics`
  for consistency, plus `--out` to choose the destination file.
  Default destination: `<data dir>/exports/battery-log-<timestamp>.csv`.
- Always writes a valid CSV (header row at minimum), even when the
  filters match zero readings, so a scripted caller never has to
  special-case an empty result.
- Verified against a synthetic SQLite database (pure Python/stdlib,
  no Windows dependency, so - like `config.py` and the analytics
  module - this could be run and checked directly without Patrick's
  hardware): row counts for the full window, a narrowed window, name
  and address substring filters, and a non-matching filter all
  verified correct; the actual CLI (`python -m btbatterylab.export`)
  exercised end-to-end with both an explicit `--out` and the default
  path.

### Step 2.7 - Logging Engine ✅

Objective:

Replace the collector's ad hoc `print()`-based console output (and
the `sys.stdout.reconfigure(line_buffering=True)` workaround it
needed to reach the standalone build's redirected `collector.log`
promptly) with real structured logging: levels, timestamps, and a
log file that doesn't grow without bound.

Implemented:

- New module `btbatterylab.logging_setup`: `configure_logging(data_dir)`
  installs a console handler and a `RotatingFileHandler` (5 MB per
  file, 3 backups kept) writing to `<data_dir>/logs/btbatterylab.log`,
  both using the same `<time> <LEVEL> [<module>] <message>` format.
  Idempotent - a second call is a no-op and returns the path already
  in use, rather than silently claiming to log somewhere it isn't.
- Every `print()` in the long-running service path (`main.py`,
  `UnifiedCollector`, `SqliteStorage`, `config.py`,
  `JsonlTailMonitor`) replaced with a `logging.getLogger(__name__)`
  call at the appropriate level (`info` for normal state/lifecycle
  messages, `warning` for a config file falling back to defaults,
  `error` - with a traceback for the JSONL line-processing case -
  for real failures).
- `main.py`'s old `sys.stdout.reconfigure(line_buffering=True)`
  workaround is no longer needed and was removed:
  `logging.StreamHandler` flushes its stream after every record
  regardless of whether stdout is a real console or the pipe
  `BluetoothWatcher.exe` redirects to `collector.log` in the
  standalone build, which is exactly the case that workaround
  existed for in the first place.
- Deliberately **not** applied to the one-shot CLI report tools
  (`btbatterylab.analytics`, `btbatterylab.export`, and the manual
  diagnostic entry point in `bluetooth_collector.py`): their printed
  output is the actual product (a report, a CSV path, a device
  listing), not a diagnostic log, so adding timestamps/levels there
  would just be noise for something read directly off the terminal.
- Verified in this session (pure Python/stdlib, no Windows
  dependency): handler installation and idempotency, INFO/WARNING/
  ERROR records reaching the rotating file with the right format,
  and `UnifiedCollector`'s event handling still working end-to-end
  through the renamed `_log_state` method with no exceptions.

Not covered by this step: the log level isn't yet configurable via
`config.json` (always `INFO`) - nothing asked for it yet, and it can
be added the same way the other tuning knobs were if it's ever
needed.

### Step 2.8 - Automated Test Suite ✅

Objective:

Before moving past v0.1 Alpha, get an automated regression net around
the Python side, so the working base doesn't have to rely solely on
manual real-hardware checks going forward.

Implemented:

- `tests/`, using only Python's standard `unittest` module (no
  third-party test runner needed - works the same on this repo's
  Windows machine and anywhere else): 98 tests across 7 files, run
  with `python -m unittest discover -s tests` from the repository
  root.
- `test_config.py`, `test_logging_setup.py`, `test_sqlite_storage.py`:
  config loading/fallback behavior, `configure_logging()`
  idempotency (including a regression test for a path-caching bug
  found while writing these tests - see below), and `SqliteStorage`'s
  insert/upsert/error-handling behavior.
- `test_analytics.py`: drain rate, runtime estimation, and charge
  session detection, including regression tests that directly encode
  the two real-data reliability-filter bugs from Step 3.1
  (`MIN_SESSION_DURATION_HOURS`, `MAX_PLAUSIBLE_DISCHARGE_RATE_PERCENT_PER_HOUR`)
  so a future change can't silently weaken those constants without a
  test failing.
- `test_export.py`: CSV export windowing, device filtering, and
  output formatting.
- `test_bluetooth_collector.py`: `discover()`/`read_battery_levels()`
  parsing and multi-node merge logic, by mocking `subprocess.run`
  instead of requiring a real Windows machine - this closes a real
  gap, since that logic previously had zero automated coverage.
- `test_unified_collector.py`: the pure-logic helpers
  (`_is_generic_name`, `_parse_timestamp`, `_maybe_update_name`,
  `_maybe_update_battery`) plus an integration-style test of
  `process_json_line`/`_handle_ble_event` against a real (tmp-path)
  `SqliteStorage`.
- `test_tail_monitor.py`: `JsonlTailMonitor` followed in a background
  thread against a real temp file - waiting for the file to appear,
  only-new-lines semantics, ordering, a consumer exception not
  killing the follow loop, and clean `stop()` behavior.
- Caught one real bug along the way: an earlier version of
  `configure_logging()` computed its returned path from the
  *current* call's `data_dir` even when short-circuiting on a
  boolean "already configured" flag, so a second call from a
  different location would report logging was happening there when
  it never actually moved. Fixed by caching the real resolved path
  instead of a boolean flag; the fix shipped with a permanent
  regression test.
- README/CONTRIBUTING updated to document the suite and how to run
  it; CONTRIBUTING's "no automated test suite yet" note removed.

Not covered by this step: `BluetoothWatcher` (C#) has no automated
tests yet; the threaded `UnifiedCollector.start()`/`_polling_loop`/
`_wait_for_next_poll` methods are exercised manually rather than
under `unittest`, since they're timing-dependent enough that a
comprehensive automated version would trade a fast, reliable suite
for a slow, potentially flaky one.

### Status

🟢 v0.1 Alpha is feature-complete and shipped: presence, unified
battery collection, storage, standalone `.exe` packaging, the
configuration system, CSV export, and the logging engine are all
implemented and were verified against real hardware; the release
issue is closed. An automated test suite (98 tests, `unittest`-based)
now covers the pure-Python side, so the working base doesn't rely on
manual verification alone going into v0.2.

---

# Phase 2 - Visualization

## Version 0.2

### Features

- NiceGUI-based application (replaces the originally-planned Streamlit dashboard)
- Device overview page
- Live battery status
- Historical battery charts
- Device filtering
- Online/offline device indicators
- Live collector control panel (start/stop, current status - replaces console-only operation)

### UI Technology Decision: NiceGUI

Objective:

Decide the technology and scope for v0.2's user interface before
building it, rather than starting to code against an assumption.

Decided (2026-09-19, Patrick): a single [NiceGUI](https://nicegui.io/)
application, replacing the Streamlit dashboard originally planned
here. Instead of two separate pieces - a Streamlit app for browsing
historical analytics, and a console window/log file for the running
collector - one NiceGUI app covers both:

- **Historical side**: everything already listed above (device
  overview, last known battery status per device, historical battery
  charts, device filtering, online/offline indicators), reading from
  the same `battery_log`/`devices` tables the `analytics`/`export`
  CLIs already use.
- **Live side**: a control panel for the running collector itself
  (start/stop, current status) - replacing today's requirement of
  watching a console window or `collector.log`/`logs\btbatterylab.log`
  to know what's happening. This is the "UI instead of the console"
  part of the decision.

Architecture decided (2026-09-19, resolving the "still open" question
above): a single process. `main.py` now starts the NiceGUI app instead
of constructing/starting `UnifiedCollector` directly; the app itself
owns the collector's lifecycle (`btbatterylab.ui.collector_manager.
CollectorManager`), running it on a background thread since
`UnifiedCollector.start()` blocks the calling thread (following the
JSONL file) - the main thread stays free to run NiceGUI's own web
server. Starting the app starts monitoring automatically, matching
today's behavior; Stop is for pausing without closing the window, not
an opt-in step.

**Skeleton implemented**: `main.py` now opens a NiceGUI page
(`btbatterylab.ui.app`) with a working live control panel - Start/Stop
buttons and a status badge (`running`/`stopped`/`error`, with the error
message shown if the collector dies unexpectedly) - plus a placeholder
card for the historical side, not built yet. `CollectorManager`'s
start/stop/error state machine has full automated test coverage
(`tests/test_collector_manager.py`, 10 tests) since it's plain Python
with no `nicegui` import; the NiceGUI page's own rendering isn't
automated, the same deliberate gap as `BluetoothWatcher`'s C# side.
**Verified on a real machine (2026-09-19, Patrick)**: `pip install -e .`
picked up `nicegui` without issues once run via
`.venv\Scripts\python.exe -m pip install -e .` (a bare `pip`/`pip.exe`
doesn't exist in this project's `.venv` - only `pip3.exe` - which
confused PowerShell's command resolution; routing through
`python.exe -m pip` sidesteps that). Running `main.py` opens the page,
the Start/Stop buttons control the collector correctly, and
`logs\btbatterylab.log` keeps logging exactly as before - monitoring
is confirmed unaffected by the new UI layer.

Still open: the historical dashboard itself (device overview, battery
charts, filtering, online/offline indicators - all of it still reads
from the same `battery_log`/`devices` tables `analytics`/`export`
already use, just not wired into this UI yet); and how this fits the
existing `BluetoothWatcher.exe` standalone packaging (Step 2.4) - a
NiceGUI app opens a browser tab, which changes what "no console
windows" means for that build.

### Status

🟡 In progress - live collector control panel implemented and verified
on real hardware; historical dashboard not started

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
- `device_type`/`vendor` identification on `Device` (GitHub issue #2)

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

### Step 3.2 - Device Type & Vendor Identification

Objective:

Populate the `device_type`/`vendor` fields on the `Device` model,
which have existed since Step 2.3 but are never actually filled in
(GitHub issue #2) — currently every device shows up without a type
or manufacturer, which limits how useful a future dashboard's
device list can be.

Planned approach (decided 2026-09-18, not started):

- **Vendor**: try PnP first — extend `discover()`'s existing
  PowerShell query (Step 2.1/2.2) to also read
  `DEVPKEY_Device_Manufacturer`, the same pattern already used for
  the battery properties. If PnP can't resolve a vendor for a given
  device, store an explicit placeholder (e.g. `"Could not identify
  vendor"`) rather than `null` or falling back to an OUI/MAC lookup
  table.
- **device_type**: same PnP-first approach, via the PnP `Class`
  property, reusing the existing multi-node merge pattern from
  `read_battery_levels()`.
- Before writing the final logic: one exploratory pass with
  `tools/property_explorer.py` against Patrick's real 5 reference
  devices, to see what PnP actually reports for each, before
  committing to the exact parsing/fallback rules.
- Scope estimate: comparable to the configuration system (Step 2.5).

### Status

🟡 In Progress — drain rate, runtime estimation, and charge/discharge
session detection are implemented as a CLI report over `battery_log`;
daily statistics, presence-aware analytics, and `device_type`/`vendor`
identification (approach decided, not started) are still open.

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
