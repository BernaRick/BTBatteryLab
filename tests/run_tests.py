"""
Friendly console runner for BTBatteryLab's automated test suite.

Plain `python -m unittest discover -s tests` works fine and stays the
documented fallback, but its raw output has two things that make it
hard to read at a glance - especially for someone running this to
check whether their own setup is healthy, not to develop the project:

- Several tests deliberately exercise an error/warning code path (a
  corrupt config.json, a failed SQLite write, a consumer exception in
  the JSONL tail loop) and that path logs or prints something as part
  of doing its job correctly. Interleaved with unittest's own
  pass/fail output, those expected messages read like something
  crashed, even when every test passed - real confusion this caused,
  more than once, when the raw output was shared for troubleshooting.
- Plain text gives no visual shortcut for "this one failed" versus
  "this one didn't".

This script is unittest's own discovery and reporting, wrapped with:

- Buffered output (unittest's own `buffer=True`): a passing test's
  printed/logged output is discarded, and a failing test's is shown
  in full, attached to its failure. The "boom"/"Unable to process
  line" messages mentioned above are exactly that kind of deliberate,
  expected output - now hidden unless something is actually wrong.
- A colored PASS/FAIL/ERROR/SKIP label per test, and a colored
  one-line summary at the end - automatically turned off when the
  output isn't a real terminal (e.g. redirected to a file to paste
  into a bug report), so a shared log always stays plain, readable
  text with no stray escape codes.
- A breakdown by area (Configuration, Bluetooth device discovery,
  Battery analytics, ...) right before that summary, so a user
  scanning the end of a long run can see at a glance which part of
  the project - if any - has a problem, without reading all the
  individual test lines above it.

Deliberately not a custom framework, and no third-party dependency:
this is entirely the standard library's own `unittest`, just
configured and wrapped a bit more thoughtfully - it runs anywhere
Python does, with nothing extra to install.

Usage:
    python tests/run_tests.py

(or double-click test.bat at the repository root, which runs this
with the project's own virtual environment)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Friendly display name per test module, keyed the way
# TestCase.__module__ reports it once unittest's discovery has
# imported it as part of the "tests" package. Anything not listed here
# (e.g. a new test file) still gets a reasonable label from
# _area_label()'s fallback below - this mapping only makes the common
# case read nicely.
_AREA_LABELS = {
    "tests.test_config": "Configuration",
    "tests.test_logging_setup": "Logging setup",
    "tests.test_bluetooth_collector": "Bluetooth device discovery",
    "tests.test_unified_collector": "Unified data collector",
    "tests.test_tail_monitor": "Live event monitoring",
    "tests.test_sqlite_storage": "Database storage",
    "tests.test_analytics": "Battery analytics",
    "tests.test_export": "CSV export",
}


def _area_label(module_name: str) -> str:
    if module_name in _AREA_LABELS:
        return _AREA_LABELS[module_name]

    # Fallback for a test module not in the mapping above (most likely
    # a new one added later): "tests.test_something" -> "Something".
    short_name = module_name.rsplit(".", 1)[-1]
    if short_name.startswith("test_"):
        short_name = short_name[len("test_") :]
    return short_name.replace("_", " ").capitalize()


class _Color:
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def _colors_enabled() -> bool:
    """
    Only color a real terminal, never piped or redirected output - if
    this is being saved to a file to paste elsewhere (as has happened
    more than once), the ANSI escape codes would just show up as
    garbage instead of color.
    """

    return sys.stdout.isatty()


def _enable_windows_ansi() -> None:
    """
    Older Windows consoles (plain cmd.exe/conhost, without a recent
    Windows Terminal) don't interpret ANSI escape codes unless virtual
    terminal processing is turned on explicitly. A no-op everywhere
    else, and never fatal if it fails for any reason - at worst, the
    output just isn't colored.
    """

    if sys.platform != "win32":
        return

    try:
        import ctypes

        STD_OUTPUT_HANDLE = -11
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = ctypes.c_uint32()

        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(
                handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            )
    except Exception:
        # Best-effort only - a console that can't be switched into
        # ANSI mode just gets plain, uncolored (but still buffered)
        # output instead.
        pass


def _label(text: str, color: str) -> str:
    if not _colors_enabled():
        return text
    return f"{color}{text}{_Color.RESET}"


class FriendlyTestResult(unittest.TextTestResult):
    """
    Same per-test reporting as unittest's own verbose TextTestResult
    (one line per test: its name, then the outcome), just with a
    colored PASS/FAIL/ERROR/SKIP label instead of a bare word, so a
    glance down the output shows exactly which tests - if any - need
    attention.

    Also tallies each outcome by area (see _area_label()) as tests
    run, so the final summary can show a breakdown - "which part of
    the project got checked, and is it okay" - without a second pass
    over the results.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Insertion order follows discovery order, which is good
        # enough here - this is a summary, not a report that needs a
        # particular sort.
        self.area_stats: dict[str, dict[str, int]] = {}

    def _tally(self, test: unittest.case.TestCase, outcome: str) -> None:
        area = _area_label(test.__class__.__module__)
        stats = self.area_stats.setdefault(
            area, {"pass": 0, "fail": 0, "error": 0, "skip": 0}
        )
        stats[outcome] += 1

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        unittest.TestResult.addSuccess(self, test)
        self._tally(test, "pass")
        if self.showAll:
            self.stream.writeln(_label("PASS", _Color.GREEN))
        elif self.dots:
            self.stream.write(_label(".", _Color.GREEN))
            self.stream.flush()

    def addError(self, test: unittest.case.TestCase, err) -> None:
        unittest.TestResult.addError(self, test, err)
        self._tally(test, "error")
        if self.showAll:
            self.stream.writeln(_label("ERROR", _Color.RED))
        elif self.dots:
            self.stream.write(_label("E", _Color.RED))
            self.stream.flush()

    def addFailure(self, test: unittest.case.TestCase, err) -> None:
        unittest.TestResult.addFailure(self, test, err)
        self._tally(test, "fail")
        if self.showAll:
            self.stream.writeln(_label("FAIL", _Color.RED))
        elif self.dots:
            self.stream.write(_label("F", _Color.RED))
            self.stream.flush()

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        unittest.TestResult.addSkip(self, test, reason)
        self._tally(test, "skip")
        if self.showAll:
            self.stream.writeln(_label(f"SKIP ({reason})", _Color.YELLOW))
        elif self.dots:
            self.stream.write(_label("s", _Color.YELLOW))
            self.stream.flush()


