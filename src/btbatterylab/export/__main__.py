"""
Command-line CSV export of the raw battery_log history.

Usage:
    python -m btbatterylab.export
    python -m btbatterylab.export --days 7 --device "MX Master"
    python -m btbatterylab.export --out battery_history.csv
    python -m btbatterylab.export --db path\to\btbatterylab.db
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from btbatterylab.config import load_config
from btbatterylab.export.csv_export import DEFAULT_WINDOW_DAYS, export_battery_log


def _parse_args(default_db_path: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export the raw battery_log history (every reading recorded "
            "from either channel) to a CSV file."
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
        help=f"Time window in days to export (default: {DEFAULT_WINDOW_DAYS}).",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Only export devices whose name or address contains this text.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "Output CSV path (default: battery-log-<timestamp>.csv inside "
            "an 'exports' subfolder of the standard data folder)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    config = load_config()
    args = _parse_args(default_db_path=config.db_path)

    if not Path(args.db).exists():
        print(f"[ERROR] Database not found: {args.db}")
        raise SystemExit(1)

    if args.out:
        out_path = Path(args.out)
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = config.data_dir / "exports" / f"battery-log-{timestamp}.csv"

    connection = sqlite3.connect(args.db)

    try:
        row_count = export_battery_log(
            connection,
            out_path,
            window_days=args.days,
            device_filter=args.device,
        )
    finally:
        connection.close()

    day_word = "day" if args.days == 1 else "days"
    print(
        f"Exported {row_count} reading(s) from the last {args.days} "
        f"{day_word} to {out_path}"
    )


if __name__ == "__main__":
    main()
