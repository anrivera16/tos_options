"""
IV Skew Backtest — Replay 10 days of snapshot history to measure
put skew behavior and test predictive signals.

Concept: IV skew = OTM put IV minus ATM put IV.
When skew steepens (OTM puts get more expensive relative to ATM),
the market is buying downside protection aggressively — often precedes drawdowns.

Usage:
    DATABASE_URL=postgresql://... python3 scripts/backtest_iv_skew.py
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from scripts.shared import ET, get_db_url, is_postgres

# ---------------------------------------------------------------------------
# Delta buckets for IV surface
# ---------------------------------------------------------------------------

# Delta buckets for IV surface
# For puts: Schwab returns negative deltas (-0.50 ATM). After ABS(), ATM = ~0.50.
# We bucket by ABS(delta) to compare puts and calls on the same scale.

PUT_BUCKETS = [
    ("atm",  0.45, 0.55),   # ATM: delta ~0.50
    ("0.05", 0.03, 0.07),   # Deep OTM: delta ~0.05
    ("0.10", 0.08, 0.12),   # OTM: delta ~0.10
    ("0.15", 0.13, 0.17),   # OTM: delta ~0.15
    ("0.20", 0.18, 0.22),   # OTM: delta ~0.20
    ("0.25", 0.23, 0.27),   # OTM: delta ~0.25
    ("0.30", 0.28, 0.32),   # OTM: delta ~0.30
]

CALL_BUCKETS = PUT_BUCKETS  # Same bucket definitions for calls


@dataclass
class SnapshotSkew:
    """One snapshot's IV skew profile."""
    symbol: str
    captured_at: str
    underlying_price: float
    put_atm_iv: float | None
    put_05_iv: float | None
    put_10_iv: float | None
    put_15_iv: float | None
    put_20_iv: float | None
    put_25_iv: float | None
    put_30_iv: float | None
    call_atm_iv: float | None
    call_10_iv: float | None
    call_20_iv: float | None
    call_30_iv: float | None
    # Derived signals
    put_skew_10_vs_atm: float | None   # put 0.10 IV - put ATM IV
    put_skew_20_vs_atm: float | None   # put 0.20 IV - put ATM IV
    put_skew_slope: float | None       # rate of change across buckets
    skew_ratio: float | None           # put_20_iv / put_atm_iv (>1 = steep)


