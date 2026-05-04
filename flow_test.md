# Sector Flow Logic Verification

> Test run against live database — 2026-05-01 23:55 UTC snapshot
> Script: `scripts/verify_flow.py` — manual SQL query, not using the scanner module
> Purpose: Verify flow calculations are correct by independently computing from raw data

---

## Raw Data Summary

**Latest snapshots found: 20 out of 30 core tickers**

| Ticker | Sector | Snapshot Date | Age |
|--------|--------|--------------|-----|
| $SPX | indexes | 2026-05-01 23:55 UTC | Fresh |
| SPY | indexes | 2026-05-01 23:55 UTC | Fresh |
| QQQ | indexes | 2026-05-01 23:55 UTC | Fresh |
| AAPL | mega_cap_tech | 2026-05-01 23:55 UTC | Fresh |
| MSFT | mega_cap_tech | 2026-04-30 18:30 UTC | ~1 day old |
| GOOGL | mega_cap_tech | 2026-05-01 13:15 UTC | ~1 day old |
| META | mega_cap_tech | 2026-05-01 13:15 UTC | ~1 day old |
| AMZN | mega_cap_tech | 2026-04-30 17:01 UTC | ~1 day old |
| NVDA | semiconductors | 2026-05-01 13:15 UTC | ~1 day old |
| AMD | semiconductors | 2026-04-30 14:00 UTC | ~2 days old |
| AVGO | semiconductors | 2026-04-28 18:30 UTC | ~3 days old |
| QCOM | semiconductors | 2026-05-01 13:15 UTC | ~1 day old |
| MU | semiconductors | 2026-05-01 15:30 UTC | ~1 day old |
| INTC | semiconductors | 2026-05-01 18:30 UTC | ~1 day old |
| MSTR | fintech_crypto | 2026-04-23 14:00 UTC | ~8 days old |
| COIN | fintech_crypto | 2026-04-22 15:30 UTC | ~9 days old |
| HOOD | fintech_crypto | 2026-04-30 13:15 UTC | ~2 days old |
| MARA | fintech_crypto | 2026-04-30 19:00 UTC | ~2 days old |
| SNOW | growth_tech | 2026-04-24 16:00 UTC | ~8 days old |
| LULU | consumer_retail | 2026-04-24 16:30 UTC | ~8 days old |

**Missing from DB (never scraped as core yet):** healthcare (TMO, VRTX, LLY), industrials_energy (GE, CAT, XOM), PANW

---

## Manual Verification of Each Sector

### INDEXES (SPY, QQQ, $SPX)

| Metric | Raw Data | Computed | Match? |
|--------|----------|----------|--------|
| Call Volume | 9,022,069 | 9,022,069 | ✅ |
| Put Volume | 8,686,549 | 8,686,549 | ✅ |
| Total Volume | 17,708,618 | 17,708,618 | ✅ |
| Call OI | 1,132,681 | 1,132,681 | ✅ |
| Put OI | 397,925 | 397,925 | ✅ |
| PCR (volume) | 8,686,549 / 9,022,069 | 0.96 | ✅ |
| PCR (OI) | 397,925 / 1,132,681 | 0.35 | ✅ |
| OTM Volume | 12,400,919 | 12,400,919 | ✅ |
| OTM Ratio | 12,400,919 / 17,708,618 | 0.70 | ✅ |
| Premium Flow | $44,268,233 | $44,268,233 | ✅ |

**Per-ticker breakdown:**
- SPY: 4.7M calls, 4.7M puts → PCR 0.98 (neutral, balanced hedging)
- QQQ: 2.4M calls, 2.3M puts → PCR 0.97 (neutral, balanced)
- $SPX: 1.9M calls, 1.7M puts → PCR 0.91 (slightly bullish)

**Assessment:** Logic correct. PCR ~0.96 = neutral market positioning. This makes sense for indexes — institutions use both calls and puts for hedging.

---

### MEGA_CAP_TECH (AAPL, MSFT, GOOGL, META, AMZN)

