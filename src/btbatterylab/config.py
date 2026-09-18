"""
Central configuration for BTBatteryLab's Python side.

The C# watcher (BluetoothWatcher/Program.cs) computes its own data
directory independently, via .NET's Environment.SpecialFolder.MyDocuments
- which resolves to the same registry value this module reads directly
below, so the two sides already agree without needing to share this
file.

Where things live, by default:

- Data directory: the real Windows "Documents" folder plus
  "BTBatteryLabData", resolved the same way Windows itself resolves
  it (via the registry key Explorer keeps up to date). This is
  correct even when Documents has been moved or redirected - e.g. by
  OneDrive, as on the developer's own machine
  ("OneDrive - <name>\\Documents" instead of the plain default path).
  This replaces what used to be a path hardcoded for one specific
  machine/user, which is what made the standalone build (and
  `python -m btbatterylab.main`/`.analytics`) only work correctly on
  that one machine.
- Config file: config.json inside that data directory. Created with
  the defaults below on first run if it doesn't exist yet, so it's
  easy to find and edit without reading the source. Only recognized
  keys are applied; anything else in the file (missing keys, unknown
  keys, keys of the wrong type) falls back to its default rather than
  crashing the collector - a bad or partial config file should never
  be the reason data collection doesn't start.

See config.example.json at the repo root for a documented copy of the
schema (that file itself is never read at runtime - it exists purely
as reference for anyone reading the repo, since the real config.json
lives in the data directory, not in the repo).

Note on logging: this module can be called before
btbatterylab.logging_setup.configure_logging() has run (main.py needs
the data directory this module resolves before it can point the
logging engine at it), so any warning logged here before that point
falls back to Python's default "handler of last resort" (printed to
stderr) rather than the rotating log file - still visible, just not
persisted. In practice this only affects a malformed config.json,
which is rare and already surfaced on the console either way.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "config.json"

# Defaults, also used as the fallback for any key missing, invalid, or
# of the wrong type in an existing config.json.
DEFAULT_POLL_INTERVAL_SECONDS = 300.0
DEFAULT_MIN_POLL_SPACING_SECONDS = 15.0
DEFAULT_PNP_TIMEOUT_SECONDS = 60.0


def _windows_documents_dir() -> Path | None:
    """
    Resolves the real Windows "Documents" folder via the same registry
    value Windows Explorer itself keeps up to date
    (...\\Explorer\\User Shell Folders\\Personal) - this is also what
    .NET's Environment.SpecialFolder.MyDocuments resolves to under the
    hood (see BluetoothWatcher/Program.cs), so both sides agree even
    when Documents has been moved or redirected.

    Returns None outside Windows, or if the lookup fails for any
    reason - callers fall back to a plain "~/Documents" in that case.
    """

    if sys.platform != "win32":
        return None

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer"
            r"\User Shell Folders",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "Personal")
    except OSError:
        return None

    return Path(os.path.expandvars(value))


def default_data_dir() -> Path:
    """The data folder used unless overridden: <Documents>/BTBatteryLabData."""

    documents = _windows_documents_dir() or (Path.home() / "Documents")
    return documents / "BTBatteryLabData"


@dataclass
class Config:
    data_dir: Path
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    min_poll_spacing_seconds: float = DEFAULT_MIN_POLL_SPACING_SECONDS
    pnp_timeout_seconds: float = DEFAULT_PNP_TIMEOUT_SECONDS

    @property
    def jsonl_path(self) -> Path:
        return self.data_dir / "ble-events.jsonl"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "btbatterylab.db"

    @property
    def config_path(self) -> Path:
        return self.data_dir / CONFIG_FILENAME


def _validated_float(raw: dict, key: str, default: float) -> float:
    value = raw.get(key, default)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    logger.warning(
        f'Ignoring invalid value for "{key}" in config.json '
        f"({value!r}), using the default ({default})."
    )
    return default


def load_config(data_dir: Path | str | None = None) -> Config:
    """
    Loads the configuration, creating config.json with the defaults in
    the data directory if it doesn't exist yet. A malformed or
    partially-filled file never prevents startup - invalid or missing
    keys just fall back to their default, with a warning logged for
    anything ignored.

    data_dir defaults to default_data_dir(); passing it explicitly is
    mainly useful for tests.
    """

    if data_dir is None:
        data_dir = default_data_dir()

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    config_path = data_dir / CONFIG_FILENAME

    if not config_path.exists():
        _write_defaults(config_path)
        return Config(data_dir=data_dir)

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON value must be an object")
    except (OSError, ValueError, json.JSONDecodeError) as ex:
        logger.warning(f"Could not read {config_path} ({ex}), using defaults instead.")
        return Config(data_dir=data_dir)

    return Config(
        data_dir=data_dir,
        poll_interval_seconds=_validated_float(
            raw, "poll_interval_seconds", DEFAULT_POLL_INTERVAL_SECONDS
        ),
        min_poll_spacing_seconds=_validated_float(
            raw, "min_poll_spacing_seconds", DEFAULT_MIN_POLL_SPACING_SECONDS
        ),
        pnp_timeout_seconds=_validated_float(
            raw, "pnp_timeout_seconds", DEFAULT_PNP_TIMEOUT_SECONDS
        ),
    )


def _write_defaults(config_path: Path) -> None:
    defaults = {
        "poll_interval_seconds": DEFAULT_POLL_INTERVAL_SECONDS,
        "min_poll_spacing_seconds": DEFAULT_MIN_POLL_SPACING_SECONDS,
        "pnp_timeout_seconds": DEFAULT_PNP_TIMEOUT_SECONDS,
    }
    try:
        config_path.write_text(
            json.dumps(defaults, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as ex:
        # Not being able to write the file (e.g. a read-only data
        # folder) is a minor inconvenience, not a reason to stop
        # startup - the defaults above still apply in memory either
        # way.
        logger.warning(f"Could not create {config_path} ({ex}), continuing with defaults.")