def fetch_daily_skew_snapshots(db_url: str, symbol: str, days: int = 10):
    """
    Fetch one EOD reading per day per symbol.
    Uses the last snapshot of each trading day, grouped by delta bucket.
    """
    import psycopg
    conn = psycopg.connect(db_url)
    try:
        # Step 1: Get the latest snapshot ID per day for this symbol
        day_snaps = conn.execute("""
            SELECT DATE(captured_at) as day, MAX(id) as snap_id
            FROM snapshots
            WHERE symbol = %s
            GROUP BY DATE(captured_at)
            ORDER BY day DESC
            LIMIT %s
        """, (symbol, days)).fetchall()

        if not day_snaps:
            print(f"No data found for {symbol}")
            return []

        snap_ids = [row[1] for row in day_snaps]
        placeholders = ", ".join(["%s"] * len(snap_ids))

        # Step 2: Fetch all contracts for those snapshots with Greeks
        rows = conn.execute(f"""
            SELECT
                s.id as snap_id,
                DATE(s.captured_at) as day,
                s.captured_at,
                s.underlying_price,
                oc.put_call,
                ABS(oc.delta) as abs_delta,
                oc.volatility as iv,
                oc.strike,
                oc.dte
            FROM option_contracts oc
            JOIN snapshots s ON oc.snapshot_id = s.id
            WHERE s.id IN ({placeholders})
            AND oc.delta IS NOT NULL
            AND oc.volatility > 0
            AND oc.volatility < 200
            AND oc.dte = 7
            ORDER BY s.captured_at, oc.put_call, ABS(oc.delta)
        """, snap_ids).fetchall()

        # Step 3: Bucket by delta
        results: list[SnapshotSkew] = []
        current_snap = None
        put_buckets = {}
        call_buckets = {}

        def emit_snap():
            nonlocal current_snap
            if current_snap is None:
                return

            # Get bucket IVs
            def get_bucket(bucket_id: str, buckets: dict) -> float | None:
                vals = buckets.get(bucket_id, [])
                if not vals:
                    return None
                return sum(vals) / len(vals)

            put_atm = get_bucket("atm", put_buckets)
            put_05 = get_bucket("0.05", put_buckets)
            put_10 = get_bucket("0.10", put_buckets)
            put_15 = get_bucket("0.15", put_buckets)
            put_20 = get_bucket("0.20", put_buckets)
            put_25 = get_bucket("0.25", put_buckets)
            put_30 = get_bucket("0.30", put_buckets)
            call_atm = get_bucket("atm", call_buckets)
            call_10 = get_bucket("0.10", call_buckets)
            call_20 = get_bucket("0.20", call_buckets)
            call_30 = get_bucket("0.30", call_buckets)

            # Derived signals
            put_skew_10 = (put_10 - put_atm) if (put_10 and put_atm) else None
            put_skew_20 = (put_20 - put_atm) if (put_20 and put_atm) else None
            skew_ratio = (put_20 / put_atm) if (put_20 and put_atm and put_atm > 0) else None

            # Skew slope: linear regression across OTM put buckets (ordered)
            put_points = []
            for label, lo, hi in PUT_BUCKETS:
                if label == "atm":
                    continue  # skip ATM for slope
                iv = get_bucket(label, put_buckets)
                if iv is not None:
                    put_points.append((float(label), iv))
            if len(put_points) >= 3:
                n = len(put_points)
                sum_x = sum(p[0] for p in put_points)
                sum_y = sum(p[1] for p in put_points)
                sum_xy = sum(p[0]*p[1] for p in put_points)
                sum_x2 = sum(p[0]**2 for p in put_points)
                denom = n * sum_x2 - sum_x**2
                if denom != 0:
                    slope = (n * sum_xy - sum_x * sum_y) / denom
                else:
                    slope = None
            else:
                slope = None

            results.append(SnapshotSkew(
                symbol=symbol,
                captured_at=current_snap[2],
                underlying_price=current_snap[3] or 0,
                put_atm_iv=put_atm,
                put_05_iv=put_05,
                put_10_iv=put_10,
                put_15_iv=put_15,
                put_20_iv=put_20,
                put_25_iv=put_25,
                put_30_iv=put_30,
                call_atm_iv=call_atm,
                call_10_iv=call_10,
                call_20_iv=call_20,
                call_30_iv=call_30,
                put_skew_10_vs_atm=put_skew_10,
                put_skew_20_vs_atm=put_skew_20,
                put_skew_slope=slope,
                skew_ratio=skew_ratio,
            ))

        for row in rows:
            snap_id, day, captured_at, price, pc, abs_delta, iv, strike, dte = row
            if snap_id != current_snap[0] if current_snap else True:
                emit_snap()
                current_snap = (snap_id, day, captured_at, price)
                put_buckets = {}
                call_buckets = {}

            bucket = None
            target = abs_delta
            buckets = put_buckets if pc == "PUT" else call_buckets

            for label, lo, hi in PUT_BUCKETS:
                if lo <= target < hi or (label == "atm" and target < 0.035):
                    bucket = label
                    break

            if bucket and iv:
                if bucket not in buckets:
                    buckets[bucket] = []
                buckets[bucket].append(iv)

        emit_snap()  # final snap
        return results

    finally:
        conn.close()


def print_skew_table(skew_data: list[SnapshotSkew]):
    """Print IV skew profile as terminal table."""
    print(f"\n{'=' * 120}")
    print(f"  IV SKEW PROFILE — {skew_data[0].symbol} | {len(skew_data)} daily readings")
    print(f"{'=' * 120}")
    print(f"  {'Date':<11} {'Spot':>7} {'ATM Put':>7} {'0.05':>6} {'0.10':>6} "
          f"{'0.15':>6} {'0.20':>6} {'0.25':>6} {'0.30':>6} | "
          f"{'Skew10':>6} {'Skew20':>6} {'Ratio':>5} {'Slope':>6}")
    print(f"  {'-' * 120}")

    for s in skew_data:
        date_str = str(s.captured_at)[:10] if s.captured_at else "?"
        spot = f"{s.underlying_price:.1f}"
        atm = f"{s.put_atm_iv:.1f}" if s.put_atm_iv else "    - "
        p05 = f"{s.put_05_iv:.1f}" if s.put_05_iv else "   - "
        p10 = f"{s.put_10_iv:.1f}" if s.put_10_iv else "   - "
        p15 = f"{s.put_15_iv:.1f}" if s.put_15_iv else "   - "
        p20 = f"{s.put_20_iv:.1f}" if s.put_20_iv else "   - "
        p25 = f"{s.put_25_iv:.1f}" if s.put_25_iv else "   - "
        p30 = f"{s.put_30_iv:.1f}" if s.put_30_iv else "   - "
        skew10 = f"{s.put_skew_10_vs_atm:+.1f}" if s.put_skew_10_vs_atm else "    - "
        skew20 = f"{s.put_skew_20_vs_atm:+.1f}" if s.put_skew_20_vs_atm else "    - "
        ratio = f"{s.skew_ratio:.2f}" if s.skew_ratio else "   - "
        slope = f"{s.put_skew_slope:+.2f}" if s.put_skew_slope is not None else "    - "

        print(f"  {date_str:<11} {spot:>7} {atm:>7} {p05:>6} {p10:>6} "
              f"{p15:>6} {p20:>6} {p25:>6} {p30:>6} | "
              f"{skew10:>6} {skew20:>6} {ratio:>5} {slope:>6}")

    print(f"  {'-' * 120}")


