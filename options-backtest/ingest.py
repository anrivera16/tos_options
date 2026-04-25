#!/usr/bin/env python3
"""Filter raw CSV files to target tickers and save as partitioned Parquet.

Usage:
    python ingest.py                     # defaults to SPY
    python ingest.py --tickers SPY QQQ   # multiple tickers
    python ingest.py --tickers SPY --force  # reprocess all files
"""

import argparse
import gzip
import re
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).parent / "raw"
PARQUET_DIR = Path(__file__).parent / "parquet"

# Regex to extract underlier from OCC option ticker: O:SPY260116P00580000 -> SPY
TICKER_RE = re.compile(r"^O:([A-Z]+)")


def extract_underlier(ticker: str) -> str:
    m = TICKER_RE.match(ticker)
    return m.group(1) if m else ""


def process_file(filepath: Path, tickers: set) -> "pd.DataFrame":
    """Read a gzipped CSV, filter to target tickers, return DataFrame."""
    try:
        with gzip.open(filepath, "rt") as f:
            df = pd.read_csv(f)
    except Exception as e:
        print(f"  [error] {filepath.name}: {e}")
        return None

    df["underlier"] = df["ticker"].apply(extract_underlier)
    df = df[df["underlier"].isin(tickers)]

    if df.empty:
        return None

    # Parse window_start from nanosecond epoch to date
    df["date"] = pd.to_datetime(df["window_start"], unit="ns").dt.date

    # Parse option details from ticker
    # O:SPY260116P00580000 -> expiry=260116, type=P, strike=580.000
    parts = re.compile(r"O:\w+(\d{6})([CP])(\d{8})")
    parsed = df["ticker"].str.extract(parts)
    df["expiry_raw"] = parsed[0]
    df["option_type"] = parsed[1]
    df["strike"] = parsed[2].astype(float) / 1000

    # Convert expiry to proper date (YYMMDD -> 20YY-MM-DD)
    df["expiry"] = pd.to_datetime("20" + df["expiry_raw"], format="%Y%m%d").dt.date

    # DTE (calendar days)
    df["dte"] = (pd.to_datetime(df["expiry"]) - pd.to_datetime(df["date"])).dt.days

    # Drop temp columns
    df = df.drop(columns=["underlier", "expiry_raw"])

    return df


def main():
    parser = argparse.ArgumentParser(description="Filter raw CSVs to Parquet")
    parser.add_argument(
        "--tickers", nargs="+", default=["SPY"], help="Underliers to keep (default: SPY)"
    )
    parser.add_argument("--force", action="store_true", help="Reprocess all files")
    args = parser.parse_args()

    tickers = set(args.tickers)
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)

    # Find raw files
    raw_files = sorted(RAW_DIR.glob("*.csv.gz"))
    if not raw_files:
        print(f"No raw files found in {RAW_DIR}")
        print("Run download.py first.")
        return

    # Find already-processed dates
    existing = set()
    if not args.force:
        for pq in PARQUET_DIR.glob("*.parquet"):
            # Files named like SPY_2025-12.parquet
            existing.add(pq.stem.split("_", 1)[1])

    print(f"Filtering to: {', '.join(sorted(tickers))}")
    print(f"Found {len(raw_files)} raw files ({len(existing)} months already processed)\n")

    all_frames = []
    for f in raw_files:
        month_key = f.stem[:7]  # "2025-12"
        if month_key in existing and not args.force:
            print(f"  [skip] {f.name} (month already in Parquet)")
            continue

        df = process_file(f, tickers)
        if df is not None:
            print(f"  [ok] {f.name}: {len(df)} rows")
            all_frames.append(df)
        else:
            print(f"  [empty] {f.name}: no matching tickers")

    if not all_frames:
        print("\nNo new data to process.")
        return

    combined = pd.concat(all_frames, ignore_index=True)
    print(f"\nTotal filtered rows: {len(combined):,}")

    # Write one Parquet per underlier per month
    for ticker in sorted(tickers):
        tdf = combined[combined["ticker"].str.startswith(f"O:{ticker}")]
        if tdf.empty:
            continue

        for month, mdf in tdf.groupby(tdf["date"].astype(str).str[:7]):
            out = PARQUET_DIR / f"{ticker}_{month}.parquet"
            mdf.to_parquet(out, index=False, engine="pyarrow")
            print(f"  [wrote] {out.name}: {len(mdf)} rows")

    print(f"\nParquet files saved to: {PARQUET_DIR.resolve()}")


if __name__ == "__main__":
    main()
