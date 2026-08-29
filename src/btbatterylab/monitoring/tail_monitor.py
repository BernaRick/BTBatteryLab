import time
from pathlib import Path
from threading import Event

from btbatterylab.monitoring.ble_presence_monitor import (
    BlePresenceMonitor,
)


class JsonlTailMonitor:
    """
    Segue in tempo reale un file JSONL.

    Quando viene aggiunta una nuova riga,
    la inoltra al BlePresenceMonitor.
    """

    def __init__(
        self,
        path: str | Path,
        consumer: BlePresenceMonitor,
        poll_interval: float = 0.5
    ) -> None:

        self.path = Path(path)
        self.consumer = consumer
        self.poll_interval = poll_interval

        self._stop_event = Event()

    def stop(self) -> None:
        """
        Ferma il monitor.
        """

        self._stop_event.set()

    def start(self) -> None:
        """
        Avvia il tailing del file.
        """

        print(f"Waiting for file: {self.path}")

        while not self.path.exists():
            if self._stop_event.is_set():
                return

            time.sleep(self.poll_interval)

        print(f"Following: {self.path}")

        with self.path.open(
            mode="r",
            encoding="utf-8"
        ) as file:

            # Vai in fondo al file
            file.seek(0, 2)

            while not self._stop_event.is_set():

                line = file.readline()

                if not line:
                    time.sleep(self.poll_interval)
                    continue

                try:
                    self.consumer.process_json_line(line)

                    status = self.consumer.status

                    print(
                        f"[STATE] "
                        f"online={status.online} "
                        f"last_change={status.last_change}"
                    )

                except Exception as ex:
                    print(
                        f"[ERROR] "
                        f"Unable to process line: {ex}"
                    )