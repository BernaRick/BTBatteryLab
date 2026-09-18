"""
Tests for btbatterylab.collector.bluetooth_collector.

subprocess.run is mocked everywhere here: discover() and
read_battery_levels() both shell out to `powershell`, which doesn't
exist on Linux (or in this cloud sandbox at all) - mocking it is what
lets the JSON-parsing and multi-node-merge logic underneath be tested
without a real Windows machine, closing a real gap (this logic
previously had zero automated coverage and could only be checked by
Patrick on real hardware).
"""

import json
import subprocess
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from btbatterylab.collector.bluetooth_collector import (
    BATTERY_LEVEL_KEY,
    BATTERY_UPDATED_KEY,
    BluetoothCollector,
    extract_address,
)


class ExtractAddressTests(unittest.TestCase):
    def test_extracts_address_from_classic_instance_id(self) -> None:
        self.assertEqual(
            extract_address(r"BTHENUM\DEV_50C275770AE8\7&abc"), "50C275770AE8"
        )

    def test_extracts_address_from_ble_instance_id(self) -> None:
        self.assertEqual(
            extract_address(r"BTHLE\DEV_50c275770ae8\8&def"), "50C275770AE8"
        )

    def test_returns_none_when_no_address_present(self) -> None:
        self.assertIsNone(extract_address(r"USB\VID_1234&PID_5678"))

    def test_returns_none_for_none_input(self) -> None:
        self.assertIsNone(extract_address(None))


def _run_result(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=["powershell"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class DiscoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collector = BluetoothCollector()

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_parses_devices_and_extracts_address(self, mock_run) -> None:
        mock_run.return_value = _run_result(
            stdout=json.dumps(
                [
                    {
                        "FriendlyName": "MX Master 2S",
                        "Status": "OK",
                        "InstanceId": r"BTHLE\DEV_50C275770AE8\8",
                    }
                ]
            )
        )

        devices = self.collector.discover()

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].name, "MX Master 2S")
        self.assertEqual(devices[0].address, "50C275770AE8")

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_single_object_result_is_wrapped_in_a_list(self, mock_run) -> None:
        # PowerShell's ConvertTo-Json returns a bare object (not a
        # single-element array) when only one device matches.
        mock_run.return_value = _run_result(
            stdout=json.dumps(
                {
                    "FriendlyName": "Solo Device",
                    "Status": "OK",
                    "InstanceId": r"BTHENUM\DEV_112233445566\1",
                }
            )
        )

        devices = self.collector.discover()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].name, "Solo Device")

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_excluded_keywords_are_filtered_out(self, mock_run) -> None:
        mock_run.return_value = _run_result(
            stdout=json.dumps(
                [
                    {"FriendlyName": "Generic Attribute Service", "Status": "OK", "InstanceId": "X\\DEV_AAAAAAAAAAAA\\1"},
                    {"FriendlyName": "RFCOMM Protocol TDI", "Status": "OK", "InstanceId": "X\\DEV_BBBBBBBBBBBB\\1"},
                    {"FriendlyName": "Real Headset", "Status": "OK", "InstanceId": "X\\DEV_CCCCCCCCCCCC\\1"},
                ]
            )
        )

        devices = self.collector.discover()
        self.assertEqual([d.name for d in devices], ["Real Headset"])

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_devices_without_a_name_are_skipped(self, mock_run) -> None:
        mock_run.return_value = _run_result(
            stdout=json.dumps(
                [
                    {"FriendlyName": None, "Status": "OK", "InstanceId": "X\\DEV_AAAAAAAAAAAA\\1"},
                    {"FriendlyName": "Named Device", "Status": "OK", "InstanceId": "X\\DEV_BBBBBBBBBBBB\\1"},
                ]
            )
        )

        devices = self.collector.discover()
        self.assertEqual([d.name for d in devices], ["Named Device"])

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_duplicate_names_are_deduplicated(self, mock_run) -> None:
        mock_run.return_value = _run_result(
            stdout=json.dumps(
                [
                    {"FriendlyName": "Dup", "Status": "OK", "InstanceId": "X\\DEV_AAAAAAAAAAAA\\1"},
                    {"FriendlyName": "Dup", "Status": "OK", "InstanceId": "X\\DEV_BBBBBBBBBBBB\\1"},
                ]
            )
        )

        devices = self.collector.discover()
        self.assertEqual(len(devices), 1)

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_timeout_raises_runtime_error(self, mock_run) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="powershell", timeout=15)

        with self.assertRaises(RuntimeError):
            self.collector.discover()

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_nonzero_returncode_raises_runtime_error(self, mock_run) -> None:
        mock_run.return_value = _run_result(returncode=1, stderr="boom")

        with self.assertRaises(RuntimeError):
            self.collector.discover()


class ReadBatteryLevelsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collector = BluetoothCollector(pnp_timeout_seconds=45.0)

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_parses_single_reading(self, mock_run) -> None:
        updated = datetime(2026, 1, 1, 10, 0, 0)
        mock_run.return_value = _run_result(
            stdout=json.dumps(
                {
                    "FriendlyName": "OPPO Enco Air2",
                    "InstanceId": r"BTHENUM\DEV_AABBCCDDEEFF\1",
                    "Address": "AA:BB:CC:DD:EE:FF",
                    "BatteryLevel": "85",
                    "BatteryUpdated": updated.isoformat(),
                }
            )
        )

        readings = self.collector.read_battery_levels()

        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].device_id, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(readings[0].battery_percent, 85)
        self.assertEqual(readings[0].timestamp, updated)

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_null_result_means_no_readings(self, mock_run) -> None:
        # ForEach-Object emitting nothing serializes as the literal
        # string "null" via ConvertTo-Json, not an empty string.
        mock_run.return_value = _run_result(stdout="null")

        readings = self.collector.read_battery_levels()
        self.assertEqual(readings, [])

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_empty_stdout_means_no_readings(self, mock_run) -> None:
        mock_run.return_value = _run_result(stdout="")

        readings = self.collector.read_battery_levels()
        self.assertEqual(readings, [])

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_multi_node_merge_keeps_most_recent_timestamp(self, mock_run) -> None:
        older = datetime(2026, 1, 1, 8, 0, 0)
        newer = datetime(2026, 1, 1, 9, 30, 0)
        mock_run.return_value = _run_result(
            stdout=json.dumps(
                [
                    {
                        "FriendlyName": "Headset (node A)",
                        "InstanceId": r"BTHENUM\DEV_AABBCCDDEEFF\1",
                        "Address": "AA:BB:CC:DD:EE:FF",
                        "BatteryLevel": "40",
                        "BatteryUpdated": older.isoformat(),
                    },
                    {
                        "FriendlyName": "Headset (node B)",
                        "InstanceId": r"BTHENUM\DEV_AABBCCDDEEFF\2",
                        # Windows can report the address with different
                        # casing depending on the node.
                        "Address": "aa:bb:cc:dd:ee:ff",
                        "BatteryLevel": "55",
                        "BatteryUpdated": newer.isoformat(),
                    },
                ]
            )
        )

        readings = self.collector.read_battery_levels()

        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].device_id, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(readings[0].battery_percent, 55)
        self.assertEqual(readings[0].timestamp, newer)

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_missing_battery_level_is_skipped(self, mock_run) -> None:
        mock_run.return_value = _run_result(
            stdout=json.dumps(
                [
                    {
                        "FriendlyName": "No battery here",
                        "InstanceId": r"BTHENUM\DEV_AABBCCDDEEFF\1",
                        "Address": "AA:BB:CC:DD:EE:FF",
                        "BatteryLevel": None,
                        "BatteryUpdated": None,
                    }
                ]
            )
        )

        readings = self.collector.read_battery_levels()
        self.assertEqual(readings, [])

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_missing_address_falls_back_to_instance_id_as_device_id(self, mock_run) -> None:
        mock_run.return_value = _run_result(
            stdout=json.dumps(
                {
                    "FriendlyName": "No address property",
                    "InstanceId": r"BTHENUM\DEV_AABBCCDDEEFF\1",
                    "Address": None,
                    "BatteryLevel": "60",
                    "BatteryUpdated": None,
                }
            )
        )

        readings = self.collector.read_battery_levels()
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].device_id, r"BTHENUM\DEV_AABBCCDDEEFF\1")

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_missing_timestamp_falls_back_to_now(self, mock_run) -> None:
        before = datetime.now()
        mock_run.return_value = _run_result(
            stdout=json.dumps(
                {
                    "FriendlyName": "No timestamp",
                    "InstanceId": r"BTHENUM\DEV_AABBCCDDEEFF\1",
                    "Address": "AA:BB:CC:DD:EE:FF",
                    "BatteryLevel": "60",
                    "BatteryUpdated": None,
                }
            )
        )

        readings = self.collector.read_battery_levels()
        after = datetime.now()

        self.assertEqual(len(readings), 1)
        self.assertTrue(before <= readings[0].timestamp <= after)

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_timeout_message_mentions_the_configured_timeout(self, mock_run) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="powershell", timeout=45)

        with self.assertRaises(RuntimeError) as ctx:
            self.collector.read_battery_levels()
        self.assertIn("45", str(ctx.exception))
        self.assertIn("pnp_timeout_seconds", str(ctx.exception))

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_nonzero_returncode_raises_runtime_error(self, mock_run) -> None:
        mock_run.return_value = _run_result(returncode=1, stderr="powershell exploded")

        with self.assertRaises(RuntimeError):
            self.collector.read_battery_levels()

    @patch("btbatterylab.collector.bluetooth_collector.subprocess.run")
    def test_uses_configured_pnp_timeout_seconds(self, mock_run) -> None:
        mock_run.return_value = _run_result(stdout="null")

        self.collector.read_battery_levels()

        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["timeout"], 45.0)


if __name__ == "__main__":
    unittest.main()
