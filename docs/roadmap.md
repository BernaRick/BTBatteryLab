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

**Historical dashboard implemented (2026-09-19)**: the placeholder card is
now a real device overview table (name, address, last known battery
reading and source, live online/offline status, last seen) with a
name/address filter, plus a battery-history line chart (`ui.echart`,
bundled with NiceGUI itself - no new dependency) with a device picker
and a time-window picker (last 24 hours/7/30/90 days). Both refresh on
a 5-second timer. Two new modules support this, both deliberately kept
free of any `nicegui` import so they stay unit-testable the same way as
`CollectorManager`:

- `btbatterylab.ui.history_reader` - read-only queries over
  `battery_log`/`devices` (`list_devices()`, `battery_history()`), using
  a short-lived `sqlite3` connection per refresh rather than a shared
  one - safe to do concurrently with `UnifiedCollector`'s own writer
  connection since `SqliteStorage` already runs in WAL mode
  (`tests/test_history_reader.py`, 12 tests).
- `btbatterylab.ui.dashboard_data` - turns that history plus
  `CollectorManager.snapshot()`'s live state into table rows and chart
  series. Online/offline is live-only, same as the control panel's own
  status: it's never persisted to SQLite, so it only ever reads
  "Online"/"Offline" while the collector is actually running and has
  observed that device this run - "Unknown" otherwise
  (`tests/test_dashboard_data.py`, 16 tests).

**Verified on a real machine (2026-09-19, Patrick)**: dashboard renders
and updates correctly - "per una prima prova la UI va bene" (good for a
first try). Patrick then used it for a while before asking for the
round of polish described next.

### UI restyle and Analysis card (2026-09-19)

After testing the dashboard for a while, Patrick asked for three things:
a friendlier, more styled UI that makes information - especially the
analysis data - stand out; both terminal windows started by `run.bat`
hidden completely (not minimized); and a manual page-refresh button.
Two follow-up choices, both via explicit question to Patrick:
**stop mechanism** - an Exit button in the dashboard stops the Python
collector and closes its process, with a separate `stop.bat` for
`BluetoothWatcher.exe` (chosen over minimizing windows and keeping
Ctrl+C/ENTER); **scope** - both bringing the existing
`btbatterylab.analytics` calculations into the dashboard and a general
visual restyle (chosen over doing just one).

**Analysis card implemented**: `btbatterylab.ui.dashboard_data.
analysis_summary()` formats a `btbatterylab.analytics.battery_analytics.
DeviceReport` (drain rate, estimated runtime, average battery, battery
range, reading count, charge/discharge session counts) for four stat
tiles next to the chart, reusing the existing analytics module rather
than duplicating any calculation (`tests/test_dashboard_data.py`, 18
new tests: battery-level banding, per-row badge color, and
`analysis_summary()` formatting - 34 tests total in that file now).

**Visual restyle implemented**: the device table's battery and status
columns render as colored Quasar badges (green/amber/red/grey, via
NiceGUI's `add_slot()` + `q-badge`) instead of plain text - good at
50% or above, warning 20-49%, critical below 20%, matching the existing
"positive"/"warning"/"negative"/"grey" status-badge idiom already used
by the live control panel rather than introducing a second color
system. The battery-history chart gained matching shaded threshold
bands (ECharts `markArea`) at the same 20%/50% cutoffs. The header
gained a manual refresh icon and an Exit icon (confirmation dialog,
then stops the collector and closes the app), and the page got a
max-width centered layout. Followed the `dataviz` skill's principles
(status colors reserved and never color-alone, single-hue sequential
encoding, hover tooltips) adapted to NiceGUI's Quasar-based styling
rather than the skill's raw CSS-variable machinery, which targets
hand-built HTML/SVG.

**Windowless `run.bat`/`BluetoothWatcher.exe` implemented**: the Python
collector now launches via `pythonw.exe` (the windowless CPython
variant) instead of `python.exe`, and `BluetoothWatcher.csproj`'s
`OutputType` changed from `Exe` to `WinExe`, so neither process ever
allocates a console window, in `run.bat` or in the standalone build.
This forced two follow-on changes: `BluetoothWatcher`'s stop mechanism
(`Console.ReadLine()`, blocking for ENTER) doesn't work without a
console, so it's now `Task.Delay(Timeout.Infinite)` plus external
termination via `stop.bat` (`taskkill /F /IM BluetoothWatcher.exe /T`,
which also takes down the embedded Python collector); and
`BluetoothWatcher`'s own console output now redirects to
`Documents\BTBatteryLabData\logs\watcher.log` instead of a terminal.
Also fixed a real bug this surfaced: `logging_setup.py`'s console
handler defaulted to `sys.stderr`, which is `None` under `pythonw.exe`
and would have crashed on the first log line - now guarded and covered
by a regression test. `run.bat` itself now does a synchronous
`dotnet build` followed by launching the built `.exe` directly, since
`dotnet run`'s own console (belonging to `dotnet.exe`, not the target
project) isn't affected by `OutputType` and would otherwise still show
a window in dev mode.

