"""
Command-line report for the analytics in battery_analytics.py.

Usage:
    python -m btbatterylab.analytics
    python -m btbatterylab.analytics --days 7 --device "MX Master"
    python -m btbatterylab.analytics --db path\to\btbatterylab.db
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from btbatterylab.analytics.battery_analytics import (
    DEFAULT_WINDOW_DAYS,
    DeviceReport,
    build_all_reports,
    format_hours,
)
from btbatterylab.config import load_config


def _parse_args(default_db_path: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Battery analytics (drain rate, estimated runtime, charge "
            "sessions) computed from the raw history in battery_log."
        )
    )
    parser.add_argument(
        "--db",
        default=str(default_db_path),
        help="Path to btbatterylab.db (default: the standard data folder).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help=f"Time window in days to analyze (default: {DEFAULT_WINDOW_DAYS}).",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Only show devices whose name or address contains this text.",
    )
    return parser.parse_args()


def _print_report(report: DeviceReport) -> None:
    label = report.name or report.address

    print(f"\n=== {label} ({report.address}) ===")

    if report.reading_count == 0:
        print(f"  No battery readings in the last {report.window_days} days.")
        return

    print(
        f"  Readings: {report.reading_count}  "
        f"(min {report.min_percent}%, max {report.max_percent}%, "
        f"avg {report.avg_percent:.0f}%)"
    )
    print(
        f"  Last known: {report.last_percent}% "
        f"at {report.last_timestamp:%Y-%m-%d %H:%M} "
        f"(source: {report.last_source})"
    )

    if report.drain_rate_percent_per_hour is not None:
        session_word = (
            "session"
            if report.discharge_session_count == 1
            else "sessions"
        )
        print(
            f"  Drain rate: {report.drain_rate_percent_per_hour:.1f}%/h "
            f"(from {report.discharge_session_count} discharge {session_word})"
        )
    else:
        print("  Drain rate: not enough data (no discharge observed yet).")

    if report.estimated_runtime_hours is not None:
        print(
            "  Estimated runtime at that pace: "
            f"~{format_hours(report.estimated_runtime_hours)} "
            "(projection from past behavior, not a live countdown)"
        )

    if report.charge_sessions:
        print(f"  Charge sessions: {len(report.charge_sessions)}")
        for session in report.charge_sessions[-3:]:
            print(
                f"    {session.start_time:%Y-%m-%d %H:%M} -> "
                f"{session.end_time:%Y-%m-%d %H:%M}: "
                f"{session.start_percent}% -> {session.end_percent}% "
                f"({format_hours(session.duration_hours)})"
            )
    else:
        print("  Charge sessions: none observed in this window.")


def main() -> None:
    config = load_config()
    args = _parse_args(default_db_path=config.db_path)

    if not Path(args.db).exists():
        print(f"[ERROR] Database not found: {args.db}")
        raise SystemExit(1)

    connection = sqlite3.connect(args.db)

    try:
        reports = build_all_reports(
            connection, window_days=args.days, device_filter=args.device
        )
    finally:
        connection.close()

    if not reports:
        print("No matching devices found.")
        return

    day_word = "day" if args.days == 1 else "days"
    print(f"BTBatteryLab analytics - last {args.days} {day_word}")

    for report in reports:
        _print_report(report)


if __name__ == "__main__":
    main()
