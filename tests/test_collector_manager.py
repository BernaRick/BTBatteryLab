"""
Tests for btbatterylab.ui.collector_manager.CollectorManager.

CollectorManager deliberately has no dependency on nicegui (see its
own docstring), so these tests use a fake UnifiedCollector-shaped
object instead of the real one - a real UnifiedCollector needs a real
JSONL file to follow, which is exactly the kind of environment
dependency this class exists to sit in front of.
"""

import threading
import time
import unittest

from btbatterylab.ui.collector_manager import (
    STATUS_ERROR,
    STATUS_RUNNING,
    STATUS_STOPPED,
    CollectorManager,
)


class _FakeCollector:
    """
    Stands in for UnifiedCollector: start() blocks until stop() is
    called from another thread, exactly like the real one following a
    JSONL file until its stop Event is set - except instantaneous and
    with no filesystem involved.
    """

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.started = threading.Event()
        self._stop_event = threading.Event()
        self.stop_called = False

    def start(self) -> None:
        self.started.set()

        if self.fail:
            raise RuntimeError("boom")

        self._stop_event.wait()

    def stop(self) -> None:
        self.stop_called = True
        self._stop_event.set()

    def snapshot(self) -> dict:
        return {"AA:BB": "fake-state"}


class CollectorManagerTests(unittest.TestCase):
    def _wait_for_status(self, manager: CollectorManager, status: str, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if manager.status == status:
                return
            time.sleep(0.01)
        self.fail(f"status never became {status!r} (still {manager.status!r})")

    def test_starts_stopped(self) -> None:
        manager = CollectorManager(collector_factory=_FakeCollector)
        self.assertEqual(manager.status, STATUS_STOPPED)
        self.assertIsNone(manager.error_message)

    def test_start_runs_collector_on_a_background_thread(self) -> None:
        collectors: list[_FakeCollector] = []

        def factory() -> _FakeCollector:
            collector = _FakeCollector()
            collectors.append(collector)
            return collector

        manager = CollectorManager(collector_factory=factory)
        manager.start()

        self.assertTrue(collectors[0].started.wait(timeout=2.0))
        self.assertEqual(manager.status, STATUS_RUNNING)

        manager.stop()

    def test_start_is_a_no_op_when_already_running(self) -> None:
        collectors: list[_FakeCollector] = []

        def factory() -> _FakeCollector:
            collector = _FakeCollector()
            collectors.append(collector)
            return collector

        manager = CollectorManager(collector_factory=factory)
        manager.start()
        collectors[0].started.wait(timeout=2.0)

        manager.start()  # should not build a second collector

        self.assertEqual(len(collectors), 1)

        manager.stop()

    def test_stop_transitions_back_to_stopped_and_calls_collector_stop(self) -> None:
        collector = _FakeCollector()
        manager = CollectorManager(collector_factory=lambda: collector)

        manager.start()
        collector.started.wait(timeout=2.0)

        manager.stop()

        self.assertEqual(manager.status, STATUS_STOPPED)
        self.assertTrue(collector.stop_called)

    def test_stop_when_not_running_is_a_no_op(self) -> None:
        manager = CollectorManager(collector_factory=_FakeCollector)
        manager.stop()  # must not raise
        self.assertEqual(manager.status, STATUS_STOPPED)

    def test_background_exception_sets_error_status(self) -> None:
        manager = CollectorManager(collector_factory=lambda: _FakeCollector(fail=True))
        manager.start()

        self._wait_for_status(manager, STATUS_ERROR)
        self.assertIn("boom", manager.error_message)

    def test_stop_after_error_clears_it(self) -> None:
        manager = CollectorManager(collector_factory=lambda: _FakeCollector(fail=True))
        manager.start()
        self._wait_for_status(manager, STATUS_ERROR)

        manager.stop()

        self.assertEqual(manager.status, STATUS_STOPPED)
        self.assertIsNone(manager.error_message)

    def test_start_after_error_builds_a_fresh_collector(self) -> None:
        collectors: list[_FakeCollector] = []

        def factory() -> _FakeCollector:
            # First one fails, second one behaves.
            collector = _FakeCollector(fail=len(collectors) == 0)
            collectors.append(collector)
            return collector

        manager = CollectorManager(collector_factory=factory)
        manager.start()
        self._wait_for_status(manager, STATUS_ERROR)

        manager.stop()
        manager.start()

        collectors[1].started.wait(timeout=2.0)
        self.assertEqual(manager.status, STATUS_RUNNING)
        self.assertEqual(len(collectors), 2)

        manager.stop()

    def test_snapshot_is_empty_when_stopped(self) -> None:
        manager = CollectorManager(collector_factory=_FakeCollector)
        self.assertEqual(manager.snapshot(), {})

    def test_snapshot_delegates_to_collector_when_running(self) -> None:
        collector = _FakeCollector()
        manager = CollectorManager(collector_factory=lambda: collector)
        manager.start()
        collector.started.wait(timeout=2.0)

        self.assertEqual(manager.snapshot(), {"AA:BB": "fake-state"})

        manager.stop()


if __name__ == "__main__":
    unittest.main()
