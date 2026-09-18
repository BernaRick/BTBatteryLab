import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from btbatterylab.collector.bluetooth_collector import BluetoothCollector
from btbatterylab.monitoring.tail_monitor import JsonlTailMonitor
from btbatterylab.storage.sqlite_storage import SqliteStorage

logger = logging.getLogger(__name__)

# Default minimum spacing between a PnP poll "woken up" by a connection
# event and the next one, so that several classic devices connecting
# almost together (e.g. turning on multiple headsets in a row) don't
# each trigger their own PowerShell poll. Overridable per-instance via
# UnifiedCollector's min_poll_spacing_seconds parameter (see
# btbatterylab.config for where that value normally comes from).
DEFAULT_MIN_POLL_SPACING_SECONDS = 15.0


def _is_generic_name(name: str | None) -> bool:
    """
    The BLE side of the watcher sometimes doesn't know the real name of
    a dual-mode device and only reports "Bluetooth <mac>": not a useful
    name, better kept as a last resort.
    """

    return not name or name.lower().startswith("bluetooth ")


@dataclass
class DeviceState:
    """
    Current view, per Bluetooth address, of the combined state of the
    two collection channels - the in-memory source of truth while
    UnifiedCollector runs, used for the console output.

    Every observed battery reading (not only the one that "wins" in
    this view) still gets recorded to SQLite via SqliteStorage - see
    _handle_ble_event/_poll_pnp_battery.
    """

    address: str
    name: str | None = None
    online: bool | None = None
    last_seen: datetime | None = None
    battery_percent: int | None = None
    battery_timestamp: datetime | None = None
    battery_source: str | None = None  # "ble" or "pnp"


