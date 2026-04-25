"""
Spread Hunter Backtest — replays historical snapshots from April 17.

For each snapshot (every 5 min), builds spreads, scores them, then checks
how those spreads would have performed at the NEXT snapshot's prices.

Shows:
  1. What the spread hunter would have recommended at each timestamp
  2. How those spreads performed 5 min later, 30 min later, and at EOD
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import defaultdict
from spread_hunter.spread_builder import (
    SpreadHunterConfig, _row_to_leg, auto_width,
    _build_bull_put_credits, _build_bear_call_credits,
    _build_iron_condors, _build_iron_flys,
    group_contracts,
)
from spread_hunter.spread_scoring import score_all
from gex.storage import get_connection

DB_URL = os.environ.get("DATABASE_URL", "postgresql://trader:changeme@localhost:5433/options")
conn = get_connection(DB_URL)

# --- Config ---
TICKER = "SPY"
MAX_SPREADS_TO_TRADE = 5          # top 5 per type
MAX_VERTICALS_FOR_IC = 30         # cap verticals before IC combo (fixes the 229K problem)
TARGET_DTE = 7                    # focus on 7 DTE

# --- Fetch all snapshots for this ticker ---
cur = conn.cursor()
cur.execute("""
    SELECT id, symbol, underlying_price, captured_at
    FROM snapshots
    WHERE symbol = %s
    ORDER BY captured_at