This also resolves the packaging question left open above: since both
processes are windowless regardless of how they're launched, the
standalone `.exe` build needs no special-case handling for "no console
windows" any more - `build_exe.bat` now generates a matching `stop.bat`
next to `BluetoothWatcher.exe` in the dist folder.

**Not verified on a real machine when written**: this round's C#
changes (`BluetoothWatcher.csproj`, `Program.cs`) could not be
compiled - no `dotnet` SDK available in this session - and were
checked only by careful manual review; the NiceGUI changes (`app.py`,
`dashboard_data.py`) could only be checked with `ast.parse`, the same
limitation as before. If the windowless behavior causes problems, the
rollback is straightforward: revert `BluetoothWatcher.csproj`'s
`OutputType` to `Exe` and `run.bat`'s Python launch back to
`python.exe`. This round's first real test did surface a real bug -
see the follow-up entry right below - but once that was fixed,
Patrick confirmed the whole round works ("ok funziona, fatto test").

### Follow-up bug: `run.bat` stopped opening the browser (2026-09-19)

Patrick pulled the round above and reported exactly the kind of
problem it was flagged as untested for: `run.bat` no longer opened
the dashboard in the browser at all ("run.bat non apre piu il
browser con la UI"). With no console window left to show a
traceback on, there was nothing to look at directly - diagnosed by
reasoning through what `pythonw.exe` actually does differently from
`python.exe`.

**Root cause**: `pythonw.exe` sets `sys.stdin`, `sys.stdout`, AND
`sys.stderr` all to `None` - not just `sys.stderr`, which is the
only one `logging_setup.configure_logging()`'s existing guard (see
above) checks. That guard only protects this project's own console
log handler from crashing; it does nothing about a plain `print()`
or a `sys.stdout.isatty()` check made by *other* code before that
point - and both `nicegui` and the `uvicorn` server underneath it
commonly do exactly that during their own startup (deciding whether
to use colored output, printing a startup banner, and so on). Under
`python.exe` in a real terminal this is harmless; under
`pythonw.exe`, calling `.write()` or `.isatty()` on `None` raises
`AttributeError`, which - with no console to print the traceback on
either - kills the whole process silently before the browser is
ever opened. This fits the report exactly: no error, no window, no
dashboard.

**Fix**: a new `ensure_console_streams()` in `logging_setup.py`,
called as literally the first thing `main.py` does - before its
import of `btbatterylab.ui.app` (which is what pulls in `nicegui`)
- redirects `sys.stdout`/`sys.stderr` to a real file
(`logs\pythonw-stdio.log`) whenever either is `None`, and is a
no-op otherwise (so `python.exe` in a real terminal is unaffected).
This is the standard fix for a `pythonw.exe`-launched application -
the same category of problem BluetoothWatcher's `Console.SetOut`/
`SetError` redirection already solved on the C# side, just not yet
applied on the Python side until now. **3 new tests**
(`tests/test_logging_setup.py`) cover: both streams already real is
a no-op; both `None` get redirected and a plain `print()` afterward
doesn't raise (the actual bug, reproduced directly); only the one
that's `None` gets redirected. **158 tests total, all passing**
(155 from the round above plus these 3).