| Metric | Raw Data | Computed | Match? |
|--------|----------|----------|--------|
| Call Volume | 2,093,248 | 2,093,248 | ✅ |
| Put Volume | 888,992 | 888,992 | ✅ |
| Total Volume | 2,982,240 | 2,982,240 | ✅ |
| PCR (volume) | 888,992 / 2,093,248 | 0.42 | ✅ |
| PCR (OI) | 684,904 / 1,591,939 | 0.43 | ✅ |
| OTM Volume | 2,396,608 | 2,396,608 | ✅ |
| OTM Ratio | 2,396,608 / 2,982,240 | 0.80 | ✅ |

**Per-ticker breakdown:**
- AAPL: 1.5M calls, 479K puts → PCR 0.33 (very bullish)
- AMZN: 371K calls, 234K puts → PCR 0.63 (moderately bullish)
- MSFT: 257K calls, 177K puts → PCR 0.69 (slightly bullish)
- GOOGL: 0 volume (snapshot at 09:15 ET, market just opened)
- META: 0 volume (same issue)

**Assessment:** Logic correct. PCR 0.42 = strongly bullish. This is driven mainly by AAPL's massive call dominance (3:1 call/put ratio). The zero-volume tickers (GOOGL, META) are from early-morning snapshots where volume hadn't accumulated yet.

**Data quality issue:** Snapshots taken at 09:15 ET show zero volume because market just opened. This inflates the sector-level PCR toward bullish for tickers that were scraped early. Need to weight by total volume to avoid noise.

---

### SEMICONDUCTORS (NVDA, AMD, AVGO, QCOM, MU, INTC)

| Metric | Raw Data | Computed | Match? |
|--------|----------|----------|--------|
| Call Volume | 814,641 | 814,641 | ✅ |
| Put Volume | 442,719 | 442,719 | ✅ |
| PCR (volume) | 442,719 / 814,641 | 0.54 | ✅ |
| PCR (OI) | 1,172,832 / 2,617,829 | 0.45 | ✅ |

**Per-ticker breakdown:**
- INTC: 522K calls, 315K puts → PCR 0.60 (slightly bullish)
- MU: 194K calls, 78K puts → PCR 0.40 (very bullish)
- AMD: 58K calls, 19K puts → PCR 0.34 (very bullish)
- AVGO: 41K calls, 31K puts → PCR 0.74 (neutral-ish)
- NVDA: 0 volume (09:15 snapshot)
- QCOM: 0 volume (09:15 snapshot)

**Assessment:** Logic correct. PCR 0.54 = bullish. Driven by MU and AMD showing strong call buying. NVDA and QCOM have zero volume due to early snapshots.

---

### FINTECH_CRYPTO (MSTR, COIN, HOOD, MARA)

| Metric | Raw Data | Computed | Match? |
|--------|----------|----------|--------|
| Call Volume | 255,952 | 255,952 | ✅ |
| Put Volume | 117,345 | 117,345 | ✅ |
| PCR (volume) | 117,345 / 255,952 | 0.46 | ✅ |
| PCR (OI) | 337,617 / 798,488 | 0.42 | ✅ |

**Per-ticker breakdown:**
- COIN: 60K calls, 14K puts → PCR 0.23 (extremely bullish)
- MSTR: 43K calls, 13K puts → PCR 0.32 (very bullish)
- MARA: 153K calls, 90K puts → PCR 0.59 (moderately bullish)
- HOOD: 0 volume (early snapshot)

**Assessment:** Logic correct. PCR 0.46 = bullish. Crypto names showing strong call buying. Note that COIN and MSTR snapshots are 8-9 days old — this is stale data, not real-time flow.

**Data quality issue:** MSTR snapshot is from April 23, COIN from April 22. These are 8-9 day old snapshots showing stale volume. The sector PCR may not reflect current flow.

---

### GROWTH_TECH (PLTR, PANW, SNOW)

| Metric | Raw Data | Computed | Match? |
|--------|----------|----------|--------|
| Call Volume | 15,698 | 15,698 | ✅ |
| Put Volume | 15,457 | 15,457 | ✅ |
| PCR (volume) | 15,457 / 15,698 | 0.98 | ✅ |

**Per-ticker:**
- SNOW: 15.7K calls, 15.5K puts → PCR 0.98 (neutral)

**Assessment:** Logic correct. Only SNOW has data (snapshot from April 24, 8 days old). PCR 0.98 = perfectly balanced. Small volume (31K total) = weak signal.

