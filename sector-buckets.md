# Sector-Bucket Watchlist

> Core + Dynamic scraper architecture. Sector-diversified continuous data collection.
> **BIDIRECTIONAL framework**: buy mispriced cheap options when IV is low, sell expensive options when IV is high.

---

## Problem

Dynamic tickers come and go. One day NVDA is scraping, next day it's dropped. This breaks:
- Mispricing baselines (need continuous history)
- IV skew tracking (need uninterrupted snapshots)
- Premium momentum signals (need day-over-day comparisons)
- Earnings IV crush patterns (need pre/post earnings data)

## Solution: Two-Bucket Architecture

**Bucket 1: Core Watchlist (never dropped)**
- Fixed list of liquid, high-IV names across market sectors
- Scraped every cycle regardless of score
- Guarantees continuous data for baseline building

**Bucket 2: Dynamic Tickers (opportunistic)**
- Same universe scanner logic as today
- Top 3-8 names per cycle by score
- Comes and goes freely, fine for opportunistic scanning

---

## Proposed Core Sectors (draft — research needed)

### Market Indexes (3)
- $SPX, SPY, QQQ
- Purpose: Baseline, market gamma regime reference

### Mega-Cap Tech (5)
- AAPL, MSFT, GOOGL, META, AMZN
- Purpose: Market drivers, tightest spreads, highest liquidity
- Notes: SPY heavyweights — always have options activity

### Semiconductors (3)
- NVDA, AMD, AVGO
- Purpose: AI cycle sensitivity, high volume, strong directional trends
- Notes: NVDA is the most liquid individual options name after SPY

### Fintech/Crypto (4)
- MSTR, COIN, HOOD, (MARA or RIOT)
- Purpose: Highest IV in market, retail flow, BTC-correlated
- Notes: MSTR often has IV > 100% — premium selling goldmine

### Consumer/Retail (4)
- TSLA, UBER, LULU, CMG
- Purpose: Earnings sensitive, retail-driven, high options activity
- Notes: TSLA earnings moves are massive — IV crush patterns valuable

### Healthcare/Biotech (3)
- TMO, REGN, VRTX
- Purpose: Catalyst-driven, FDA events, steady IV
- Notes: Lower volume than tech but very consistent

### Industrials/Energy (3)
- GE, CAT, XOM
- Purpose: Sector rotation plays, macro/economic cycle signals
- Notes: Energy IV spikes on geopolitical events

### Growth/Tech (3)
- PLTR, PANW, SNOW
- Purpose: High IV growth names, earnings momentum
- Notes: PLTR retail-heavy, PANW enterprise security

### Semiconductors Extended (3)
- QCOM, MU, INTC
- Purpose: Chip cycle diversification, different sub-sectors
- Notes: MU memory cycle, QCOM mobile, INTC legacy/fab

---

## Rate Limit Math

| Scenario | Tickers | Calls/Cycle | Cycle Interval | Utilization |
|----------|---------|-------------|----------------|-------------|
| Current | 11 | 22 | 5 min | 7% |
| Core (24) | 24 | 48 | 5 min | 16% |
| Core + Dynamic (32) | 32 | 64 | 5 min | 21% |
| Core (24) every minute | 24 | 48 | 1 min | 80% |

**Max budget:** 60 calls/min × 5 min = 300 calls per cycle
**Core only:** 48 calls = 16% utilization
**Core + 8 dynamic:** 64 calls = 21% utilization
**Plenty of headroom to add more or increase frequency.**

---

## Open Questions (Research Needed)

**Research files completed in /buckets/:**
- `01_liquidity_analysis.md` -- Options volume, OI, spread data for all tickers
- `02_iv_analysis.md` -- IV levels, IV rank, IV vs RV by sector
- `03_correlation_analysis.md` -- Which tickers are redundant vs unique signals
- `04_earnings_analysis.md` -- Earnings timing, IV crush by sector
- `05_bidirectional_strategies.md` -- WHEN to buy vs sell, per-sector playbook

### Remaining questions:

1. **Which sectors have the most liquid options?**
   - Need to check: avg daily options volume by sector
   - Focus on tickers with >500 contracts OI and >100 daily volume

2. **IV levels by sector**
   - Which sectors consistently have the highest IV?
   - Where's the premium selling opportunity?
   - Where's the cheap premium buying opportunity?

3. **Earnings calendar density**
   - Which sectors have the most frequent earnings events?
   - Can we capture IV crush patterns systematically?

4. **Correlation between sectors**
   - Do certain sectors move together? (e.g., NVDA + AMD + AVGO)
   - Should we pick one per sector or multiple?
   - If we have both NVDA and AMD, are we just doubling the same signal?

5. **Minimum liquidity threshold**
   - What's the minimum OI/volume for reliable theoretical value comparison?
   - Wide spreads = noisy mispricing signals

6. **Sector rebalancing**
   - How often do we review the core list?
   - What triggers adding/removing a sector?
   - Quarterly review? Monthly?

7. **Cross-sector signals**
   - When IV spikes in one sector but not others, is that a rotation signal?
   - Can we detect money flowing between sectors via IV changes?

8. **Dynamic scanner improvement**
   - Current scoring is volume + move-based
   - Should we add IV rank as a scoring factor?
   - Should we penalize tickers already in core watchlist?

---

## Implementation Plan (once research is done)

1. Update `config/watchlist.yaml` with sector buckets
2. Modify `scripts/options_scraper.py` to read core + dynamic
3. Add sector labels to dynamic_tickers.json output
4. Push to desktop, verify continuous scraping across all sectors
5. After 5-10 days: start building per-ticker mispricing baselines
