"""
Test the algo pipeline against real Schwab data in Postgres.

Usage:
    DATABASE_URL="postgresql://trader:changeme@localhost:5433/options" \
        python3 scripts/test_algo_signals.py
"""
from __future__ import annotations

import os
import sys
import logging

logging.basicConfig(level=logging.WARNING, format="%(name)s | %(message)s")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gex.storage import get_connection
from algo.config import PipelineConfig, baseline_config, full_stack_config
from algo.pipeline import BacktestPipeline
from algo.display import format_pipeline_report
from algo.wall_detector import detect_walls, fetch_strike_data_from_rows
from algo.trend_filter import determine_trend
from algo.iv_rank_filter import compute_iv_rank

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://trader:changeme@localhost:5433/options"
)


def fetch_data(conn):
    """Fetch all data needed for the pipeline from DB."""
    cur = conn.cursor()

    # Latest SPY snapshot
    cur.execute("""
        SELECT id, underlying_price, captured_at
        FROM snapshots WHERE symbol = 'SPY'
        ORDER BY captured_at::timestamp DESC LIMIT 1
    """)
    snap_id, price, ts = cur.fetchone()

    # All contracts
    cur.execute("""
        SELECT underlying_symbol, strike, put_call, expiration_date, dte,
               bid, ask, mark, delta, gamma, theta, vega, volatility,
               open_interest, total_volume
        FROM option_contracts
        WHERE snapshot_id = %s AND delta IS NOT NULL
        ORDER BY put_call, dte, strike
    """, [snap_id])
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    # Price history for trend
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

    # IV history
    cur.execute("""
        SELECT oc.volatility
        FROM (
            SELECT oc.volatility, ABS(oc.strike - s.underlying_price) as dist,
                   s.captured_at,
                   ROW_NUMBER() OVER(PARTITION BY s.id
                       ORDER BY ABS(oc.strike - s.underlying_price)) as rn
            FROM option_contracts oc
            JOIN snapshots s ON oc.snapshot_id = s.id
            WHERE s.symbol = 'SPY' AND oc.put_call = 'PUT'
            AND oc.volatility IS NOT NULL AND s.underlying_price IS NOT NULL
            AND s.captured_at::timestamp >= NOW() - INTERVAL '30 days'
        ) oc WHERE rn = 1 ORDER BY captured_at
    """)
    ivs = [float(r[0]) for r in cur.fetchall() if r[0]]
    current_iv = ivs[-1] if ivs else None

    return {
        "rows": rows,
        "underlying_price": float(price),
        "timestamp": str(ts),
        "price_history": prices,
        "iv_history": ivs,
        "current_iv": current_iv,
    }


def main():
    conn = get_connection(DB_URL)
    data = fetch_data(conn)

    # ── Compute context info ─────────────────────────────
    cfg_full = full_stack_config()
    cfg_full.generator.strike_width = 3.0  # fits current data range

    trend_dir = determine_trend(
        data["underlying_price"], data["price_history"], cfg_full.trend
    )
    sma20 = sum(data["price_history"][-20:]) / 20 if len(data["price_history"]) >= 20 else 0

    trend_info = {
        "direction": trend_dir.value,
        "sma": sma20,
        "price": data["underlying_price"],
        "sma_pct": (data["underlying_price"] - sma20) / sma20 * 100 if sma20 else 0,
    }

    iv_rank_val = compute_iv_rank(data["current_iv"], data["iv_history"]) if data["current_iv"] else None
    iv_info = {
        "current_iv": data["current_iv"],
        "rank": iv_rank_val,
        "historical_min": min(data["iv_history"]) if data["iv_history"] else 0,
        "historical_max": max(data["iv_history"]) if data["iv_history"] else 0,
    }

    strike_data = fetch_strike_data_from_rows(data["rows"])
    walls = detect_walls(strike_data, data["underlying_price"], cfg_full.walls)

    # ── Run baseline ─────────────────────────────────────
    cfg_base = baseline_config()
    cfg_base.generator.strike_width = 3.0
    cfg_base.scoring.enabled = True  # need scores for display

    pipeline_base = BacktestPipeline(cfg_base)
    result_base = pipeline_base.run_on_snapshot(
        rows=data["rows"],
        underlying_price=data["underlying_price"],
        snapshot_timestamp=data["timestamp"],
    )

    print(format_pipeline_report(result_base, walls=walls, trend_info=trend_info, iv_info=iv_info))

    # ── Run full stack (lowered IV rank to force flow-through) ──
    print()
    print("  ═══════════════════════════════════════════════════")
    print("  FULL STACK  (IV rank min lowered to 5% for demo)")
    print("  ═══════════════════════════════════════════════════")

    cfg_full.iv_rank.min_rank = 5.0  # lower so current 7% passes
    cfg_full.scoring.enabled = True
    cfg_full.earnings.enabled = False  # skip for demo — AAPL/META report next week

    pipeline_full = BacktestPipeline(cfg_full)
    result_full = pipeline_full.run_on_snapshot(
        rows=data["rows"],
        underlying_price=data["underlying_price"],
        snapshot_timestamp=data["timestamp"],
        price_history=data["price_history"],
        historical_ivs=data["iv_history"],
        current_iv=data["current_iv"],
    )

    print(format_pipeline_report(result_full, walls=walls, trend_info=trend_info, iv_info=iv_info))


if __name__ == "__main__":
    main()