**Confirmed working (2026-09-19, Patrick)**: "ok funziona, fatto
test" - the browser opens again, and the round above (badges, chart
bands, Analysis card, refresh/exit icons, windowless `run.bat`/
`stop.bat`) works. This diagnosis was reasoned from how `pythonw.exe`
behaves rather than from a traceback actually seen (there was
nothing to see it on), so it's worth remembering `logs\pythonw-
stdio.log` (new) exists if anything similar ever resurfaces - it
should now capture whatever a third-party library would otherwise
have printed, alongside `logs\btbatterylab.log`.

### Test.txt feedback round (2026-09-28)

After the round above was confirmed working and the standalone build
rebuilt, Patrick did a further round of testing on real hardware and
sent back a `Test.txt` with six UI requests and five bugs. Six
clarifying questions were asked first (`AskUserQuestion`) rather than
guessing on the two genuinely ambiguous ones, and answered before any
change was made.

**UI requests, all implemented**:

- Collector status/Start/Stop moved from their own full-width
  "Collector" card into the header, restyled to match the compact
  icon-first Refresh/Exit buttons (the ambiguous one - confirmed
  "move it, don't just restyle it in place").
- A user-selectable online/offline/unknown status filter on the
  device table, alongside the existing name/address text filter.
- `source` moved to the last column of the device table.
- Battery history and Analysis now sit side by side (wrapping to
  stacked on narrow screens) instead of stacked full-width.
- A "Last 1 hour" option added to the Battery history window picker -
  turned out to need no special-casing anywhere: `battery_history()`/
  `build_device_report()` already only use `window_days` inside a
  `timedelta(...)`, which accepts a plain float (`1/24`) just as well
  as an int.
- The battery-history chart now shows a visible marker (`showSymbol`)
  on every actual reading, not just a smooth interpolated line.

**Bugs, all root-caused by reading the actual code (not guessed) before
fixing**:

- **"Last seen" wrong for offline devices** (stuck at dashboard-launch
  time). Root cause: `_poll_pnp_battery()` called
  `SqliteStorage.record_device_seen()` - which advances `last_seen` -
  for *every* PnP battery reading, including stale/cached values
  Windows keeps reporting for a device that's actually offline (see
  `BluetoothCollector.read_battery_levels()`'s own docstring, which
  already documented this). But presence is architecturally the
  "ble" channel's job (`_handle_ble_event`, which BluetoothWatcher
  fires for every paired device, BLE and classic alike, on every real
  connect/disconnect) - PnP polling has no reliable way to tell a
  fresh reading from a stale one, so it should never touch
  `last_seen` at all. **Fix**: a new `SqliteStorage.ensure_device_exists()`
  that creates the device row if missing (so `record_battery()`'s
  foreign key is satisfied) but never advances `last_seen` or the name
  on conflict - `_poll_pnp_battery()` now calls this instead of
  `record_device_seen()`.
- **Inaccurate "Estimated runtime left" / "Battery range (avg)" /
  charge-discharge session counts**. Two compounding root causes: (1)
  `_poll_pnp_battery()` wrote a brand new `battery_log` row on *every*
  poll, even when the value hadn't changed - for a device stuck
  reporting the same cached percentage while offline, that's a new row
  every `poll_interval_seconds`, and when the real value finally
  changed on reconnect, the transition looked artificially fast
  (bloating `reading_count` and, mostly caught by the existing
  `MAX_PLAUSIBLE_DISCHARGE_RATE_PERCENT_PER_HOUR` filter, effectively
  losing that signal rather than misrepresenting it). (2) A device
  found at (say) 80% and not seen again for days until it reconnected
  at 60% was treated as one continuous discharge session spanning the
  whole gap - a drain rate so slow it implied days of remaining
  runtime, when the battery was actually used up during whatever time
  it was really connected. **Fix**: `_poll_pnp_battery()` now tracks
  the last value it wrote per address and skips the write when
  unchanged; `battery_analytics._build_sessions()` now has a
  `MAX_READING_GAP_HOURS` (6.0) - a gap longer than that between two
  readings for the same device closes out whatever session was
  building instead of bridging across it, on the reasoning that a real
  connected device reports far more often than that, so a long silence
  almost always means it was actually offline.
- **Exit button not closing everything** (Patrick's report: didn't
  close the browser or `BluetoothWatcher.exe`, only stopped the
  collector). This was a deliberate design decision from the round
  above (Exit = collector + Python process, `stop.bat` = separate for
  `BluetoothWatcher`) that Patrick asked to widen rather than a bug in
  the narrower behavior - confirmed via `AskUserQuestion` ("Exit
  should close everything"). **Fix**: `_exit_app()` now also runs
  `taskkill /F /IM BluetoothWatcher.exe /T` (the same mechanism
  `stop.bat` already used), and a `threading.Timer`-based hard
  `os._exit()` failsafe fires a few seconds later in case
  `app.shutdown()` doesn't actually end the process on its own -
  `app.shutdown()`'s behavior has varied across NiceGUI
  versions/native-vs-browser modes, so this guarantees the process
  ends either way instead of chasing every version's exact behavior.
  The browser tab itself stays outside the app's control (a script can
  only close a tab it opened itself) - the exit-confirmation dialog's
  text was reworded to not promise that.
- **Two flashing PowerShell console windows** on every PnP poll cycle,
  with no output. Root cause: neither of `BluetoothCollector`'s two
  `subprocess.run(["powershell", ...])` calls (`discover()`,
  `read_battery_levels()`) passed `creationflags=CREATE_NO_WINDOW` -
  harmless while the parent ran under `python.exe` with its own real
  console for the child to share, but a regression exposed by the
  2026-09-19 windowless change (`pythonw.exe` has no console of its
  own, so each PowerShell child now opens a brand new, briefly-visible
  one). "2 windows" matches exactly: one call each. **Fix**: both
  calls now pass `creationflags` (0, a no-op, on anything but Windows -
  this module's own tests run on Linux with `subprocess.run` mocked).
- **Slow battery status update at dashboard launch**. Root cause:
  `UnifiedCollector.start()` kicks off the first PnP poll immediately,
  and `_poll_pnp_battery()` ran `discover()` (up to 15s) and
  `read_battery_levels()` (up to `pnp_timeout_seconds`, 60s by
  default) one after another - up to ~75s worst case before a classic
  device (no BLE Battery Service) shows any battery data. **Fix**:
  the two calls - independent of each other; `discover()` only
  supplies display names here - now run concurrently on a
  `ThreadPoolExecutor`, cutting the worst case roughly in half to
  `max(~15s, pnp_timeout_seconds)`. A genuine architecture change (e.g.
  reading battery from the C# watcher instead of PowerShell/WMI) would
  cut this further but is out of scope for this round.

**19 new/changed tests** across `test_sqlite_storage.py`,
`test_unified_collector.py`, `test_analytics.py`,
`test_bluetooth_collector.py`, and `test_history_reader.py`. **177
tests total, all passing.**

**Confirmed working on real hardware** - Patrick pushed the change and
rebuilt the standalone `.exe`, then did a further round of testing
(see below) rather than reporting any regression from this round.

### Test.txt feedback round 2 (2026-09-28)

Patrick's further testing after confirming the round above surfaced
five more UI requests and three more bugs, sent as a second `Test.txt`.
No clarifying questions were needed this time - each item was clear
enough to implement directly with judgment calls noted inline below.

**UI requests, all five implemented**:

- Header buttons "more minimal and visually uniform" - the status
  badge + separator combo from the round above was replaced with a
  single row of small flat/dense icon buttons (Start/Stop/Refresh/
  Exit) plus one small colored status dot (hover for the actual
  status text), matching Quasar's own icon-button conventions instead
  of mixing element styles.
- The battery-history chart showing "Pick a device above..." even
  when a device *was* selected but simply had no readings in the
  current time window (e.g. offline for the last 7 days, filtered to
  "Last 7 days"). **Fix**: the empty-state message is now
  context-aware - "Pick a device..." only when nothing is selected,
  "No battery readings in this time window for this device - try a
  longer window above" when a device is selected but the query
  returned nothing.
- Battery history and Analysis given a different width ratio (2:1
  instead of 1:1) so the chart has more room to read, per Patrick's
  request that history "needs to be bigger to read the chart better."
- Clicking a device's row in the overview table now selects that
  device in the history/Analysis picker above, wired via NiceGUI's
  `ui.table`'s `rowClick` event - "(if possible)" in Patrick's
  wording; it was.
- A logo replacing the "BTBatteryLab" text label - Patrick sent
  `Vet1.svg` right after this round shipped, saved at
  `src/btbatterylab/ui/assets/Vet1.svg`. The header's logo lookup was
  originally hardcoded to a specific `logo.png` filename, which
  wouldn't have matched an `.svg` with a different name at all -
  caught before it could become a silent no-op, and generalized to
  `_find_logo()`: picks the first image file (any name, any of
  `.svg`/`.png`/`.jpg`/`.jpeg`/`.webp`/`.gif`) found in that directory,
  falling back to the bluetooth icon + text label only if it's empty.
  **Follow-up bug** (Patrick, after rebuilding the standalone `.exe`:
  "il logo non appare, propio nulla"): worked when run from source but
  not from the packaged build. Two compounding causes - (1)
  `btbatterylab.spec`'s `Analysis` had `datas=[]`, so PyInstaller,
  which only bundles Python modules it detects via import analysis,
  silently dropped the whole `assets/` folder (not Python code) from
  the frozen build; (2) even with that fixed, `app.py`'s own lookup
  located the assets directory via `Path(__file__).parent`, which is
  correct from source but no longer points at a real directory once
  this module is archived into the frozen build. **Fix**: the spec now
  bundles `src/btbatterylab/ui/assets/` explicitly, and `app.py` checks
  `sys._MEIPASS` (the directory PyInstaller actually extracts data
  files into) first, falling back to the `__file__`-relative path only
  for the normal, non-frozen case. Neither half is testable without a
  real PyInstaller build on Windows - the `sys._MEIPASS` path-joining
  logic was verified in isolation instead.
  **Second follow-up bug** (Patrick, after rebuilding again and testing
  both the `.exe` and `run.bat`: "niente logo... io non ho trovato
  nulla di sbagliato", with a full HTML dump of the running page
  attached): still no logo, on *both* methods this time. Patrick's HTML
  dump was the key piece of evidence - it showed NiceGUI had generated
  a perfectly valid static route for `Vet1.svg`
  (`/_nicegui/auto/static/<hash>/Vet1.svg`), proving the file *was*
  being found and served correctly, which ruled out both previous
  fixes as the cause and pointed somewhere new. **Root cause**:
  NiceGUI's own static-file serving (`add_static_file()` in
  `nicegui/app/app.py`) returns the file via Starlette's
  `FileResponse` without ever setting an explicit `media_type`, so the
  browser is told the file's Content-Type by Python's
  `mimetypes.guess_type()` - which, for `.svg` specifically, also
  consults the Windows registry (`HKEY_CLASSES_ROOT\.svg\Content
  Type`) on that platform. A missing or wrong entry there makes it
  return nothing, so the file gets served as
  `application/octet-stream` - a generic "download this" type that
  browsers won't render inline as an `<img>`, which looks exactly like
  "no logo at all" with no broken-image icon. **Fix**: the app now
  serves the logo from its own route (`/branding/logo`) with an
  explicit, hardcoded extension-to-MIME mapping
  (`.svg` -> `image/svg+xml`, etc.), bypassing the OS/registry
  dependency entirely; `ui.image()` points at that route instead of
  the raw file path.

**Bugs, all root-caused by reading the actual code before fixing**:

- **Offline device's battery badge colored by its last-known
  percentage**, which can misleadingly look like a live low-battery
  warning for a device that's actually just disconnected. **Fix**:
  `dashboard_data.device_row()` now forces the grey ("unknown") color
  whenever `status` is specifically `Offline`, regardless of the
  stored percentage - kept narrow (not applied to the separate
  `Unknown` status, which still needs percentage-based coloring per
  the existing, tested behavior) after checking the existing test
  suite first rather than after breaking it.
- **Drain rate / estimated runtime showing no data on the 1-hour/24-
  hour windows**, which is usually expected (too few readings yet in a
  short window to compute a rate) rather than a real bug, but gave no
  indication of *why* - Patrick's own suggested fix ("un messaggio che
  dice che più misurazioni daranno dati più certi"). **Fix**:
  `analysis_summary()` now returns a `needs_longer_window` flag (true
  when the window is `<= SHORT_WINDOW_DAYS_THRESHOLD` (1 day) *and*
  either value is missing) that the Analysis card uses to show a short
  explanatory hint instead of a bare "Not enough data"/"Unknown" - a
  long window (7/30/90 days) with genuinely no drain rate (e.g. a
  device that's never discharged) does *not* show the hint, since a
  longer window wouldn't add anything there.
- **PnP battery updates taking ~40s**, much slower than the BLE path,
  with Patrick's own hypothesis it might be a PowerShell cmdlet delay.
  Root cause, confirmed by reading `read_battery_levels()`'s embedded
  PowerShell: `Get-PnpDeviceProperty -InstanceId $_.InstanceId` with no
  `-KeyName` filter asks Windows for *every* property of the PnP node -
  a known slow pattern - before this code filters down to the three it
  actually wants (`DEVPKEY_Bluetooth_DeviceAddress` and the two
  vendor-specific battery keys) in memory afterwards. **Fix**: the
  query now passes `-KeyName` with exactly those three property keys,
  so PowerShell itself only fetches what's needed instead of
  everything. This can't be measured from this sandbox (no real PnP
  devices here) - Patrick's confirmation on real hardware will say
  whether it accounts for the full ~40s or only part of it.

**Also addressed, related to but not itself in Patrick's bug list**:
the Exit button "doesn't close the browser tab" is architecturally
unfixable (browsers only let a script close a tab it opened itself -
already true, and already explained in the round-above writeup and
the exit dialog's own text). What *was* fixable: what the tab shows
once the app really has exited. Previously `ui.run_javascript(...)`
was called without `await`, so the coroutine it returns was never
actually driven - the `window.close()` attempt likely never even
reached the browser before the process below exited. **Fix**: the
call is now awaited (with a short timeout, so a stuck or refused call
can't block shutdown - the hard `os._exit()` failsafe from the round
above is started first regardless), and besides trying
`window.close()`, it now also rewrites the whole page to a plain
"BTBatteryLab has closed - it's safe to close this tab now" message as
a fallback, so the tab shows a clear, deliberate end state instead of
a dead/disconnected-socket page once the server process actually ends.

**7 new/changed tests** across `test_dashboard_data.py` (offline-badge
coloring, the `needs_longer_window` flag across all four combinations
of window length and missing values) and `test_bluetooth_collector.py`
(the `-KeyName` filtering). No test for the header restyle, chart
empty-state wording, table/picker linkage, or the exit-page JavaScript
itself - `btbatterylab.ui.app` remains the one deliberately untested
layer (see [Automated tests](../README.md#automated-tests)), the same
gap as every round before this one; what's underneath it
(`dashboard_data`, `bluetooth_collector`) is what's actually covered.
**184 tests total, all passing.**

**Pending verification on real hardware** - written and unit-tested in
this same sandbox (no Windows machine, `nicegui`, or real Bluetooth
hardware available here, same situation as every previous round), not
yet confirmed by Patrick.

### Status

🟡 A second round of fixes from real-hardware testing feedback
(`Test.txt`, 2026-09-28 - see above), including Patrick's own logo, is
implemented and unit-tested but not yet confirmed on real hardware.
The first Test.txt round is confirmed working by Patrick (pushed,
`.exe` rebuilt). The 2026-09-19 round both build on
(live collector control panel, historical dashboard, Analysis card,
visual restyle, windowless `run.bat`/`BluetoothWatcher.exe`
architecture) remains verified and working. Standalone `.exe`
packaging (`build_exe.bat`) needs a rebuild to pick up this round's
changes too - see the possible-next-steps list in
`claude/project-status.md`.

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
