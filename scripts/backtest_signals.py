"""
Backtest with Signal Filters — replays historical snapshots through the
signal filter pipeline to see which trades would have actually fired.

Shows:
  1. How many legs passed each filter at each timestamp
  2. Which spreads were actually built from filtered legs
  3. Comparison: raw candidate count vs. filtered count
  4. Full filter reasons for top candidates
"""
from __future__ import annotations

import sys
import os
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spread_hunter.spread_builder import (
    SpreadHunterConfig,
    build_filtered_spreads,
    fetch_contracts,
    fetch_price_history,
    fetch_atm_iv_history,
    fetch_strike_oi,
    group_contracts,
    _row_to_leg,
    _f,
    _build_bull_put_credits,
    _build_bear_call_credits,
)
from spread_hunter.signal_filters import (
    run_all_filters,
    check_delta,
    check_volume_oi,
    check_iv_rank,
    check_trend,
    check_support,
)
from spread_hunter.spread_types import SignalFilter
from spread_hunter.spread_scoring import score_all
from gex.storage import get_connection


def parse_args():
    p = argparse.ArgumentParser(description="Backtest signal filters against historical data")
    p.add_argument("--ticker", default="SPY", help="Ticker to backtest (default: SPY)")
    p.add_argument("--dte-min", type=int, default=5, help="Min DTE (default: 5)")
    p.add_argument("--dte-max", type=int, default=9, help="Max DTE (default: 9)")
    p.add_argument("--delta-min", type=float, default=0.10, help="Min abs delta (default: 0.10)")
    p.add_argument("--delta-max", type=float, default=0.25, help="Max abs delta (default: 0.25)")
    p.add_argument("--iv-rank-min", type=float, default=30.0, help="Min IV rank %% (default: 30)")
    p.add_argument("--iv-rank-max", type=float, default=95.0, help="Max IV rank %% (default: 95)")
    p.add_argument("--min-oi", type=int, default=100, help="Min open interest (default: 100)")
    p.add_argument("--min-volume", type=int, default=50, help="Min volume (default: 50)")
    p.add_argument("--sma-periods", type=int, default=20, help="SMA periods for trend (default: 20)")
    p.add_argument("--no-trend-filter", action="store_true", help="Disable trend filter")
    p.add_argument("--support-threshold", type=float, default=3.0,
                    help="Support OI threshold multiplier (default: 3.0)")
    p.add_argument("--support-buffer", type=float, default=1.0,
                    help="Support buffer %% (default: 1.0)")
    p.add_argument("--detail", action="store_true",
                    help="Show per-leg filter reasons for every candidate")
    p.add_argument("--compare", action="store_true",
                    help="Show raw vs filtered side-by-side comparison")
    return p.parse_args()


