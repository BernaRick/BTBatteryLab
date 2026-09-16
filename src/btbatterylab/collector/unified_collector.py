import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from btbatterylab.collector.bluetooth_collector import BluetoothCollector
from btbatterylab.monitoring.tail_monitor import JsonlTailMonitor


def _is_generic_name(name: str | None) -> bool:
    """
    Il lato BLE del watcher a volte non conosce il nome vero di un
    device dual-mode e riporta solo "Bluetooth <mac>": non e' un
    nome utile, meglio tenerlo come ultima spiaggia.
    """

    return not name or name.lower().startswith("bluetooth ")


@dataclass
class DeviceState:
    """
    Vista corrente, per indirizzo Bluetooth, dello stato combinato dei
    due canali di raccolta. Non e' ancora persistita da nessuna parte
    (lo storage SQLite e' un passo successivo): per ora e' la fonte di
    verita' in memoria durante l'esecuzione di UnifiedCollector.
    """

    address: str
    name: str | None = None
    online: bool | None = None
    last_seen: datetime | None = None
    battery_percent: int | None = None
    battery_timestamp: datetime | None = None
    battery_source: str | None = None  # "ble" o "pnp"


class UnifiedCollector:
    """
    Combina i due canali di raccolta, complementari e non
    sovrapponibili, in un'unica vista per-device:

    - "ble": eventi push in tempo reale scritti da BluetoothWatcher
      (C#) su ble-events.jsonl. Copre presenza (online/offline) per
      ogni device BLE accoppiato, e batteria live per chi espone un
      GATT Battery Service (es. mouse, tastiere).

    - "pnp": polling periodico via PowerShell/PnP
      (BluetoothCollector.read_battery_levels()), l'unico modo oggi
      di leggere la batteria dei device classici (cuffie/auricolari)
      che non la espongono via BLE. Piu' lento (decine di secondi),
      per questo va a polling invece che in tempo reale.

    Quando entrambi i canali hanno un valore di batteria per lo
    stesso indirizzo, vince quello con il timestamp piu' recente -
    stesso principio gia' usato dentro read_battery_levels() per i
    device con piu' nodi PnP.
    """

    def __init__(
        self,
        jsonl_path: str | Path,
        poll_interval_seconds: float = 300.0,
        failure_retry_seconds: float = 30.0,
    ) -> None:

        self.poll_interval_seconds = poll_interval_seconds
        self.failure_retry_seconds = failure_retry_seconds

        self._collector = BluetoothCollector()
        self._states: dict[str, DeviceState] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._polling_thread: threading.Thread | None = None

        self._tail_monitor = JsonlTailMonitor(
            path=jsonl_path,
            consumer=self,
        )

    # --- interfaccia richiesta da JsonlTailMonitor (JsonlConsumer) ---

    def process_json_line(self, line: str) -> None:
        line = line.strip()

        if not line:
            return

        event = json.loads(line)

        self._handle_ble_event(event)

    # --- canale "ble" ---

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

            if battery_percent is not None:
                self._maybe_update_battery(
                    state, int(battery_percent), timestamp, source="ble"
                )

        self._print_state(address)

    # --- canale "pnp" ---

    def _poll_pnp_battery(self) -> bool:
        """
        Restituisce True se il polling e' andato a buon fine, False
        altrimenti (usato da _polling_loop per decidere se ritentare
        subito invece di aspettare l'intero poll_interval_seconds).
        """

        try:
            devices = self._collector.discover()
            readings = self._collector.read_battery_levels()
        except Exception as ex:
            print(f"[UnifiedCollector] Errore durante il polling PnP: {ex}")
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

                self._maybe_update_battery(
                    state,
                    reading.battery_percent,
                    reading.timestamp,
                    source="pnp",
                )

                updated_addresses.append(address)

        for address in updated_addresses:
            self._print_state(address)

        return True

    def _polling_loop(self) -> None:
        while not self._stop_event.is_set():
            success = self._poll_pnp_battery()

            wait_seconds = (
                self.poll_interval_seconds
                if success
                else self.failure_retry_seconds
            )

            self._stop_event.wait(wait_seconds)

    # --- helper condivisi ---

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

    def _print_state(self, address: str) -> None:
        with self._lock:
            state = self._states.get(address)

        if state is None:
            return

        if state.battery_percent is not None:
            battery = f"{state.battery_percent}% (fonte: {state.battery_source})"
        else:
            battery = "n/d"

        if state.online is True:
            online = "online"
        elif state.online is False:
            online = "offline"
        else:
            online = "?"

        print(
            f"[{datetime.now():%H:%M:%S}] "
            f"{state.name or address} [{address}]: "
            f"{online}, batteria {battery}"
        )

    # --- ciclo di vita ---

    def snapshot(self) -> dict[str, DeviceState]:
        """
        Copia dello stato corrente di ogni device conosciuto finora.
        """

        with self._lock:
            return dict(self._states)

    def start(self) -> None:
        """
        Avvia entrambi i canali. Chiamata bloccante (segue il file
        JSONL sul thread corrente) finche' non si chiama stop() da
        un altro thread o non arriva un KeyboardInterrupt.
        """

        self._polling_thread = threading.Thread(
            target=self._polling_loop,
            daemon=True,
        )
        self._polling_thread.start()

        self._tail_monitor.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._tail_monitor.stop()
