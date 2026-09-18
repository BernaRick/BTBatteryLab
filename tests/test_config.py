"""
Tests for btbatterylab.config.

No Windows dependency: _windows_documents_dir() returns None on any
non-Windows platform, so load_config() falls back to the data_dir
passed in explicitly (which is all these tests ever do) without
touching the registry lookup at all.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from btbatterylab.config import (
    DEFAULT_MIN_POLL_SPACING_SECONDS,
    DEFAULT_PNP_TIMEOUT_SECONDS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    Config,
    load_config,
)


class LoadConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data_dir = Path(tempfile.mkdtemp(prefix="btb_config_"))
        self.addCleanup(shutil.rmtree, self.data_dir, ignore_errors=True)

    def test_creates_config_file_with_defaults_on_first_run(self) -> None:
        config = load_config(self.data_dir)

        config_path = self.data_dir / "config.json"
        self.assertTrue(config_path.exists())

        written = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(written["poll_interval_seconds"], DEFAULT_POLL_INTERVAL_SECONDS)
        self.assertEqual(written["min_poll_spacing_seconds"], DEFAULT_MIN_POLL_SPACING_SECONDS)
        self.assertEqual(written["pnp_timeout_seconds"], DEFAULT_PNP_TIMEOUT_SECONDS)

        self.assertEqual(config.poll_interval_seconds, DEFAULT_POLL_INTERVAL_SECONDS)
        self.assertEqual(config.min_poll_spacing_seconds, DEFAULT_MIN_POLL_SPACING_SECONDS)
        self.assertEqual(config.pnp_timeout_seconds, DEFAULT_PNP_TIMEOUT_SECONDS)

    def test_reads_back_edited_values(self) -> None:
        load_config(self.data_dir)  # creates the file

        config_path = self.data_dir / "config.json"
        config_path.write_text(
            json.dumps({"poll_interval_seconds": 60, "min_poll_spacing_seconds": 5, "pnp_timeout_seconds": 30}),
            encoding="utf-8",
        )

        config = load_config(self.data_dir)
        self.assertEqual(config.poll_interval_seconds, 60.0)
        self.assertEqual(config.min_poll_spacing_seconds, 5.0)
        self.assertEqual(config.pnp_timeout_seconds, 30.0)

    def test_invalid_type_falls_back_to_default(self) -> None:
        config_path = self.data_dir / "config.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"poll_interval_seconds": "not a number"}), encoding="utf-8"
        )

        config = load_config(self.data_dir)
        self.assertEqual(config.poll_interval_seconds, DEFAULT_POLL_INTERVAL_SECONDS)

    def test_bool_is_rejected_even_though_it_is_an_int_subclass(self) -> None:
        # isinstance(True, int) is True in Python - the validator must
        # explicitly exclude bool or "poll_interval_seconds: true" in
        # config.json would silently become 1.0 instead of falling
        # back to the default.
        config_path = self.data_dir / "config.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"poll_interval_seconds": True}), encoding="utf-8"
        )

        config = load_config(self.data_dir)
        self.assertEqual(config.poll_interval_seconds, DEFAULT_POLL_INTERVAL_SECONDS)

    def test_corrupt_json_falls_back_to_defaults(self) -> None:
        config_path = self.data_dir / "config.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text("not json{{{", encoding="utf-8")

        config = load_config(self.data_dir)
        self.assertEqual(config.poll_interval_seconds, DEFAULT_POLL_INTERVAL_SECONDS)
        self.assertEqual(config.min_poll_spacing_seconds, DEFAULT_MIN_POLL_SPACING_SECONDS)
        self.assertEqual(config.pnp_timeout_seconds, DEFAULT_PNP_TIMEOUT_SECONDS)

    def test_non_dict_json_falls_back_to_defaults(self) -> None:
        config_path = self.data_dir / "config.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text("[1, 2, 3]", encoding="utf-8")

        config = load_config(self.data_dir)
        self.assertEqual(config.poll_interval_seconds, DEFAULT_POLL_INTERVAL_SECONDS)

    def test_missing_keys_fall_back_individually(self) -> None:
        config_path = self.data_dir / "config.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"poll_interval_seconds": 42}), encoding="utf-8")

        config = load_config(self.data_dir)
        self.assertEqual(config.poll_interval_seconds, 42.0)
        self.assertEqual(config.min_poll_spacing_seconds, DEFAULT_MIN_POLL_SPACING_SECONDS)
        self.assertEqual(config.pnp_timeout_seconds, DEFAULT_PNP_TIMEOUT_SECONDS)


class ConfigDerivedPathsTests(unittest.TestCase):
    def test_derived_paths(self) -> None:
        config = Config(data_dir=Path("/tmp/example-data-dir"))
        self.assertEqual(config.jsonl_path, Path("/tmp/example-data-dir/ble-events.jsonl"))
        self.assertEqual(config.db_path, Path("/tmp/example-data-dir/btbatterylab.db"))
        self.assertEqual(config.config_path, Path("/tmp/example-data-dir/config.json"))


if __name__ == "__main__":
    unittest.main()