def main():
    args = parse_args()

    DB_URL = os.environ.get(
        "DATABASE_URL",
        "postgresql://trader:changeme@localhost:5433/options"
    )
    conn = get_connection(DB_URL)

    # Build signal filter from CLI args
    sf = SignalFilter(
        delta_min=args.delta_min,
        delta_max=args.delta_max,
        iv_rank_min=args.iv_rank_min,
        iv_rank_max=args.iv_rank_max,
        trend_sma_periods=args.sma_periods,
        trend_require_above_sma=not args.no_trend_filter,
        min_oi=args.min_oi,
        min_volume=args.min_volume,
        support_oi_threshold=args.support_threshold,
        support_buffer_pct=args.support_buffer,
        min_dte=args.dte_min,
        max_dte=args.dte_max,
    )

    # --- Get all snapshots for this ticker ---
    cur = conn.cursor()
    cur.execute("""
        SELECT id, symbol, underlying_price, captured_at
        FROM snapshots
        WHERE symbol = %s
        ORDER BY captured_at
    """, (args.ticker,))
    snapshots = cur.fetchall()

    if not snapshots:
        print(f"No snapshots found for {args.ticker}")
        return

    print("=" * 90)
    print(f"  SIGNAL FILTER BACKTEST — {args.ticker}")
    print(f"  Snapshots: {len(snapshots)} | Time: {snapshots[0][3]} -> {snapshots[-1][3]}")
    print(f"  DTE range: {args.dte_min}-{args.dte_max}")
    print(f"  Delta range: {args.delta_min:.2f}-{args.delta_max:.2f}")
    print(f"  OI >= {args.min_oi} | Vol >= {args.min_volume}")
    print(f"  IV rank: {args.iv_rank_min:.0f}%-{args.iv_rank_max:.0f}%")
    print(f"  Trend filter: {'OFF' if args.no_trend_filter else f'SMA({args.sma_periods})'}")
    print("=" * 90)
    print()

    # --- Process each snapshot ---
    all_results = []

    for snap_idx, (snap_id, symbol, underlying_price, captured_at) in enumerate(snapshots):
        time_str = str(captured_at)[11:16] if captured_at else "??:??"
        price = float(underlying_price) if underlying_price else 0.0

        # Fetch contracts for this snapshot
        cur.execute("""
            SELECT oc.underlying_symbol, s.underlying_price, oc.strike, oc.put_call,
                   oc.expiration_date, oc.dte, oc.bid, oc.ask, oc.mark,
                   oc.delta, oc.gamma, oc.theta, oc.vega, oc.volatility,
                   oc.total_volume, oc.open_interest
            FROM option_contracts oc
            JOIN snapshots s ON oc.snapshot_id = s.id
            WHERE oc.snapshot_id = %s
            AND oc.delta IS NOT NULL
            AND oc.volatility IS NOT NULL
        """, (snap_id,))
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]

        if not rows:
            all_results.append({
                "time": time_str, "price": price,
                "raw_puts": 0, "raw_calls": 0,
                "filtered_puts": 0, "filtered_calls": 0,
                "filter_details": [],
                "spreads": {},
                "raw_spreads": {},
            })
            continue

        # Build legs
        config = SpreadHunterConfig(min_dte=args.dte_min, max_dte=args.dte_max, min_oi=0, min_volume=0)
        groups = group_contracts(rows)
        expirations = groups.get(args.ticker, {})

        all_puts = []
        all_calls = []
        for exp, pc_map in expirations.items():
            puts = [p for p in pc_map.get("PUT", []) if args.dte_min <= p.dte <= args.dte_max]
            calls = [c for c in pc_map.get("CALL", []) if args.dte_min <= c.dte <= args.dte_max]
            all_puts.extend(puts)
            all_calls.extend(calls)

        # --- Fetch historical context ---
        iv_history = fetch_atm_iv_history(conn, args.ticker, sf.iv_lookback_days, is_pg=True)
        price_history = fetch_price_history(conn, args.ticker, sf.iv_lookback_days, is_pg=True)
        put_oi_map = fetch_strike_oi(conn, args.ticker, "PUT", is_pg=True)
        call_oi_map = fetch_strike_oi(conn, args.ticker, "CALL", is_pg=True)

        # --- Run filters on each leg ---
        passed_puts = []
        passed_calls = []
        filter_details = []

        for leg in all_puts:
            ok, reasons = run_all_filters(
                leg, price, sf,
                historical_ivs=iv_history,
                price_history=price_history,
                strike_oi_map=put_oi_map,
            )
            if args.detail:
                filter_details.append({
                    "strike": leg.strike,
                    "put_call": leg.put_call,
                    "delta": leg.delta,
                    "iv": leg.iv,
                    "oi": leg.open_interest,
                    "vol": leg.volume,
                    "passed": ok,
                    "reasons": reasons,
                })
            if ok:
                passed_puts.append(leg)

        for leg in all_calls:
            ok, reasons = run_all_filters(
                leg, price, sf,
                historical_ivs=iv_history,
                price_history=price_history,
                strike_oi_map=call_oi_map,
            )
            if args.detail:
                filter_details.append({
                    "strike": leg.strike,
                    "put_call": leg.put_call,
                    "delta": leg.delta,
                    "iv": leg.iv,
                    "oi": leg.open_interest,
                    "vol": leg.volume,
                    "passed": ok,
                    "reasons": reasons,
                })
            if ok:
                passed_calls.append(leg)

        # --- Build spreads from filtered legs ---
        filtered_bulls = _build_bull_put_credits(passed_puts, price, config)
        filtered_bears = _build_bear_call_credits(passed_calls, price, config)

        # --- Build spreads from ALL legs (for comparison) ---
        raw_bulls = _build_bull_put_credits(all_puts, price, config)
        raw_bears = _build_bear_call_credits(all_calls, price, config)

        all_results.append({
            "time": time_str,
            "price": price,
            "raw_puts": len(all_puts),
            "raw_calls": len(all_calls),
            "filtered_puts": len(passed_puts),
            "filtered_calls": len(passed_calls),
            "filter_details": filter_details,
            "spreads": {
                "bull_put": filtered_bulls,
                "bear_call": filtered_bears,
            },
            "raw_spreads": {
                "bull_put": raw_bulls,
                "bear_call": raw_bears,
            },
        })

    # --- Display summary table ---
    print(f"{'Time':<8} {'Price':>8} {'Raw':>10} {'Filtered':>10} {'Ratio':>7} | "
          f"{'BullPut':>8} {'BearCall':>9} | {'RawBP':>7} {'RawBC':>8}")
    print("-" * 90)

    total_raw = 0
    total_filtered = 0
    total_bull = 0
    total_bear = 0

    for r in all_results:
        raw = r["raw_puts"] + r["raw_calls"]
        filt = r["filtered_puts"] + r["filtered_calls"]
        ratio = f"{filt/raw:.0%}" if raw > 0 else "-"
        nb = len(r["spreads"]["bull_put"])
        nbc = len(r["spreads"]["bear_call"])
        rb = len(r["raw_spreads"]["bull_put"])
        rbc = len(r["raw_spreads"]["bear_call"])

        total_raw += raw
        total_filtered += filt
        total_bull += nb
        total_bear += nbc

        marker = " >>>" if nb > 0 or nbc > 0 else ""
        print(f"{r['time']:<8} {r['price']:>8.2f} {raw:>10} {filt:>10} {ratio:>7} | "
              f"{nb:>8} {nbc:>9} | {rb:>7} {rbc:>8}{marker}")

    print("-" * 90)
    print(f"{'TOTAL':<8} {'':>8} {total_raw:>10} {total_filtered:>10} "
          f"{'%d%%' % (total_filtered/total_raw*100) if total_raw else '-':>7} | "
          f"{total_bull:>8} {total_bear:>9}")
    print()

    # --- Show filtered spreads ---
    if total_bull > 0:
        print("--- BULL PUT CREDIT SPREADS (from filtered legs) ---")
        print(f"{'Time':<8} {'Sell/Buy':>12} {'Credit':>8} {'MaxLoss':>8} {'ROI%':>6} {'Delta':>8}")
        print("-" * 60)
        for r in all_results:
            for s in r["spreads"]["bull_put"][:3]:
                print(f"{r['time']:<8} {s.short_leg.strike:>5.0f}/{s.long_leg.strike:<5.0f} "
                      f"${s.net_premium:>6.2f} ${s.max_loss:>6.2f} {s.roi_pct:>5.1f}% "
                      f"{s.short_leg.delta or 0:>7.3f}")
        print()

    if total_bear > 0:
        print("--- BEAR CALL CREDIT SPREADS (from filtered legs) ---")
        print(f"{'Time':<8} {'Sell/Buy':>12} {'Credit':>8} {'MaxLoss':>8} {'ROI%':>6} {'Delta':>8}")
        print("-" * 60)
        for r in all_results:
            for s in r["spreads"]["bear_call"][:3]:
                print(f"{r['time']:<8} {s.short_leg.strike:>5.0f}/{s.long_leg.strike:<5.0f} "
                      f"${s.net_premium:>6.2f} ${s.max_loss:>6.2f} {s.roi_pct:>5.1f}% "
                      f"{s.short_leg.delta or 0:>7.3f}")
        print()

    # --- Show filter failure breakdown ---
    print("--- FILTER FAILURE BREAKDOWN ---")
    fail_counts = {"DELTA": 0, "VOL/OI": 0, "IV_RANK": 0, "TREND": 0, "SUPPORT": 0}
    for r in all_results:
        for d in r["filter_details"]:
            if not d["passed"]:
                for reason in d["reasons"]:
                    if "FAIL" in reason:
                        for key in fail_counts:
                            if key in reason:
                                fail_counts[key] += 1
                                break

    total_fails = sum(fail_counts.values())
    if total_fails > 0:
        for key, count in fail_counts.items():
            pct = count / total_fails * 100
            bar = "#" * int(pct / 2)
            print(f"  {key:<10} {count:>6} ({pct:>5.1f}%) {bar}")
    else:
        print("  No failures (all legs passed or no data)")
    print()

    # --- Detailed filter reasons ---
    if args.detail:
        print("--- DETAILED FILTER LOG ---")
        for r in all_results:
            if not r["filter_details"]:
                continue
            failed = [d for d in r["filter_details"] if not d["passed"]]
            if failed:
                print(f"  [{r['time']}] {len(failed)} legs failed filters:")
                for d in failed[:10]:  # show first 10
                    fail_reasons = [r for r in d["reasons"] if "FAIL" in r]
                    print(f"    {d['strike']:.0f} {d['put_call']} d={d['delta']:.3f} "
                          f"iv={d['iv']:.1f} oi={d['oi']} vol={d['vol']}: "
                          f"{'; '.join(fail_reasons[:2])}")
                if len(failed) > 10:
                    print(f"    ... and {len(failed)-10} more")
        print()

    # --- Side-by-side comparison ---
    if args.compare:
        print("--- RAW vs FILTERED COMPARISON ---")
        print(f"{'Time':<8} {'Raw Legs':>10} {'Filtered':>10} {'Blocked':>10} | "
              f"{'Raw BP':>8} {'Filt BP':>8} | {'Raw BC':>8} {'Filt BC':>8}")
        print("-" * 85)
        for r in all_results:
            raw = r["raw_puts"] + r["raw_calls"]
            filt = r["filtered_puts"] + r["filtered_calls"]
            blocked = raw - filt
            rbp = len(r["raw_spreads"]["bull_put"])
            fbp = len(r["spreads"]["bull_put"])
            rbc = len(r["raw_spreads"]["bear_call"])
            fbc = len(r["spreads"]["bear_call"])
            print(f"{r['time']:<8} {raw:>10} {filt:>10} {blocked:>10} | "
                  f"{rbp:>8} {fbp:>8} | {rbc:>8} {fbc:>8}")

    conn.close()
    print()
    print("Done!")


if __name__ == "__main__":
    main()