---

### CONSUMER_RETAIL (TSLA, UBER, LULU, CMG)

| Metric | Raw Data | Computed | Match? |
|--------|----------|----------|--------|
| Call Volume | 7,109 | 7,109 | ✅ |
| Put Volume | 3,728 | 3,728 | ✅ |
| PCR (volume) | 3,728 / 7,109 | 0.52 | ✅ |

**Per-ticker:**
- LULU: 7.1K calls, 3.7K puts → PCR 0.52 (bullish)

**Assessment:** Logic correct. Only LULU has data (snapshot from April 24, 8 days old). Very small volume (10.8K) = weak signal.

---

## Logic Verification Summary

### ✅ All Calculations Match

| Check | Result |
|-------|--------|
| Volume aggregation | All sectors match raw sums |
| PCR (volume) formula | put_volume / call_volume — correct |
| PCR (OI) formula | put_oi / call_oi — correct |
| OTM detection (calls) | strike > spot → correct |
| OTM detection (puts) | strike < spot → correct |
| Premium flow | sum(volume × mark) — correct |
| Direction thresholds | < 0.7 = bullish, > 1.3 = bearish — correct |
| Signal strength | >500K = strong, >100K = moderate — correct |

### ⚠️ Data Quality Issues Found

1. **Early-morning snapshots show zero volume**
   - GOOGL, META, NVDA, QCOM, HOOD all have 0 volume
   - Snapshots taken at 09:15 ET (market just opened)
   - These tickers contribute nothing to sector totals
   - **Impact:** Sector PCR may skew toward tickers scraped later in the day

2. **Stale snapshots for some tickers**
   - MSTR: 8 days old, COIN: 9 days old
   - SNOW: 8 days old, LULU: 8 days old
   - Volume data is from those old dates, not current
   - **Impact:** PCR for fintech_crypto and consumer_retail reflects stale positioning

3. **Volume vs OI divergence**
   - INDEXES: PCR(volume) = 0.96, PCR(OI) = 0.35
   - Huge gap means: lots of calls being opened but few being traded today
   - This is a real signal — long-term call positioning vs intraday flow

### 📊 Sector Signals (verified correct)

| Sector | PCR | Direction | Volume | Strength | Data Quality |
|--------|-----|-----------|--------|----------|--------------|
| indexes | 0.96 | NEUTRAL | 17.7M | strong | ✅ Fresh |
| mega_cap_tech | 0.42 | BULLISH | 3.0M | strong | ⚠️ 2 of 5 tickers zero vol |
| semiconductors | 0.54 | BULLISH | 1.3M | strong | ⚠️ 2 of 6 tickers zero vol |
| fintech_crypto | 0.46 | BULLISH | 373K | moderate | ⚠️ 2 of 4 tickers stale (8-9 days) |
| growth_tech | 0.98 | NEUTRAL | 31K | weak | ⚠️ Only 1 ticker, 8 days old |
| consumer_retail | 0.52 | BULLISH | 11K | weak | ⚠️ Only 1 ticker, 8 days old |

### 🔧 Recommended Fixes

1. **Filter out zero-volume tickers from PCR calculation**
   - Currently, zero-volume tickers don't affect the ratio (they contribute 0/0), but they make sectors appear less diverse
   - Better: only include tickers with volume > 0 in sector PCR

2. **Weight PCR by volume to avoid stale data distortion**
   - A sector with one fresh ticker (1M vol) and one stale ticker (100 vol) should be dominated by the fresh one
   - Current logic already does this (sums are volume-weighted)

3. **Add freshness check**
   - Flag sectors where >50% of volume comes from snapshots >24h old
   - Don't post Discord alerts for stale sectors

4. **Baseline comparison (vs Avg) shows 0.0x**
   - The `volume_vs_avg` is 0.0x for most sectors because the baseline query needs more data
   - After 5+ days of consistent scraping, this will work correctly
   - Not a logic bug, just immature baselines

---

## Conclusion

**The flow logic is mathematically correct.** All calculations match independent manual verification. The PCR, OTM ratio, and premium flow formulas are accurate.

The main issues are data quality (stale snapshots, early-morning zero volume), not logic errors. These will improve as the scraper runs continuously with the new sector-bucket watchlist.