def print_signal_analysis(skew_data: list[SnapshotSkew]):
    """Analyze skew signals for predictive patterns."""
    if len(skew_data) < 3:
        print("\n  Not enough data for signal analysis (need 3+ days)")
        return

    print(f"\n{'=' * 80}")
    print(f"  SIGNAL ANALYSIS — {skew_data[0].symbol}")
    print(f"{'=' * 80}")

    # Track skew changes
    prev_ratio = None
    prev_slope = None
    for i, s in enumerate(skew_data):
        date_str = str(s.captured_at)[:10] if s.captured_at else "?"

        signals = []
        if s.skew_ratio is not None and prev_ratio is not None:
            ratio_change = s.skew_ratio - prev_ratio
            if ratio_change > 0.05:
                signals.append("STEEPENING")
            elif ratio_change < -0.05:
                signals.append("FLATTENING")

        if s.put_skew_slope is not None and prev_slope is not None:
            slope_change = s.put_skew_slope - prev_slope
            if slope_change > 0.02:
                signals.append("ACCEL_UP")
            elif slope_change < -0.02:
                signals.append("ACCEL_DOWN")

        if s.skew_ratio and s.skew_ratio > 1.5:
            signals.append("EXTREME_SKEW")

        signal_str = ", ".join(signals) if signals else "quiet"
        ratio_str = f"{s.skew_ratio:.2f}" if s.skew_ratio else "-"
        slope_str = f"{s.put_skew_slope:+.2f}" if s.put_skew_slope is not None else "-"

        print(f"  {date_str}  ratio={ratio_str}  slope={slope_str}  [{signal_str}]")

        prev_ratio = s.skew_ratio
        prev_slope = s.put_skew_slope

    # Summary stats
    ratios = [s.skew_ratio for s in skew_data if s.skew_ratio is not None]
    slopes = [s.put_skew_slope for s in skew_data if s.put_skew_slope is not None]

    if ratios:
        print(f"\n  Skew Ratio Stats (put_20_iv / put_atm_iv):")
        print(f"    Min: {min(ratios):.2f}  Max: {max(ratios):.2f}  Avg: {sum(ratios)/len(ratios):.2f}")
    if slopes:
        print(f"\n  Skew Slope Stats (IV change per delta point):")
        print(f"    Min: {min(slopes):+.2f}  Max: {max(slopes):+.2f}  Avg: {sum(slopes)/len(slopes):+.2f}")


def main():
    db_url = get_db_url()
    if not is_postgres(db_url):
        print("Error: This script requires a PostgreSQL connection")
        sys.exit(1)

    symbol = "SPY"
    days = 30

    print(f"Fetching IV skew data for {symbol} (last {days} days)...")
    skew_data = fetch_daily_skew_snapshots(db_url, symbol, days=days)

    if not skew_data:
        print("No data found. Try a different symbol or check DB connection.")
        sys.exit(1)

    # Reverse to chronological order
    skew_data.reverse()

    print_skew_table(skew_data)
    print_signal_analysis(skew_data)

    # Also show SPX if available
    print(f"\n{'=' * 120}")
    print(f"\nFetching $SPX skew data...")
    spx_data = fetch_daily_skew_snapshots(db_url, "$SPX", days=days)
    if spx_data:
        spx_data.reverse()
        print_skew_table(spx_data)
        print_signal_analysis(spx_data)


if __name__ == "__main__":
    main()
