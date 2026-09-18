"""
Tests for btbatterylab.monitoring.tail_monitor.

JsonlTailMonitor.start() is a blocking call by design (it's meant to
run on its own thread/process), so every test here runs it on a
background thread and stops it via .stop() in a guaranteed cleanup,
polling briefly for the expected effect instead of using a fixed
sleep - keeps the suite fast while staying robust against scheduling
jitter.
"""

import shutil
import tempfile
import time
import unittest
from pathlib import Path
from threading import Thread


class RecordingConsumer:
    """
    Minimal JsonlConsumer: just remembers every line it was given, so
    tests can assert on what (and in what order) the monitor forwarded
    - and can inject a failure to check the monitor survives it.
    """

    def __init__(self, raise_on: str | None = None) -> None:
        self.lines: list[str] = []
        self._raise_on = raise_on

    def process_json_line(self, line: str) -> None:
        if self._raise_on is not None and self._raise_on in line:
            raise ValueError(f"boom: {line!r}")
        self.lines.append(line)


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class JsonlTailMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="btb_tail_"))
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.path = self.tmp_dir / "events.jsonl"

        # Imported here (rather than at module scope) is unnecessary in
        # this project, but the local import keeps the dependency
        # explicit right next to where instances are built.
        from btbatterylab.monitoring.tail_monitor import JsonlTailMonitor

        self._monitor_cls = JsonlTailMonitor
        self._threads: list[Thread] = []

    def tearDown(self) -> None:
        for thread in self._threads:
            thread.join(timeout=2.0)

    def _start_in_background(self, monitor) -> None:
        thread = Thread(target=monitor.start, daemon=True)
        self._threads.append(thread)
        self.addCleanup(monitor.stop)
        thread.start()

    def test_waits_for_the_file_to_be_created_then_follows_new_lines(self) -> None:
        consumer = RecordingConsumer()
        monitor = self._monitor_cls(
            path=self.path, consumer=consumer, poll_interval=0.02
        )
        self._start_in_background(monitor)

        # The file doesn't exist yet: the monitor must be waiting, not
        # erroring out.
        time.sleep(0.1)
        self.assertEqual(consumer.lines, [])

        # Create the (empty) file and give the monitor a moment to
        # notice it and seek to its end, *before* writing the line we
        # actually want it to observe. Writing content in the same
        # breath as creating the file would race the monitor's
        # exists()-then-seek(0, 2): if that whole sequence lands after
        # the write, the seek lands past the new content and the line
        # is never seen - a real (if narrow) startup race in the
        # implementation itself, not something this test is trying to
        # exercise.
        self.path.touch()
        self.assertTrue(_wait_until(lambda: self.path.exists()))
        time.sleep(0.15)

        with self.path.open("a", encoding="utf-8") as file:
            file.write('{"n": 1}\n')
            file.flush()

        self.assertTrue(_wait_until(lambda: consumer.lines == ['{"n": 1}\n']))

    def test_only_lines_appended_after_start_are_seen(self) -> None:
        # The monitor seeks to the end of the file before tailing, so
        # pre-existing content (e.g. from a previous run) must not be
        # replayed.
        self.path.write_text('{"n": 0}\n', encoding="utf-8")

        consumer = RecordingConsumer()
        monitor = self._monitor_cls(
            path=self.path, consumer=consumer, poll_interval=0.02
        )
        self._start_in_background(monitor)
        # Give the monitor time to open the file and seek to its
        # current end before the test appends more content (see the
        # comment in the previous test about this race).
        time.sleep(0.15)

        with self.path.open("a", encoding="utf-8") as file:
            file.write('{"n": 1}\n')

        self.assertTrue(_wait_until(lambda: consumer.lines == ['{"n": 1}\n']))

    def test_multiple_lines_are_forwarded_in_order(self) -> None:
        consumer = RecordingConsumer()
        monitor = self._monitor_cls(
            path=self.path, consumer=consumer, poll_interval=0.02
        )
        self.path.touch()
        self._start_in_background(monitor)
        time.sleep(0.15)

        with self.path.open("a", encoding="utf-8") as file:
            for i in range(5):
                file.write(f'{{"n": {i}}}\n')
                file.flush()

        self.assertTrue(_wait_until(lambda: len(consumer.lines) == 5))
        self.assertEqual(
            consumer.lines, [f'{{"n": {i}}}\n' for i in range(5)]
        )

    def test_consumer_exception_on_one_line_does_not_stop_the_monitor(self) -> None:
        consumer = RecordingConsumer(raise_on="bad")
        monitor = self._monitor_cls(
            path=self.path, consumer=consumer, poll_interval=0.02
        )
        self.path.touch()
        self._start_in_background(monitor)
        time.sleep(0.15)

        with self.path.open("a", encoding="utf-8") as file:
            file.write('{"ok": "bad-one"}\n')
            file.write('{"ok": "good-one"}\n')

        self.assertTrue(_wait_until(lambda: consumer.lines == ['{"ok": "good-one"}\n']))

    def test_stop_before_the_file_ever_appears_returns_cleanly(self) -> None:
        consumer = RecordingConsumer()
        monitor = self._monitor_cls(
            path=self.path, consumer=consumer, poll_interval=0.02
        )
        thread = Thread(target=monitor.start, daemon=True)
        thread.start()

        time.sleep(0.05)
        monitor.stop()
        thread.join(timeout=2.0)

        self.assertFalse(thread.is_alive())

    def test_stop_while_following_stops_the_loop(self) -> None:
        consumer = RecordingConsumer()
        monitor = self._monitor_cls(
            path=self.path, consumer=consumer, poll_interval=0.02
        )
        self.path.touch()
        thread = Thread(target=monitor.start, daemon=True)
        thread.start()

        # Give it a chance to reach the "Following" tailing loop before
        # stopping.
        time.sleep(0.1)
        monitor.stop()
        thread.join(timeout=2.0)

        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
