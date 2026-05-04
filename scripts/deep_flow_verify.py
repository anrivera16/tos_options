import os, sys
for line in open('.env'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k, v)

sys.path.insert(0, '.')
import yaml
import psycopg

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

# Fetch ALL contract data for deep analysis
rows = conn.execute(f"""
    SELECT s.symbol, oc.put_call, oc.strike, oc.total_volume, oc.open_interest,
           oc.mark, oc.bid, oc.ask, s.underlying_price, oc.volatility,
           oc.theoretical_option_value, oc.delta, oc.dte
    FROM option_contracts oc
    JOIN snapshots s ON oc.snapshot_id = s.id
    WHERE s.id IN ({snap_id_placeholders})
    AND oc.delta IS NOT NULL
""", snap_ids).fetchall()

# Deep aggregation per sector
sector_data = {}
for row in rows:
    symbol, pc, strike, vol, oi, mark, bid, ask, spot, iv, theo, delta, dte = row
    sector = sector_map.get(symbol, "unknown")
    if sector not in sector_data:
        sector_data[sector] = {
            # Volume
            "call_vol": 0, "put_vol": 0, "call_oi": 0, "put_oi": 0,
            "otm_call_vol": 0, "otm_put_vol": 0, "atm_vol": 0,
            # Premium
            "call_premium": 0.0, "put_premium": 0.0,
            "total_premium": 0.0,
            # IV
            "call_iv_sum": 0.0, "call_iv_count": 0,
            "put_iv_sum": 0.0, "put_iv_count": 0,
            # Spread
            "spread_sum": 0.0, "spread_count": 0,
            # Volume/OI
            "total_contracts_with_oi": 0,
            # Strike concentration
            "strike_volumes": {},
            # DTE split
            "near_term_vol": 0,  # DTE 0-7
            "mid_term_vol": 0,   # DTE 8-30
            "far_term_vol": 0,   # DTE 30+
            # Mispricing
            "misprice_sum": 0.0, "misprice_count": 0,
        }

    vol = int(vol or 0)
    oi = int(oi or 0)
    mark_f = float(mark or 0)
    bid_f = float(bid or 0)
    ask_f = float(ask or 0)
    spot_f = float(spot or 0)
    iv_f = float(iv or 0)
    theo_f = float(theo or 0) if theo else None
    delta_f = float(delta or 0)
    dte_i = int(dte or 0)

    d = sector_data[sector]

    # Volume by type
    if pc == "CALL":
        d["call_vol"] += vol
        d["call_oi"] += oi
        d["call_premium"] += vol * mark_f
        if iv_f > 0:
            d["call_iv_sum"] += iv_f
            d["call_iv_count"] += 1
    elif pc == "PUT":
        d["put_vol"] += vol
        d["put_oi"] += oi
        d["put_premium"] += vol * mark_f
        if iv_f > 0:
            d["put_iv_sum"] += iv_f
            d["put_iv_count"] += 1

    d["total_premium"] += vol * mark_f

    # OTM/ATM classification
    if spot_f > 0:
        dist_pct = abs(strike - spot_f) / spot_f * 100
        if dist_pct < 1.0:
            d["atm_vol"] += vol
            if pc == "CALL":
                d["otm_call_vol"] += 0  # ATM not OTM
            else:
                d["otm_put_vol"] += 0
        else:
            if pc == "CALL" and strike > spot_f:
                d["otm_call_vol"] += vol
            elif pc == "PUT" and strike < spot_f:
                d["otm_put_vol"] += vol

    # Bid/ask spread
    if ask_f > 0 and bid_f > 0:
        spread = ask_f - bid_f
        d["spread_sum"] += spread
        d["spread_count"] += 1

    # OI tracking
    if oi > 0:
        d["total_contracts_with_oi"] += 1

    # Strike concentration
    strike_key = round(strike, 0)
    d["strike_volumes"][strike_key] = d["strike_volumes"].get(strike_key, 0) + vol

    # DTE split
    if dte_i <= 7:
        d["near_term_vol"] += vol
    elif dte_i <= 30:
        d["mid_term_vol"] += vol
    else:
        d["far_term_vol"] += vol

    # Mispricing
    if theo_f and mark_f and theo_f > 0:
        mispct = ((mark_f - theo_f) / theo_f) * 100
        d["misprice_sum"] += mispct
        d["misprice_count"] += 1

print(f"{'='*130}")
print(f"DETAILED SECTOR FLOW ANALYSIS — {latest_snaps[0][2] if latest_snaps else 'N/A'}")
print(f"Total tickers analyzed: {len(snap_ids)} | Total contracts: {len(rows)}")
print(f"{'='*130}\n")

