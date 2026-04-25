"""
Spread Hunter — TOS Trade Log
Prints each recommended spread with full leg details formatted for manual entry in ThinkOrSwim.
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
cur = conn.cursor()

# Get latest SPY snapshot
cur.execute("""
    SELECT id, symbol, underlying_price, captured_at
    FROM snapshots
    WHERE symbol = 'SPY'
    ORDER BY captured_at DESC
    LIMIT 1
""")
snap_id, symbol, underlying_price, captured_at = cur.fetchone()
print(f"Data from: {captured_at}")
print(f"SPY last: ${underlying_price}")
print()

# Fetch contracts for 7 DTE
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

def expiry_to_tos(expiry_str):
    """Convert '2026-04-24T20:00:00.000+00:00' to '04/24/2026' for TOS."""
    return expiry_str[:10].replace("-", "/")

def strike_to_tos_sym(underlying, expiry_str, put_call, strike):
    """Build OCC-style symbol: SPY_042426P710"""
    exp_date = expiry_str[:10]
    parts = exp_date.split("-")
    yy = parts[0][2:]   # 26
    mm = parts[1]       # 04
    dd = parts[2]       # 24
    pc = "C" if put_call == "CALL" else "P"
    # Strike as 8-digit with leading zeros, 3 decimal places
    strike_int = int(strike * 1000)
    strike_str = f"{strike_int:08d}"
    return f"{underlying}_{mm}{dd}{yy}{pc}{strike_str}"

config = SpreadHunterConfig(min_dte=7, max_dte=7, min_oi=10, min_volume=0)
groups = group_contracts(rows)
expirations = groups.get("SPY", {})

price = float(underlying_price)

# Build all spread types
all_bulls = []
all_bears = []
for exp, pc_map in expirations.items():
    puts = [p for p in pc_map.get("PUT", []) if config.min_dte <= p.dte <= config.max_dte]
    calls = [c for c in pc_map.get("CALL", []) if config.min_dte <= c.dte <= config.max_dte]
    all_bulls.extend(_build_bull_put_credits(puts, price, config))
    all_bears.extend(_build_bear_call_credits(calls, price, config))

raw = {"bull_put_credit": all_bulls, "bear_call_credit": all_bears}
scored = score_all(raw)

# Build ICs from top 30 each
ics = _build_iron_condors(scored["bull_put_credit"][:30], scored["bear_call_credit"][:30], price, config)
for ic in ics:
    ic.score = (ic.roi_pct / 100.0) * 0.5 + (1.0 if ic.total_credit > 0 else 0)
ics.sort(key=lambda x: x.score, reverse=True)

# ============================================================================
# PRINT TRADE LOG
# ============================================================================
TOP_N = 3

separator = "=" * 95

# --- BULL PUT CREDIT SPREADS ---
print(separator)
print("  BULL PUT CREDIT SPREADS  (sell higher put, buy lower put)")
print(f"  SPY @ ${price:.2f} | Exp: 7 DTE (Apr 24) | Top {TOP_N}")
print(separator)
print()

for i, s in enumerate(scored["bull_put_credit"][:TOP_N], 1):
    expiry_tos = expiry_to_tos(s.short_leg.expiration_date)
    short_sym = strike_to_tos_sym("SPY", s.short_leg.expiration_date, "PUT", s.short_leg.strike)
    long_sym = strike_to_tos_sym("SPY", s.long_leg.expiration_date, "PUT", s.long_leg.strike)
    
    print(f"  #{i}  Score: {s.score:.3f}")
    print(f"  ┌─────────────────────────────────────────────────────────────────────────┐")
    print(f"  │  SELL  {s.short_leg.strike:>6.0f} PUT  {short_sym}")
    print(f"  │    Bid: ${s.short_leg.bid:.2f}  Ask: ${s.short_leg.ask:.2f}  Mark: ${s.short_leg.mark:.2f}")
    print(f"  │    Delta: {s.short_leg.delta:.3f}  IV: {s.short_leg.iv:.1f}%  OI: {s.short_leg.open_interest:,}  Vol: {s.short_leg.volume:,}")
    print(f"  │")
    print(f"  │  BUY   {s.long_leg.strike:>6.0f} PUT  {long_sym}")
    print(f"  │    Bid: ${s.long_leg.bid:.2f}  Ask: ${s.long_leg.ask:.2f}  Mark: ${s.long_leg.mark:.2f}")
    print(f"  │    Delta: {s.long_leg.delta:.3f}  IV: {s.long_leg.iv:.1f}%  OI: {s.long_leg.open_interest:,}  Vol: {s.long_leg.volume:,}")
    print(f"  │")
    print(f"  │  Expiration: {expiry_tos} ({s.dte} DTE)")
    print(f"  │  Width: ${s.strike_width:.0f}")
    print(f"  │  Net Credit: ${s.net_premium:.2f} (x100 = ${s.net_premium*100:.0f} per contract)")
    print(f"  │  Max Profit: ${s.max_profit:.2f} (x100 = ${s.max_profit*100:.0f})")
    print(f"  │  Max Loss:   ${s.max_loss:.2f} (x100 = ${s.max_loss*100:.0f})")
    print(f"  │  Breakeven:  ${s.breakeven:.2f}")
    print(f"  │  ROI:        {s.roi_pct:.1f}%")
    print(f"  │  Net Delta:  {s.net_delta:.4f}  Net Theta: {s.net_theta:.4f}")
    print(f"  └─────────────────────────────────────────────────────────────────────────┘")
    print()

# --- BEAR CALL CREDIT SPREADS ---
print(separator)
print("  BEAR CALL CREDIT SPREADS  (sell lower call, buy higher call)")
print(f"  SPY @ ${price:.2f} | Exp: 7 DTE (Apr 24) | Top {TOP_N}")
print(separator)
print()

for i, s in enumerate(scored["bear_call_credit"][:TOP_N], 1):
    short_sym = strike_to_tos_sym("SPY", s.short_leg.expiration_date, "CALL", s.short_leg.strike)
    long_sym = strike_to_tos_sym("SPY", s.long_leg.expiration_date, "CALL", s.long_leg.strike)
    
    print(f"  #{i}  Score: {s.score:.3f}")
    print(f"  ┌─────────────────────────────────────────────────────────────────────────┐")
    print(f"  │  SELL  {s.short_leg.strike:>6.0f} CALL {short_sym}")
    print(f"  │    Bid: ${s.short_leg.bid:.2f}  Ask: ${s.short_leg.ask:.2f}  Mark: ${s.short_leg.mark:.2f}")
    print(f"  │    Delta: {s.short_leg.delta:.3f}  IV: {s.short_leg.iv:.1f}%  OI: {s.short_leg.open_interest:,}  Vol: {s.short_leg.volume:,}")
    print(f"  │")
    print(f"  │  BUY   {s.long_leg.strike:>6.0f} CALL {long_sym}")
    print(f"  │    Bid: ${s.long_leg.bid:.2f}  Ask: ${s.long_leg.ask:.2f}  Mark: ${s.long_leg.mark:.2f}")
    print(f"  │    Delta: {s.long_leg.delta:.3f}  IV: {s.long_leg.iv:.1f}%  OI: {s.long_leg.open_interest:,}  Vol: {s.long_leg.volume:,}")
    print(f"  │")
    print(f"  │  Expiration: {expiry_to_tos(s.short_leg.expiration_date)} ({s.dte} DTE)")
    print(f"  │  Width: ${s.strike_width:.0f}")
    print(f"  │  Net Credit: ${s.net_premium:.2f} (x100 = ${s.net_premium*100:.0f} per contract)")
    print(f"  │  Max Profit: ${s.max_profit:.2f} (x100 = ${s.max_profit*100:.0f})")
    print(f"  │  Max Loss:   ${s.max_loss:.2f} (x100 = ${s.max_loss*100:.0f})")
    print(f"  │  Breakeven:  ${s.breakeven:.2f}")
    print(f"  │  ROI:        {s.roi_pct:.1f}%")
    print(f"  │  Net Delta:  {s.net_delta:.4f}  Net Theta: {s.net_theta:.4f}")
    print(f"  └─────────────────────────────────────────────────────────────────────────┘")
    print()

# --- IRON CONDORS ---
print(separator)
print("  IRON CONDORS  (bull put + bear call, same expiry)")
print(f"  SPY @ ${price:.2f} | Exp: 7 DTE (Apr 24) | Top {TOP_N}")
print(separator)
print()

for i, ic in enumerate(ics[:TOP_N], 1):
    ps_sym = strike_to_tos_sym("SPY", ic.put_short.expiration_date, "PUT", ic.put_short.strike)
    pl_sym = strike_to_tos_sym("SPY", ic.put_long.expiration_date, "PUT", ic.put_long.strike)
    cs_sym = strike_to_tos_sym("SPY", ic.call_short.expiration_date, "CALL", ic.call_short.strike)
    cl_sym = strike_to_tos_sym("SPY", ic.call_long.expiration_date, "CALL", ic.call_long.strike)
    
    print(f"  #{i}  Score: {ic.score:.3f}")
    print(f"  ┌─────────────────────────────────────────────────────────────────────────┐")
    print(f"  │  LEG 1 - SELL  {ic.put_short.strike:>6.0f} PUT  {ps_sym}")
    print(f"  │    Bid: ${ic.put_short.bid:.2f}  Ask: ${ic.put_short.ask:.2f}  Delta: {ic.put_short.delta:.3f}  OI: {ic.put_short.open_interest:,}")
    print(f"  │")
    print(f"  │  LEG 2 - BUY   {ic.put_long.strike:>6.0f} PUT  {pl_sym}")
    print(f"  │    Bid: ${ic.put_long.bid:.2f}  Ask: ${ic.put_long.ask:.2f}  Delta: {ic.put_long.delta:.3f}  OI: {ic.put_long.open_interest:,}")
    print(f"  │")
    print(f"  │  LEG 3 - SELL  {ic.call_short.strike:>6.0f} CALL {cs_sym}")
    print(f"  │    Bid: ${ic.call_short.bid:.2f}  Ask: ${ic.call_short.ask:.2f}  Delta: {ic.call_short.delta:.3f}  OI: {ic.call_short.open_interest:,}")
    print(f"  │")
    print(f"  │  LEG 4 - BUY   {ic.call_long.strike:>6.0f} CALL {cl_sym}")
    print(f"  │    Bid: ${ic.call_long.bid:.2f}  Ask: ${ic.call_long.ask:.2f}  Delta: {ic.call_long.delta:.3f}  OI: {ic.call_long.open_interest:,}")
    print(f"  │")
    print(f"  │  Expiration: {expiry_to_tos(ic.expiration_date)} ({ic.dte} DTE)")
    print(f"  │  Put Width: ${ic.put_width:.0f}  |  Call Width: ${ic.call_width:.0f}")
    print(f"  │  Put Credit:  ${ic.put_credit:.2f}")
    print(f"  │  Call Credit: ${ic.call_credit:.2f}")
    print(f"  │  TOTAL Credit: ${ic.total_credit:.2f} (x100 = ${ic.total_credit*100:.0f})")
    print(f"  │  Max Loss:   ${ic.max_loss:.2f} (x100 = ${ic.max_loss*100:.0f})")
    print(f"  │  Breakeven Low:  ${ic.breakeven_low:.2f}")
    print(f"  │  Breakeven High: ${ic.breakeven_high:.2f}")
    print(f"  │  Range: ${ic.breakeven_low:.2f} to ${ic.breakeven_high:.2f} ({ic.breakeven_high - ic.breakeven_low:.2f} wide)")
    print(f"  │  ROI: {ic.roi_pct:.1f}%")
    print(f"  └─────────────────────────────────────────────────────────────────────────┘")
    print()

# --- QUICK REFERENCE for TOS entry ---
print(separator)
print("  QUICK REFERENCE — Copy into TOS")
print(separator)
print()
print("  In TOS: Analyze tab -> Add simulated trades, or use the Trade tab")
print()
print("  BULL PUT #1:")
bp1 = scored["bull_put_credit"][0]
print(f"    SELL -1 SPY {expiry_to_tos(bp1.short_leg.expiration_date)} {bp1.short_leg.strike:.0f} PUT")
print(f"    BUY  +1 SPY {expiry_to_tos(bp1.long_leg.expiration_date)} {bp1.long_leg.strike:.0f} PUT")
print(f"    Net credit: ${bp1.net_premium:.2f} | Breakeven: ${bp1.breakeven:.2f} | ROI: {bp1.roi_pct:.1f}%")
print()
print("  BEAR CALL #1:")
bc1 = scored["bear_call_credit"][0]
print(f"    SELL -1 SPY {expiry_to_tos(bc1.short_leg.expiration_date)} {bc1.short_leg.strike:.0f} CALL")
print(f"    BUY  +1 SPY {expiry_to_tos(bc1.long_leg.expiration_date)} {bc1.long_leg.strike:.0f} CALL")
print(f"    Net credit: ${bc1.net_premium:.2f} | Breakeven: ${bc1.breakeven:.2f} | ROI: {bc1.roi_pct:.1f}%")
print()
if ics:
    ic1 = ics[0]
    print("  IRON CONDOR #1:")
    print(f"    SELL -1 SPY {expiry_to_tos(ic1.put_short.expiration_date)} {ic1.put_short.strike:.0f} PUT")
    print(f"    BUY  +1 SPY {expiry_to_tos(ic1.put_long.expiration_date)} {ic1.put_long.strike:.0f} PUT")
    print(f"    SELL -1 SPY {expiry_to_tos(ic1.call_short.expiration_date)} {ic1.call_short.strike:.0f} CALL")
    print(f"    BUY  +1 SPY {expiry_to_tos(ic1.call_long.expiration_date)} {ic1.call_long.strike:.0f} CALL")
    print(f"    Total credit: ${ic1.total_credit:.2f} | Range: ${ic1.breakeven_low:.2f}-${ic1.breakeven_high:.2f} | ROI: {ic1.roi_pct:.1f}%")

conn.close()
print()
print("Done!")
