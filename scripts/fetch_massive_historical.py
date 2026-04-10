#!/usr/bin/env python3
"""
Fetch Historical Options Data from Massive API

Usage:
    python scripts/fetch_massive_historical.py --symbol SPY [--days 7] [--dry-run]

Options:
    --symbol     Symbol to fetch (default: SPY)
    --days       Number of days to fetch (default: 7)
    --dry-run    Test API connection without writing to DB
    --db         Write to database (default: True if DB available)
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from z0dte.db.connection import get_connection
from z0dte.ingestion.pipeline import IngestionPipeline
from z0dte.sources.massive_api import MassiveAPIDataSource, MassiveAPIError


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch historical options data from Massive API"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="SPY",
        help="Symbol to fetch (default: SPY)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to fetch (default: 7)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test API connection without writing to DB",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip database write",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Massive API key (or use MASSIVE_API_KEY env var)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    api_key = args.api_key or __import__("os").environ.get("MASSIVE_API_KEY")
    if not api_key:
        print("Error: MASSIVE_API_KEY environment variable or --api-key required")
        sys.exit(1)

    print("=" * 60)
    print("MASSIVE API HISTORICAL DATA FETCH")
    print(f"Symbol: {args.symbol}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        print(f"\nConnecting to Massive API...")
        source = MassiveAPIDataSource(
            api_key=api_key,
            symbols=[args.symbol],
        )

        if args.dry_run:
            print("\nDry run mode - testing API connection...")
            snapshot = source.fetch_snapshot(args.symbol)
            print(f"  Fetched snapshot with {len(snapshot.contracts)} contracts")
            print(f"  Underlying price: ${snapshot.underlying_price:.2f}")
            print(f"  Source: {snapshot.source}")
            print("\nDry run successful!")
            return

        if not args.no_db:
            print("\nConnecting to database...")
            try:
                conn = get_connection()
                print("  Connected successfully")
            except Exception as e:
                print(f"  Database connection failed: {e}")
                print("  Falling back to dry-run mode")
                args.dry_run = True

        if args.no_db or args.dry_run:
            print("\nFetching data (no DB write)...")
            snapshot = source.fetch_snapshot(args.symbol)
            print(f"\nFetched {len(snapshot.contracts)} contracts")
            print(f"Underlying price: ${snapshot.underlying_price:.2f}")
            print(f"Captured at: {snapshot.captured_at}")
            return

        print(f"\nFetching and storing {args.symbol} options data...")

        pipeline = IngestionPipeline(source=source, db_conn=conn)
        snapshot_id = pipeline.run_one(args.symbol)

        print(f"\nSnapshot stored with ID: {snapshot_id}")
        print(f"Contracts written: {len(source.fetch_snapshot(args.symbol).contracts)}")

    except MassiveAPIError as e:
        print(f"\nMassive API Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