""", (TICKER,))
snapshots = cur.fetchall()
print(f"Found {len(snapshots)} snapshots for {TICKER}")
print(f"Time range: {snapshots[0][3]} -> {snapshots[-1][3]}")
print(f"Price range: {snapshots[0][2]} -> {snapshots[-1][2]}")
print()

# --- For each snapshot, fetch contracts and build spreads ---
all_results = []

for snap_idx, (snap_id, symbol, underlying_price, captured_at) in enumerate(snapshots):
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
        continue

    config = SpreadHunterConfig(min_dte=TARGET_DTE, max_dte=TARGET_DTE, min_oi=10, min_volume=0)
    groups = group_contracts(rows)
    expirations = groups.get(TICKER, {})

    all_bull_puts = []
    all_bear_calls = []

    for exp, pc_map in expirations.items():
        puts = [p for p in pc_map.get("PUT", []) if config.min_dte <= p.dte <= config.max_dte]
        calls = [c for c in pc_map.get("CALL", []) if config.min_dte <= c.dte <= config.max_dte]

        bp = _build_bull_put_credits(puts, float(underlying_price), config)
        bc = _build_bear_call_credits(calls, float(underlying_price), config)
        all_bull_puts.extend(bp)
        all_bear_calls.extend(bc)

    # Score verticals
    raw = {
        "bull_put_credit": all_bull_puts,
        "bear_call_credit": all_bear_calls,
    }
    scored = score_all(raw)

    # Get top N per type
    top_bulls = scored["bull_put_credit"][:MAX_SPREADS_TO_TRADE]
    top_bears = scored["bear_call_credit"][:MAX_SPREADS_TO_TRADE]

    # Build ICs from top verticals only (capped)
    raw_ic = {
        "bull_put_credit": all_bull_puts[:MAX_VERTICALS_FOR_IC],
        "bear_call_credit": all_bear_calls[:MAX_VERTICALS_FOR_IC],
    }
    scored_ic_v = score_all(raw_ic)
    ics = _build_iron_condors(
        scored_ic_v["bull_put_credit"],
        scored_ic_v["bear_call_credit"],
        float(underlying_price),
        config,
    )
    # Score and top N
    for ic in ics:
        ic.score = (ic.roi_pct / 100.0) * 0.5 + (1.0 if ic.total_credit > 0 else 0)
    ics.sort(key=lambda x: x.score, reverse=True)
    top_ics = ics[:MAX_SPREADS_TO_TRADE]

    time_str = str(captured_at)[11:16] if captured_at else "??:??"
    all_results.append({
        "time": time_str,
        "price": float(underlying_price),
        "snap_idx": snap_idx,
        "bull_puts": top_bulls,
        "bear_calls": top_bears,
        "iron_condors": top_ics,
        "n_bull": len(all_bull_puts),
        "n_bear": len(all_bear_calls),
    })

# --- Display results ---
print("=" * 90)
print(f"  SPREAD HUNTER BACKTEST — {TICKER} — April 17, 2026 (After Hours)")
print(f"  Target DTE: {TARGET_DTE} | Top {MAX_SPREADS_TO_TRADE} per type")
print("=" * 90)

print()
print("--- BULL PUT CREDIT SPREADS (top pick at each timestamp) ---")
print(f"{'Time':<8} {'Price':>7} {'Sell/Buy':>12} {'Credit':>8} {'MaxLoss':>8} {'ROI%':>6} {'Score':>6} {'Candidates':>10}")
print("-" * 75)

for r in all_results:
    if r["bull_puts"]:
        s = r["bull_puts"][0]
        print(f"{r['time']:<8} {r['price']:>7.2f} {s.short_leg.strike:>5.0f}/{s.long_leg.strike:<5.0f} "
              f"${s.net_premium:>6.2f} ${s.max_loss:>6.2f} {s.roi_pct:>5.1f}% {s.score:>6.3f} {r['n_bull']:>10}")

# Track a specific spread over time
print()
print("--- TRACKING: Best 7-DTE bull put from first snapshot ---")
first_bull = all_results[0]["bull_puts"][0] if all_results[0]["bull_puts"] else None
if first_bull:
    sell_strike = first_bull.short_leg.strike
    buy_strike = first_bull.long_leg.strike
    entry_credit = first_bull.net_premium
    width = first_bull.strike_width

    print(f"  Spread: SELL {sell_strike} PUT / BUY {buy_strike} PUT")
    print(f"  Entry credit: ${entry_credit:.2f} | Width: ${width:.0f} | Max risk: ${width - entry_credit:.2f}")
    print()
    print(f"  {'Time':<8} {'Price':>7} {'Short Bid':>10} {'Long Ask':>10} {'Spread Val':>11} {'P&L':>8}")
    print("  " + "-" * 60)

    for r in all_results:
        # Find the matching strikes in this snapshot
        # Rebuild legs for this timestamp to get current prices
        snap_id = snapshots[r["snap_idx"]][0]
        cur.execute("""
            SELECT strike, put_call, bid, ask, mark, delta
            FROM option_contracts
            WHERE snapshot_id = %s AND put_call = 'PUT'
            AND strike IN (%s, %s)
            AND dte = %s
        """, (snap_id, sell_strike, buy_strike, TARGET_DTE))
        leg_rows = cur.fetchall()

        short_bid = long_ask = None
        for row in leg_rows:
            strike, pc, bid, ask, mark, delta = row
            if abs(strike - sell_strike) < 0.01:
                short_bid = float(bid or mark or 0)
            if abs(strike - buy_strike) < 0.01:
                long_ask = float(ask or mark or 0)

        if short_bid is not None and long_ask is not None:
            # To close: buy back short (pay ask or mid), sell long (receive bid or mid)
            # Using mid prices for fair value
            short_mid = (short_bid + (short_bid + 0.05)) / 2 if short_bid else 0  # approximate
            long_mid = (long_ask + (long_ask - 0.05)) / 2 if long_ask else 0      # approximate
            spread_mid = long_mid - short_mid  # cost to close
            # P&L = credit received - cost to close
            # Cost to close = buy short back at mid - sell long at mid
            close_cost = short_mid - long_mid  # what you pay to close
            pnl = entry_credit - close_cost
            pnl_pct = (pnl / (width - entry_credit)) * 100 if (width - entry_credit) > 0 else 0

            print(f"  {r['time']:<8} {r['price']:>7.2f} ${short_bid:>8.2f} ${long_ask:>8.2f} "
                  f"${short_mid - long_mid:>9.2f} ${pnl:>7.2f}")

print()

# Bear call summary
print("--- BEAR CALL CREDIT SPREADS (top pick at each timestamp) ---")
print(f"{'Time':<8} {'Price':>7} {'Sell/Buy':>12} {'Credit':>8} {'MaxLoss':>8} {'ROI%':>6} {'Score':>6}")
print("-" * 65)

for r in all_results:
    if r["bear_calls"]:
        s = r["bear_calls"][0]
        print(f"{r['time']:<8} {r['price']:>7.2f} {s.short_leg.strike:>5.0f}/{s.long_leg.strike:<5.0f} "
              f"${s.net_premium:>6.2f} ${s.max_loss:>6.2f} {s.roi_pct:>5.1f}% {s.score:>6.3f}")

print()

# Iron Condor summary
print("--- IRON CONDORS (top pick at each timestamp) ---")
print(f"{'Time':<8} {'Price':>7} {'Put Wing':>14} {'Call Wing':>14} {'Credit':>8} {'ROI%':>6}")
print("-" * 70)

for r in all_results:
    if r["iron_condors"]:
        ic = r["iron_condors"][0]
        print(f"{r['time']:<8} {r['price']:>7.2f} "
              f"{ic.put_short.strike:>5.0f}/{ic.put_long.strike:<5.0f}  "
              f"{ic.call_short.strike:>5.0f}/{ic.call_long.strike:<5.0f}  "
              f"${ic.total_credit:>6.2f} {ic.roi_pct:>5.1f}%")

# Summary stats
print()
print("=" * 90)
print("  SUMMARY")
print("=" * 90)
bulls_with_data = [r for r in all_results if r["bull_puts"]]
if bulls_with_data:
    first = bulls_with_data[0]["bull_puts"][0]
    last = bulls_with_data[-1]["bull_puts"][0]
    print(f"  Bull Put top pick consistency:")
    print(f"    Opening: SELL {first.short_leg.strike}/{first.long_leg.strike} @ ${first.net_premium:.2f}")
    print(f"    Closing:  SELL {last.short_leg.strike}/{last.long_leg.strike} @ ${last.net_premium:.2f}")
    print(f"    Credit change: ${last.net_premium - first.net_premium:+.2f}")

bears_with_data = [r for r in all_results if r["bear_calls"]]
if bears_with_data:
    first = bears_with_data[0]["bear_calls"][0]
    last = bears_with_data[-1]["bear_calls"][0]
    print(f"  Bear Call top pick consistency:")
    print(f"    Opening: SELL {first.short_leg.strike}/{first.long_leg.strike} @ ${first.net_premium:.2f}")
    print(f"    Closing:  SELL {last.short_leg.strike}/{last.long_leg.strike} @ ${last.net_premium:.2f}")
    print(f"    Credit change: ${last.net_premium - first.net_premium:+.2f}")

conn.close()
print()
print("Done!")
