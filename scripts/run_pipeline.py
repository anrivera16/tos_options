"""
Credit Spread Pipeline — run the algo pipeline against live Schwab data.

Usage:
    python3 scripts/run_pipeline.py
    python3 scripts/run_pipeline.py --config baseline
    python3 scripts/run_pipeline.py --config full_stack
"""
from __future__ import annotations

import os
import sys
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algo.config import PipelineConfig, baseline_config, full_stack_config
from algo.pipeline import BacktestPipeline
from algo.display import format_pipeline_report
from algo.wall_detector import detect_walls, fetch_strike_data_from_rows
from algo.trend_filter import determine_trend
from algo.iv_rank_filter import compute_iv_rank
from gex.storage import get_connection

logging.basicConfig(level=logging.WARNING, format="%(name)s | %(message)s")

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://trader:changeme@localhost:5433/options"
)

CONFIGS = {
    "baseline": baseline_config,
    "full_stack": full_stack_config,
}


def fetch_data(conn):
    """Fetch everything the pipeline needs from Postgres."""
    cur = conn.cursor()

    # Latest SPY snapshot
    cur.execute("""
        SELECT id, underlying_price, captured_at
        FROM snapshots WHERE symbol = 'SPY'
        ORDER BY captured_at::timestamp DESC LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        print("No SPY snapshots found in database.")
        sys.exit(1)

    snap_id, price, ts = row

    # All option contracts for this snapshot
    cur.execute("""
        SELECT underlying_symbol, strike, put_call, expiration_date, dte,
               bid, ask, mark, delta, gamma, theta, vega, volatility,
               open_interest, total_volume
        FROM option_contracts
        WHERE snapshot_id = %s AND delta IS NOT NULL
        ORDER BY put_call, dte, strike
    """, [snap_id])
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, r)) for r in cur.fetchall()]

    # Daily closing prices for trend filter (30 days)
    cur.execute("""
        SELECT DISTINCT ON (captured_at::date)
            underlying_price, captured_at::date as day
        FROM snapshots
        WHERE symbol = 'SPY'
        AND captured_at::timestamp >= NOW() - INTERVAL '30 days'
        AND underlying_price IS NOT NULL
        ORDER BY captured_at::date, captured_at DESC
    """)
    prices = [float(r[0]) for r in cur.fetchall() if r[0]]

    # Daily ATM IV history for IV rank calculation.
    # Method: one EOD reading per day, closest-to-ATM put at DTE 14,
    # from the last snapshot of each trading day. This gives a clean,
    # consistent IV series rather than mixing DTEs and intraday noise.
    IV_DTE = 14  # fixed DTE for consistent comparison
    cur.execute("""
        SELECT day, iv FROM (
            SELECT date(s.captured_at::timestamp) as day,
                   oc.volatility as iv,
                   ROW_NUMBER() OVER (
                       PARTITION BY date(s.captured_at::timestamp)
                       ORDER BY s.captured_at::timestamp DESC,
                                ABS(oc.strike - s.underlying_price)
                   ) as rn
            FROM option_contracts oc
            JOIN snapshots s ON oc.snapshot_id = s.id
            WHERE s.symbol = 'SPY'
            AND oc.put_call = 'PUT'
            AND oc.dte = %s
            AND ABS(oc.strike - s.underlying_price) < 1
            AND oc.volatility > 0 AND oc.volatility < 200
            AND s.underlying_price IS NOT NULL
        ) sub WHERE rn = 1 ORDER BY day
    """, [IV_DTE])
    iv_rows = cur.fetchall()
    ivs = [float(r[1]) for r in iv_rows if r[1]]
    current_iv = ivs[-1] if ivs else None
    iv_days = len(ivs)

    return {
        "rows": rows,
        "underlying_price": float(price),
        "timestamp": str(ts),
        "price_history": prices,
        "iv_history": ivs,
        "current_iv": current_iv,
        "iv_days": iv_days,
        "iv_dte": IV_DTE,
    }


def run(config: PipelineConfig) -> None:
    conn = get_connection(DB_URL)
    data = fetch_data(conn)

    # Adjust strike width to match available data range
    # Scraper captures ~655-775 on SPY, $3 width fits the delta 0.10-0.20 zone
    config.generator.strike_width = 3.0

    # Compute market context for display
    trend_dir = determine_trend(
        data["underlying_price"], data["price_history"], config.trend
    )
    sma20 = (
        sum(data["price_history"][-20:]) / 20
        if len(data["price_history"]) >= 20 else 0
    )
    trend_info = {
        "direction": trend_dir.value,
        "sma": sma20,
        "price": data["underlying_price"],
        "sma_pct": (
            (data["underlying_price"] - sma20) / sma20 * 100 if sma20 else 0
        ),
    }

    current_iv = data["current_iv"]
    iv_history = data["iv_history"]
    iv_rank_val = compute_iv_rank(current_iv, iv_history) if current_iv else None
    iv_info = {
        "current_iv": current_iv,
        "rank": iv_rank_val,
        "historical_min": min(iv_history) if iv_history else 0,
        "historical_max": max(iv_history) if iv_history else 0,
        "days": data["iv_days"],
        "dte": data["iv_dte"],
    }

    strike_data = fetch_strike_data_from_rows(data["rows"])
    walls = detect_walls(strike_data, data["underlying_price"], config.walls)

    # Run pipeline
    pipeline = BacktestPipeline(config)
    result = pipeline.run_on_snapshot(
        rows=data["rows"],
        underlying_price=data["underlying_price"],
        snapshot_timestamp=data["timestamp"],
        price_history=data["price_history"],
        historical_ivs=data["iv_history"],
        current_iv=data["current_iv"],
    )

    print(format_pipeline_report(
        result, walls=walls, trend_info=trend_info, iv_info=iv_info
    ))


def main():
    parser = argparse.ArgumentParser(
        description="Credit spread signal pipeline for SPY"
    )
    parser.add_argument(
        "--config", "-c",
        choices=list(CONFIGS.keys()),
        default="full_stack",
        help="Pipeline config preset (default: full_stack)",
    )
    args = parser.parse_args()

    config = CONFIGS[args.config]()
    run(config)


if __name__ == "__main__":
    main()
