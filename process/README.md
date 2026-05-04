# process/ -- Nightly Research Reports

Generates a plain-text research report every evening summarizing options
market structure across SPY, QQQ, and (when available) IWM.

## What it covers

1. **VIX level** -- market regime (low/normal/elevated/fear)
2. **GEX walls** -- top strikes by absolute gamma exposure (dealer positioning)
3. **OI clusters** -- highest open interest strikes (pinning/magnet levels)
4. **GEX flip zones** -- zero-crossings where dealer behavior shifts
5. **Short gamma zones** -- negative GEX strikes that accelerate moves
6. **VEX hotspots** -- strikes most sensitive to IV changes
7. **DEX exposure** -- net delta exposure (directional positioning)
8. **Near-price analysis** -- 2% window around spot, aggregate positioning
9. **Day-over-day change** -- how positioning shifted from yesterday

## Usage

```bash
# Default: SPY + QQQ text report to stdout
python process/generate_nightly_report.py

# Save to file (creates reports/ dir)
python process/generate_nightly_report.py -o reports/report_2026-05-02.txt

# JSON output (for piping to other tools)
python process/generate_nightly_report.py --json

# Add IWM (needs data in DB first)
python process/generate_nightly_report.py --symbols SPY,QQQ,IWM
```

## Data sources

| Source        | What                          | Status       |
|---------------|-------------------------------|--------------|
| Schwab scraper -> Postgres | GEX, DEX, VEX, TEX, OI per strike | SPY, QQQ, $SPX active (1201 snapshots each) |
| VIX index level | Market regime context       | NOT in DB -- needs scraper enable or CBOE fetch |
| IWM options   | Russell 2000 positioning      | NOT in DB -- needs scraper enable |

## Adding IWM

Add to `TICKER_CONFIGS` in `scripts/options_scraper.py`:
```python
"IWM": {"strike_count": 50, "days": 14},
```

## Adding VIX

Option A: Enable VIX in the scraper (already configured but not running).
Option B: Fetch CBOE VIX daily close CSV and cache locally.

## Report interpretation

- **LONG GAMMA regime** (positive net GEX): dealers buy dips, sell rips. Mean-reverting, choppy. Good for premium selling.
- **SHORT GAMMA regime** (negative net GEX): dealers sell dips, buy rips. Trendy, momentum. Be careful selling premium.
- **GEX walls** act as magnets -- price tends to pin near big GEX clusters at expiry.
- **Flip zones** are inflection points. If price crosses from +GEX to -GEX territory, dealers flip from mean-revert to trend-adding behavior.
- **Short gamma zones** are accelerants. If SPY trades through a -$50B GEX strike, dealers must sell to hedge, fueling the move.
- **VEX hotspots** show where IV changes will cause the most hedging flow.
