"""Quick test with $3 width to fit current scraped data range."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gex.storage import get_connection
from algo.generators import generate_from_rows
from algo.config import GeneratorConfig

DB_URL = os.environ.get("DATABASE_URL", "postgresql://trader:changeme@localhost:5433/options")
conn = get_connection(DB_URL)
cur = conn.cursor()

cur.execute("""
    SELECT id, underlying_price, captured_at
    FROM snapshots WHERE symbol = 'SPY'
    ORDER BY captured_at DESC LIMIT 1
""")
snap_id, price, ts = cur.fetchone()

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

print(f"SPY @ ${price} | {len(rows)} contracts | snapshot {ts}")
print(f"Strike range: {min(r['strike'] for r in rows)} - {max(r['strike'] for r in rows)}")

# Test with $3 width
cfg = GeneratorConfig(strike_width=3.0)
cands = generate_from_rows(rows, float(price), cfg, str(ts))
print(f"\n$3 width candidates: {len(cands)}")
for c in cands:
    print(f"  {c.spread_type:20s} | {c.short_strike:.0f}/{c.long_strike:.0f} | "
          f"DTE={c.dte} | Δ={abs(c.short_delta or 0):.3f} | "
          f"Credit=${c.credit:.2f} | ROC={c.roc_pct:.0f}% | "
          f"Width=${c.strike_width:.0f}")

# Also test $2 width
cfg2 = GeneratorConfig(strike_width=2.0)
cands2 = generate_from_rows(rows, float(price), cfg2, str(ts))
print(f"\n$2 width candidates: {len(cands2)}")
for c in cands2:
    print(f"  {c.spread_type:20s} | {c.short_strike:.0f}/{c.long_strike:.0f} | "
          f"DTE={c.dte} | Δ={abs(c.short_delta or 0):.3f} | "
          f"Credit=${c.credit:.2f} | ROC={c.roc_pct:.0f}% | "
          f"Width=${c.strike_width:.0f}")
