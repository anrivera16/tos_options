#!/usr/bin/env python3
"""Download Polygon options day aggregates from S3 flatfiles.

Usage:
    python download.py                          # download last 6 months
    python download.py --start 2024-01-01       # from specific date
    python download.py --start 2024-01-01 --end 2024-06-30
    python download.py --months 12              # last 12 months
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

RAW_DIR = Path(__file__).parent / "raw"
ENDPOINT = "https://files.massive.com"
BUCKET = "s3://flatfiles/us_options_opra/day_aggs_v1"


def trading_days(start: datetime, end: datetime) -> list[str]:
    """Generate weekdays between start and end (excludes weekends)."""
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            days.append(current.strftime("%Y/%m/%Y-%m-%d"))
        current += timedelta(days=1)
    return days


def download_file(date_path: str) -> bool:
    """Download a single day's CSV.gz file."""
    filename = date_path.split("/")[-1] + ".csv.gz"
    local_path = RAW_DIR / filename

    if local_path.exists():
        print(f"  [skip] {filename} (already exists)")
        return True

    s3_uri = f"{BUCKET}/{date_path}.csv.gz"
    print(f"  [download] {filename}...", end=" ", flush=True)

    result = subprocess.run(
        ["aws", "s3", "cp", s3_uri, str(local_path), "--endpoint-url", ENDPOINT],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        size_mb = local_path.stat().st_size / (1024 * 1024)
        print(f"OK ({size_mb:.1f} MB)")
        return True
    else:
        print(f"FAILED")
        print(f"    {result.stderr.strip()}")
        if local_path.exists():
            local_path.unlink()
        return False


def main():
    parser = argparse.ArgumentParser(description="Download Polygon options day aggs")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--months", type=int, default=6, help="Months to look back (default: 6)")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d")
    else:
        start = datetime.now() - timedelta(days=args.months * 30)

    end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()

    days = trading_days(start, end)
    print(f"Downloading {len(days)} trading days from {start.date()} to {end.date()}")
    print(f"Output: {RAW_DIR.resolve()}\n")

    success = 0
    failed = 0
    for day in days:
        if download_file(day):
            success += 1
        else:
            failed += 1

    print(f"\nDone: {success} downloaded, {failed} failed")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
