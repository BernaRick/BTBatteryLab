import sqlite3
import threading
from datetime import datetime
from pathlib import Path


class SqliteStorage:
    """
    Persistenza locale in SQLite per lo storico di device e batteria.

    Due tabelle, come da docs/architecture.md:

    - devices: una riga per device (chiave = indirizzo Bluetooth), con
      il nome migliore conosciuto e la prima/ultima volta che ne
      abbiamo saputo qualcosa (presenza o batteria).
    - battery_log: una riga per ogni lettura di batteria osservata da
      uno dei due canali (ble/pnp) - storico grezzo, non filtrato dal
      "freshest wins" usato per la vista live in UnifiedCollector,
      cosi' da avere in futuro dati sufficienti per drain rate,
      runtime estimation, trend di degrado.

    Una connessione sola, condivisa, con lock interno: UnifiedCollector
    scrive da due thread diversi (tail JSONL sul thread principale,
    polling PnP su un thread in background).

    Gli errori SQLite vengono intercettati e stampati invece di far
    cadere il collector: la persistenza e' un side-effect utile ma non
    deve mai interrompere il monitoraggio live.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            self.db_path, check_same_thread=False
        )
        self._connection.execute("PRAGMA journal_mode=WAL;")
        self._connection.execute("PRAGMA foreign_keys=ON;")

        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    address TEXT PRIMARY KEY,
                    name TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                )
                """
            )

            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS battery_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    address TEXT NOT NULL REFERENCES devices(address),
                    timestamp TEXT NOT NULL,
                    battery_percent INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    UNIQUE(address, timestamp, source)
                )
                """
            )

            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_battery_log_address_ts
                ON battery_log(address, timestamp)
                """
            )

    @staticmethod
    def _format_timestamp(timestamp: datetime) -> str:
        return timestamp.isoformat(timespec="microseconds")

    def record_device_seen(
        self,
        address: str,
        name: str | None,
        timestamp: datetime,
    ) -> None:
        """
        Crea il device se non esiste (first_seen = last_seen = timestamp),
        altrimenti aggiorna il nome (se conosciuto) e sposta in avanti
        last_seen - mai indietro, nel caso arrivino eventi fuori ordine.
        """

        ts = self._format_timestamp(timestamp)

        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO devices (address, name, first_seen, last_seen)
                    VALUES (:address, :name, :ts, :ts)
                    ON CONFLICT(address) DO UPDATE SET
                        name = COALESCE(excluded.name, devices.name),
                        last_seen = MAX(devices.last_seen, excluded.last_seen)
                    """,
                    {"address": address, "name": name, "ts": ts},
                )
        except sqlite3.Error as ex:
            print(f"[SqliteStorage] Errore su record_device_seen: {ex}")

    def record_battery(
        self,
        address: str,
        battery_percent: int,
        timestamp: datetime,
        source: str,
    ) -> None:
        """
        Registra una lettura di batteria grezza. Duplicati esatti
        (stesso device, stesso timestamp, stessa fonte - tipico di un
        poll PnP che ritrova lo stesso BatteryUpdated di prima perche'
        il device non ha aggiornato la stima) vengono scartati in
        silenzio dal vincolo UNIQUE.
        """

        ts = self._format_timestamp(timestamp)

        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO battery_log
                        (address, timestamp, battery_percent, source)
                    VALUES (?, ?, ?, ?)
                    """,
                    (address, ts, battery_percent, source),
                )
        except sqlite3.Error as ex:
            print(f"[SqliteStorage] Errore su record_battery: {ex}")

    def close(self) -> None:
        with self._lock:
            self._connection.close()
