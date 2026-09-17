import time
from pathlib import Path
from threading import Event
from typing import Protocol


class JsonlConsumer(Protocol):
    def process_json_line(self, line: str) -> None: ...


class JsonlTailMonitor:
    """
    Follows a JSONL file in real time.

    When a new line is added, it forwards it to the consumer (any
    object with a process_json_line(line) method). It doesn't know or
    assume anything about the consumer's internal state: it's up to the
    consumer itself to decide whether/what to print or do with each
    processed line.
    """

    def __init__(
        self,
        path: str | Path,
        consumer: JsonlConsumer,
        poll_interval: float = 0.5
    ) -> None:

        self.path = Path(path)
        self.consumer = consumer
        self.poll_interval = poll_interval

        self._stop_event = Event()

    def stop(self) -> None:
        """
        Stops the monitor.
        """

        self._stop_event.set()

    def start(self) -> None:
        """
        Starts tailing the file.
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

            # Seek to the end of the file
            file.seek(0, 2)

            while not self._stop_event.is_set():

                line = file.readline()

                if not line:
                    time.sleep(self.poll_interval)
                    continue

                try:
                    self.consumer.process_json_line(line)

                except Exception as ex:
                    print(
                        f"[ERROR] "
                        f"Unable to process line: {ex}"
                    )