def _print_banner(tag: str, message: str, color: str) -> None:
    line = "=" * 70
    print()
    print(_label(line, color))
    print(_label(f"{tag}: {message}", color + _Color.BOLD))
    print(_label(line, color))


def _print_area_breakdown(area_stats: dict[str, dict[str, int]]) -> None:
    """
    One line per area: what was checked, and whether it's okay - the
    "things checked and their status" recap, so a problem area stands
    out without reading every individual test line above it.
    """

    if not area_stats:
        return

    print()
    print(_label("Areas checked:", _Color.BOLD))

    name_width = max(len(area) for area in area_stats)
    for area, stats in area_stats.items():
        total = stats["pass"] + stats["fail"] + stats["error"] + stats["skip"]
        problems = stats["fail"] + stats["error"]

        if problems:
            status = _label(
                f"{stats['pass']}/{total} passed - {problems} problem(s)", _Color.RED
            )
        elif stats["skip"]:
            status = _label(
                f"{stats['pass']}/{total} passed ({stats['skip']} skipped)",
                _Color.YELLOW,
            )
        else:
            status = _label(f"{total}/{total} passed", _Color.GREEN)

        print(f"  {area:<{name_width}}  {status}")


def _print_summary(result: unittest.TestResult) -> None:
    _print_area_breakdown(getattr(result, "area_stats", {}))

    failed = len(result.failures)
    errored = len(result.errors)

    if result.wasSuccessful():
        message = f"all {result.testsRun} tests passed"
        if result.skipped:
            message += f" ({len(result.skipped)} skipped)"
        _print_banner("OK", message, _Color.GREEN)
        return

    parts = []
    if failed:
        parts.append(f"{failed} failed")
    if errored:
        parts.append(f"{errored} errored")
    message = f"{', '.join(parts)} out of {result.testsRun} tests - see details above"
    _print_banner("FAILED", message, _Color.RED)


def main() -> int:
    _enable_windows_ansi()

    # Defensive fallback: on a machine where the package isn't
    # installed into the active environment (`pip install -e .`),
    # this still finds it. A no-op when it's already importable, since
    # this is inserted after any existing entries.
    sys.path.append(str(REPO_ROOT / "src"))

    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir=str(REPO_ROOT / "tests"), top_level_dir=str(REPO_ROOT)
    )

    runner = unittest.TextTestRunner(
        verbosity=2,
        buffer=True,
        resultclass=FriendlyTestResult,
    )
    result = runner.run(suite)

    _print_summary(result)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