class UnifiedCollector:
    """
    Combines the two collection channels, complementary and
    non-overlapping, into a single per-device view:

    - "ble": real-time push events written by BluetoothWatcher (C#) to
      ble-events.jsonl. Covers presence (online/offline) for every
      paired BLE device, and live battery for whichever ones expose a
      GATT Battery Service (e.g. mice, keyboards).

    - "pnp": periodic polling via PowerShell/PnP
      (BluetoothCollector.read_battery_levels()), currently the only
      way to read the battery of classic devices (earbuds/headsets)
      that don't expose it over BLE. Slower (tens of seconds), which is
      why it's polled instead of real-time.

    When both channels have a battery value for the same address, the
    one with the most recent timestamp wins - the same principle
    already used inside read_battery_levels() for devices with
    multiple PnP nodes.
    """

    def __init__(
        self,
        jsonl_path: str | Path,
        poll_interval_seconds: float = 300.0,
        failure_retry_seconds: float = 30.0,
        db_path: str | Path | None = None,
        min_poll_spacing_seconds: float = DEFAULT_MIN_POLL_SPACING_SECONDS,
        pnp_timeout_seconds: float = 60.0,
    ) -> None:

        self.poll_interval_seconds = poll_interval_seconds
        self.failure_retry_seconds = failure_retry_seconds
        self.min_poll_spacing_seconds = min_poll_spacing_seconds

        # Default: the same place as the JSONL, so there's no need to
        # configure two separate paths (see btbatterylab.config, which
        # is what actually resolves both from a single data directory
        # in normal use).
        if db_path is None:
            db_path = Path(jsonl_path).with_name("btbatterylab.db")

        self._collector = BluetoothCollector(
            pnp_timeout_seconds=pnp_timeout_seconds
        )
        self._storage = SqliteStorage(db_path)
        self._states: dict[str, DeviceState] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._poll_now_event = threading.Event()
        self._last_poll_time: float | None = None
        self._polling_thread: threading.Thread | None = None

        self._tail_monitor = JsonlTailMonitor(
            path=jsonl_path,
            consumer=self,
        )

    # --- interface required by JsonlTailMonitor (JsonlConsumer) ---

    def process_json_line(self, line: str) -> None:
        line = line.strip()

        if not line:
            return

        event = json.loads(line)

        self._handle_ble_event(event)

    # --- "ble" channel ---

    def _handle_ble_event(self, event: dict) -> None:
        event_type = event.get("Event")

        if event_type not in ("Startup", "ConnectionStatusChanged"):
            return

        address = event.get("BluetoothAddress")

        if not address:
            return

        address = address.upper()

        status = event.get("Status")
        online = None

        if status == "Connected":
            online = True
        elif status == "Disconnected":
            online = False

        name = event.get("DeviceName")
        battery_percent = event.get("BatteryPercent")
        timestamp = self._parse_timestamp(event.get("Timestamp")) or datetime.now()

        with self._lock:
            state = self._states.setdefault(
                address, DeviceState(address=address)
            )

            if online is not None:
                state.online = online

            state.last_seen = timestamp
            self._maybe_update_name(state, name)

            self._storage.record_device_seen(address, state.name, timestamp)

            if battery_percent is not None:
                battery_percent = int(battery_percent)

                self._maybe_update_battery(
                    state, battery_percent, timestamp, source="ble"
                )

                self._storage.record_battery(
                    address, battery_percent, timestamp, source="ble"
                )

        self._log_state(address)

        # Classic devices (BR/EDR, e.g. headsets without a BLE
        # interface) can't report battery from this channel: their
        # "Connected" event always arrives with BatteryPercent=null.
        # Instead of waiting up to poll_interval_seconds to find out
        # the battery, we trigger a PnP poll right away. Harmless even
        # for a BLE device without a Battery Service: worst case it's
        # one extra PnP poll, capped by the minimum spacing in
        # _wait_for_next_poll.
        if online is True and battery_percent is None:
            self._poll_now_event.set()

    # --- "pnp" channel ---

    def _poll_pnp_battery(self) -> bool:
        """
        Returns True if the poll succeeded, False otherwise (used by
        _polling_loop to decide whether to retry right away instead of
        waiting the full poll_interval_seconds).
        """

        try:
            devices = self._collector.discover()
            readings = self._collector.read_battery_levels()
        except Exception as ex:
            logger.error(f"Error during PnP polling: {ex}")
            return False

        names_by_address = {
            device.address: device.name
            for device in devices
            if device.address
        }

        updated_addresses: list[str] = []

        with self._lock:
            for reading in readings:
                address = reading.device_id.upper()

                state = self._states.setdefault(
                    address, DeviceState(address=address)
                )

                self._maybe_update_name(
                    state, names_by_address.get(address)
                )

                self._storage.record_device_seen(
                    address, state.name, reading.timestamp
                )

                self._maybe_update_battery(
                    state,
                    reading.battery_percent,
                    reading.timestamp,
                    source="pnp",
                )

                self._storage.record_battery(
                    address,
                    reading.battery_percent,
                    reading.timestamp,
                    source="pnp",
                )

                updated_addresses.append(address)

        for address in updated_addresses:
            self._log_state(address)

        return True

    def _polling_loop(self) -> None:
        while not self._stop_event.is_set():
            success = self._poll_pnp_battery()
            self._last_poll_time = time.monotonic()

            wait_seconds = (
                self.poll_interval_seconds
                if success
                else self.failure_retry_seconds
            )

            self._wait_for_next_poll(wait_seconds)

    def _wait_for_next_poll(self, wait_seconds: float) -> None:
        """
        Waits until the next scheduled poll, but wakes up early if a
        connection event without battery arrives (see
        _handle_ble_event) - provided at least
        self.min_poll_spacing_seconds has passed since the last poll,
        so we don't hammer PowerShell when several devices connect
        almost together.
        """

        deadline = time.monotonic() + wait_seconds

        while not self._stop_event.is_set():
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                return

            triggered = self._poll_now_event.wait(min(remaining, 1.0))

            if not triggered:
                continue

            self._poll_now_event.clear()

            since_last_poll = (
                time.monotonic() - self._last_poll_time
                if self._last_poll_time is not None
                else self.min_poll_spacing_seconds
            )

            if since_last_poll >= self.min_poll_spacing_seconds:
                return  # returns right away: _polling_loop will poll now

            # Too soon since the last poll: ignore this trigger and
            # keep waiting out the rest of the scheduled time (or a
            # later trigger).

    # --- shared helpers ---

    @staticmethod
    def _parse_timestamp(raw: str | None) -> datetime | None:
        if not raw:
            return None

        try:
            normalized = raw.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)

            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)

            return parsed
        except ValueError:
            return None

    @staticmethod
    def _maybe_update_name(state: DeviceState, candidate: str | None) -> None:
        if not candidate:
            return

        if state.name is None or (
            _is_generic_name(state.name) and not _is_generic_name(candidate)
        ):
            state.name = candidate

    @staticmethod
    def _maybe_update_battery(
        state: DeviceState,
        battery_percent: int,
        timestamp: datetime,
        source: str,
    ) -> None:
        if (
            state.battery_timestamp is None
            or timestamp > state.battery_timestamp
        ):
            state.battery_percent = battery_percent
            state.battery_timestamp = timestamp
            state.battery_source = source

    def _log_state(self, address: str) -> None:
        with self._lock:
            state = self._states.get(address)

        if state is None:
            return

        if state.battery_percent is not None:
            battery = f"{state.battery_percent}% (source: {state.battery_source})"
        else:
            battery = "n/a"

        if state.online is True:
            online = "online"
        elif state.online is False:
            online = "offline"
        else:
            online = "?"

        logger.info(
            f"{state.name or address} [{address}]: {online}, battery {battery}"
        )

    # --- lifecycle ---

    def snapshot(self) -> dict[str, DeviceState]:
        """
        Copy of the current state of every device known so far.
        """

        with self._lock:
            return dict(self._states)

    def start(self) -> None:
        """
        Starts both channels. Blocking call (follows the JSONL file on
        the current thread) until stop() is called from another thread
        or a KeyboardInterrupt arrives.
        """

        # The JSONL file is already shown by JsonlTailMonitor ("Waiting
        # for file"/"Following"), but the database isn't - without this
        # line, the only way to know where SqliteStorage is writing is
        # to read the code.
        logger.info(f"Database: {self._storage.db_path}")

        self._polling_thread = threading.Thread(
            target=self._polling_loop,
            daemon=True,
        )
        self._polling_thread.start()

        self._tail_monitor.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._tail_monitor.stop()
        self._storage.close()
