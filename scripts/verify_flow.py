import os, sys
for line in open('.env'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k, v)

sys.path.insert(0, '.')
import yaml
import psycopg

# Load watchlist
with open('config/watchlist.yaml') as f:
    cfg = yaml.safe_load(f)

core = cfg.get('core', {})
tickers = []
for sector_name, tickers_list in core.items():
    if not isinstance(tickers_list, list):
        continue
    for t in tickers_list:
        if isinstance(t, dict):
            tickers.append(t)
        elif isinstance(t, str):
            tickers.append({"symbol": t, "sector": sector_name})

sector_map = {t["symbol"]: t.get("sector", "unknown") for t in tickers}
symbol_list = list(sector_map.keys())
placeholders = ", ".join(["%s"] * len(symbol_list))

# Connect
db_url = os.environ.get("DATABASE_URL", "")
conn = psycopg.connect(db_url)

# Get latest snapshot per symbol
latest_snaps = conn.execute(f"""
    SELECT DISTINCT ON (symbol) id, symbol, captured_at, underlying_price
    FROM snapshots
    WHERE symbol IN ({placeholders})
    ORDER BY symbol, captured_at DESC
""", symbol_list).fetchall()

snap_ids = [r[0] for r in latest_snaps]
snap_id_placeholders = ", ".join(["%s"] * len(snap_ids))

print(f"Latest snapshots: {len(snap_ids)} symbols")
for r in latest_snaps:
    print(f"  {r[1]:<6} snap_id={r[0]}  captured={r[2]}")

# Fetch all contracts
rows = conn.execute(f"""
    SELECT s.symbol, oc.put_call, oc.strike, oc.total_volume, oc.open_interest,
           oc.mark, s.underlying_price, oc.in_the_money
    FROM option_contracts oc
    JOIN snapshots s ON oc.snapshot_id = s.id
    WHERE s.id IN ({snap_id_placeholders})
""", snap_ids).fetchall()

# Aggregate per sector
sector_data = {}
ticker_breakdown = {}

for row in rows:
    symbol, pc, strike, vol, oi, mark, spot, itm = row
    sector = sector_map.get(symbol, "unknown")
    if sector not in sector_data:
        sector_data[sector] = {
            "call_vol": 0, "put_vol": 0, "call_oi": 0, "put_oi": 0,
            "otm_vol": 0, "total_vol": 0, "premium": 0.0,
        }

    vol = int(vol or 0)
    oi = int(oi or 0)
    mark_f = float(mark or 0)
    spot_f = float(spot or 0)

    if pc == "CALL":
        sector_data[sector]["call_vol"] += vol
        sector_data[sector]["call_oi"] += oi
    elif pc == "PUT":
        sector_data[sector]["put_vol"] += vol
        sector_data[sector]["put_oi"] += oi

    # OTM check
    if pc == "CALL" and spot_f > 0 and strike > spot_f:
        sector_data[sector]["otm_vol"] += vol
    elif pc == "PUT" and spot_f > 0 and strike < spot_f:
        sector_data[sector]["otm_vol"] += vol

    sector_data[sector]["total_vol"] += vol
    sector_data[sector]["premium"] += vol * mark_f

    # Ticker breakdown
    if symbol not in ticker_breakdown:
        ticker_breakdown[symbol] = {"call_vol": 0, "put_vol": 0, "sector": sector, "spot": spot_f}
    if pc == "CALL":
        ticker_breakdown[symbol]["call_vol"] += vol
    elif pc == "PUT":
        ticker_breakdown[symbol]["put_vol"] += vol

print(f"\n{'='*120}")
print(f"SECTOR FLOW VERIFICATION — {latest_snaps[0][2] if latest_snaps else 'N/A'}")
print(f"{'='*120}\n")

for sector in sorted(sector_data.keys()):
    d = sector_data[sector]
    cv = d["call_vol"]
    pv = d["put_vol"]
    co = d["call_oi"]
    po = d["put_oi"]
    tv = d["total_vol"]
    ov = d["otm_vol"]
    prem = d["premium"]
    pcr = round(pv/cv, 2) if cv > 0 else None
    pcr_oi = round(po/co, 2) if co > 0 else None
    otm_r = round(ov/tv, 2) if tv > 0 else None

    if pcr is not None:
        if pcr < 0.7:
            direction = "BULLISH (PCR < 0.7)"
        elif pcr > 1.3:
            direction = "BEARISH (PCR > 1.3)"
        else:
            direction = "NEUTRAL"
    else:
        direction = "N/A"

    print(f"--- {sector.upper()} ---")
    print(f"  Call Volume:   {cv:>12,}")
    print(f"  Put Volume:    {pv:>12,}")
    print(f"  Total Volume:  {tv:>12,}")
    print(f"  Call OI:       {co:>12,}")
    print(f"  Put OI:        {po:>12,}")
    print(f"  PCR (volume):  {pcr}")
    print(f"  PCR (OI):      {pcr_oi}")
    print(f"  OTM Volume:    {ov:>12,}")
    print(f"  OTM Ratio:     {otm_r}")
    print(f"  Premium Flow:  ${prem:>14,.0f}")
    print(f"  Direction:     {direction}")
    print()

# Ticker breakdown for top sectors
print(f"{'='*120}")
print(f"TOP TICKER BREAKDOWN")
print(f"{'='*120}\n")

for sym in sorted(ticker_breakdown.keys()):
    tb = ticker_breakdown[sym]
    cv = tb["call_vol"]
    pv = tb["put_vol"]
    pcr = round(pv/cv, 2) if cv > 0 else None
    print(f"  {sym:<6} [{tb['sector']:<20}] Calls: {cv:>10,} Puts: {pv:>10,} PCR: {pcr} Spot: {tb['spot']}")

conn.close()