for sector in sorted(sector_data.keys()):
    d = sector_data[sector]
    cv = d["call_vol"]
    pv = d["put_vol"]
    co = d["call_oi"]
    po = d["put_oi"]
    tv = cv + pv
    cp = d["call_premium"]
    pp = d["put_premium"]
    tp = d["total_premium"]

    pcr_v = round(pv/cv, 2) if cv > 0 else None
    pcr_o = round(po/co, 2) if co > 0 else None

    avg_call_iv = round(d["call_iv_sum"]/d["call_iv_count"], 1) if d["call_iv_count"] > 0 else None
    avg_put_iv = round(d["put_iv_sum"]/d["put_iv_count"], 1) if d["put_iv_count"] > 0 else None
    iv_skew = round(avg_put_iv - avg_call_iv, 1) if (avg_put_iv and avg_call_iv) else None

    avg_spread = round(d["spread_sum"]/d["spread_count"], 4) if d["spread_count"] > 0 else None

    otm_call = d["otm_call_vol"]
    otm_put = d["otm_put_vol"]
    atm = d["atm_vol"]
    otm_total = otm_call + otm_put

    avg_misprice = round(d["misprice_sum"]/d["misprice_count"], 2) if d["misprice_count"] > 0 else None

    # Top 5 strike concentration
    sorted_strikes = sorted(d["strike_volumes"].items(), key=lambda x: x[1], reverse=True)
    top5_vol = sum(v for _, v in sorted_strikes[:5])
    top5_pct = round(top5_vol/tv*100, 1) if tv > 0 else 0
    top5_strikes = ", ".join([f"${s:.0f}({v/1000:.0f}K)" for s, v in sorted_strikes[:5]])

    # DTE split
    near_pct = round(d["near_term_vol"]/tv*100, 1) if tv > 0 else 0
    mid_pct = round(d["mid_term_vol"]/tv*100, 1) if tv > 0 else 0
    far_pct = round(d["far_term_vol"]/tv*100, 1) if tv > 0 else 0

    # Volume/OI ratio
    total_oi = co + po
    vol_oi_ratio = round(tv/total_oi, 2) if total_oi > 0 else None

    print(f"{'='*130}")
    print(f"  {sector.upper()}")
    print(f"{'='*130}")
    print(f"  VOLUME & POSITIONING")
    print(f"    Call Volume:    {cv:>12,}  ({cv/tv*100:.1f}%)  |  Call Premium:    ${cp:>12,.0f}")
    print(f"    Put Volume:     {pv:>12,}  ({pv/tv*100:.1f}%)  |  Put Premium:     ${pp:>12,.0f}")
    print(f"    Total Volume:   {tv:>12,}                       |  Total Premium:   ${tp:>12,.0f}")
    print(f"    Call OI:        {co:>12,}                       |  Put OI:          {po:>12,}")
    print(f"    PCR (vol):      {pcr_v}                       |  PCR (OI):        {pcr_o}")
    if pcr_v is not None:
        if pcr_v < 0.7:
            print(f"    Direction:      BULLISH (put/call ratio < 0.7)")
        elif pcr_v > 1.3:
            print(f"    Direction:      BEARISH (put/call ratio > 1.3)")
        else:
            print(f"    Direction:      NEUTRAL")
    print()
    print(f"  IMPLIED VOLATILITY")
    print(f"    Avg Call IV:    {avg_call_iv if avg_call_iv else 'N/A':>12}  |  Avg Put IV:      {avg_put_iv if avg_put_iv else 'N/A'}")
    print(f"    IV Skew:        {iv_skew if iv_skew is not None else 'N/A':>12}  (put IV - call IV, positive = fear premium)")
    print(f"    Avg Mispricing: {avg_misprice if avg_misprice is not None else 'N/A':>12}%  (mark vs theoretical, + = expensive, - = cheap)")
    print()
    print(f"  LIQUIDITY & FLOW")
    print(f"    Avg Bid/Ask:    ${avg_spread if avg_spread else 'N/A':>10}  |  Vol/OI Ratio:    {vol_oi_ratio if vol_oi_ratio else 'N/A'}")
    print(f"    ATM Volume:     {atm:>12,}  ({atm/tv*100:.1f}%)  |  OTM Volume:      {otm_total:>10,}  ({otm_total/tv*100:.1f}%)")
    print(f"    OTM Calls:      {otm_call:>12,}  |  OTM Puts:        {otm_put:>12,}")
    print(f"    Top 5 Strikes:  {top5_pct:.1f}% of total volume → {top5_strikes}")
    print()
    print(f"  DTE DISTRIBUTION")
    print(f"    Near-term (0-7d):  {d['near_term_vol']:>10,}  ({near_pct:.1f}%)")
    print(f"    Mid-term (8-30d):  {d['mid_term_vol']:>10,}  ({mid_pct:.1f}%)")
    print(f"    Far-term (30d+):   {d['far_term_vol']:>10,}  ({far_pct:.1f}%)")
    print()

conn.close()
