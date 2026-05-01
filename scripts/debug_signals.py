"""Quick debug for signal generation."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gex.storage import get_connection
from algo.generators import generate_from_rows
from algo.config import GeneratorConfig

DB_URL = os.environ.get("DATABASE_URL", "postgresql://trader:changeme@localhost:5433/options")
conn = get_connection(DB_URL)
cur = conn.cursor()

# Get latest SPY snapshot
cur.execute("""
    SELECT id, underlying_price, captured_at
    FROM snapshots
    WHERE symbol = 'SPY'
    ORDER BY captured_at DESC
    LIMIT 1
""")
snap = cur.fetchone()
snap_id, price, ts = snap
print(f"Snapshot: id={snap_id}, price=${price}, ts={ts}")

# Get contracts
cur.execute("""
    SELECT underlying_symbol, strike, put_call, expiration_date, dte,
           bid, ask, mark, delta, gamma, theta, vega, volatility,
           open_interest, total_volume
    FROM option_contracts
    WHERE snapshot_id = %s
    AND delta IS NOT NULL
    ORDER BY put_call, dte, strike
""", [snap_id])

columns = [desc[0] for desc in cur.description]
rows = [dict(zip(columns, row)) for row in cur.fetchall()]
print(f"Total rows: {len(rows)}")

# Show a sample
if rows:
    print(f"\nSample row: {rows[0]}")

# Filter to DTE 5-9
in_range = [r for r in rows if r.get("dte") and 5 <= int(r["dte"] or 0) <= 9]
print(f"DTE 5-9: {len(in_range)}")

# Filter further: delta 0.10-0.20
delta_ok = [r for r in in_range if r.get("delta") and 0.10 <= abs(float(r["delta"])) <= 0.20]
print(f"Delta 0.10-0.20: {len(delta_ok)}")

# Try generating
cfg = GeneratorConfig()
cands = generate_from_rows(rows, float(price), cfg, str(ts))
print(f"\nCandidates generated: {len(cands)}")

# If 0, debug why
if not cands and delta_ok:
    print("\nDebugging a single row:")
    r = delta_ok[0]
    print(f"  {r['put_call']} strike={r['strike']} delta={r['delta']} dte={r['dte']}")
    print(f"  mark={r['mark']} bid={r['bid']} ask={r['ask']}")
    print(f"  oi={r['open_interest']} vol={r['total_volume']}")
    
    # Check if OTM
    if r["put_call"] == "PUT":
        otm = float(r["strike"]) < float(price)
        print(f"  OTM (strike < price)? {otm} ({r['strike']} < {price})")
    else:
        otm = float(r["strike"]) > float(price)
        print(f"  OTM (strike > price)? {otm} ({r['strike']} > {price})")
