"""
Tests for btbatterylab.logging_setup.

configure_logging() mutates module-level state (the root logger's
handlers, and the module's own "already configured" flag) as a
deliberate side effect - that's the whole point of the function - so
every test here resets both in setUp/tearDown to avoid leaking
handlers into other tests (or other test files, if run in the same
process via `python -m unittest discover`).
"""

import logging
import logging.handlers
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import btbatterylab.logging_setup as logging_setup
from btbatterylab.logging_setup import LOG_FILENAME, LOG_SUBDIR, configure_logging


class ConfigureLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data_dir = Path(tempfile.mkdtemp(prefix="btb_logging_"))
        self.addCleanup(shutil.rmtree, self.data_dir, ignore_errors=True)

        # Snapshot and restore the root logger's handlers/level, and
        # the module's "already configured" flag, so this test suite
        # never leaks a handler (which would otherwise write to a
        # deleted temp directory, or duplicate log lines) into
        # whatever test runs next.
        self._root_logger = logging.getLogger()
        self._original_handlers = list(self._root_logger.handlers)
        self._original_level = self._root_logger.level
        self._original_configured_path = logging_setup._configured_path

        self.addCleanup(self._restore_logging_state)

        logging_setup._configured_path = None
        for handler in list(self._root_logger.handlers):
            self._root_logger.removeHandler(handler)

    def _restore_logging_state(self) -> None:
        # Close every handler this test installed before dropping the
        # reference - otherwise the underlying log file's descriptor
        # stays open for the life of the test process (a real problem
        # on Windows, where an open handle can block the next test's
        # tempdir cleanup or a rebuild, the same class of issue as the
        # OneDrive file-lock notes elsewhere in this project).
        for handler in list(self._root_logger.handlers):
            self._root_logger.removeHandler(handler)
            handler.close()
        for handler in self._original_handlers:
            self._root_logger.addHandler(handler)
        self._root_logger.setLevel(self._original_level)
        logging_setup._configured_path = self._original_configured_path

    def test_creates_log_directory_and_returns_expected_path(self) -> None:
        log_path = configure_logging(self.data_dir)

        self.assertEqual(log_path, self.data_dir / LOG_SUBDIR / LOG_FILENAME)
        self.assertTrue((self.data_dir / LOG_SUBDIR).is_dir())

    def test_records_reach_the_file_with_level_and_logger_name(self) -> None:
        log_path = configure_logging(self.data_dir)

        logger = logging.getLogger("btbatterylab.some.module")
        logger.info("hello info")
        logger.warning("hello warning")
        logger.error("hello error")

        for handler in self._root_logger.handlers:
            handler.flush()

        content = log_path.read_text(encoding="utf-8")
        self.assertIn("hello info", content)
        self.assertIn("hello warning", content)
        self.assertIn("hello error", content)
        self.assertIn("INFO", content)
        self.assertIn("WARNING", content)
        self.assertIn("ERROR", content)
        self.assertIn("btbatterylab.some.module", content)

    def test_debug_is_filtered_out_at_default_info_level(self) -> None:
        log_path = configure_logging(self.data_dir, level=logging.INFO)

        logger = logging.getLogger("btbatterylab.some.other.module")
        logger.debug("should not appear")

        for handler in self._root_logger.handlers:
            handler.flush()

        content = log_path.read_text(encoding="utf-8")
        self.assertNotIn("should not appear", content)

    def test_second_call_with_a_different_data_dir_is_a_no_op(self) -> None:
        """
        Regression test: an earlier version of configure_logging()
        computed its return value from the *current* call's data_dir
        even when it was a no-op, so a second call from a different
        location would claim logging was happening there when it
        never actually moved. The fix caches the real path from the
        first call and always returns that.
        """

        first_path = configure_logging(self.data_dir)

        other_dir = Path(tempfile.mkdtemp(prefix="btb_logging_other_"))
        self.addCleanup(shutil.rmtree, other_dir, ignore_errors=True)

        second_path = configure_logging(other_dir)

        self.assertEqual(second_path, first_path)
        self.assertFalse((other_dir / LOG_SUBDIR).exists())

    def test_second_call_does_not_duplicate_handlers(self) -> None:
        configure_logging(self.data_dir)
        handler_count_after_first = len(self._root_logger.handlers)

        configure_logging(self.data_dir)
        handler_count_after_second = len(self._root_logger.handlers)

        self.assertEqual(handler_count_after_first, handler_count_after_second)

    def test_no_console_handler_or_crash_when_stderr_is_none(self) -> None:
        """
        Regression test for running under pythonw.exe (see run.bat,
        which now starts the collector that way): sys.stderr is None
        there, and logging.StreamHandler() defaults to sys.stderr, so
        configure_logging() must skip adding a console handler
        instead of installing one backed by None - both the crash
        this would otherwise cause on the first log call and file
        logging still working are checked here.
        """

        with patch.object(logging_setup.sys, "stderr", None):
            log_path = configure_logging(self.data_dir)

            logger = logging.getLogger("btbatterylab.some.headless.module")
            logger.info("hello from a headless process")

        for handler in self._root_logger.handlers:
            handler.flush()

        self.assertEqual(len(self._root_logger.handlers), 1)
        self.assertIsInstance(
            self._root_logger.handlers[0], logging.handlers.RotatingFileHandler
        )
        self.assertIn(
            "hello from a headless process", log_path.read_text(encoding="utf-8")
        )


if __name__ == "__main__":
    unittest.main()
