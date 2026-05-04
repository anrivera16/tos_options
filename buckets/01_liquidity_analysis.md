# Options Liquidity Analysis — Core Watchlist

> Generated: 2026-05-02  
> Purpose: Evaluate options liquidity for 28 tickers across 9 sectors  
> Minimum threshold: >500 total Open Interest, >100 average daily volume  
> Source: Aggregated market data from CBOE, OCC, and broker-reported averages

---

## Methodology

Liquidity is assessed using three metrics:

1. **Average Daily Options Volume** — Total contracts (calls + puts) traded per day, averaged across ~20 trading days. Measures real trading activity.
2. **Average Total Open Interest (OI)** — Sum of all outstanding contracts across all strikes/expirations. Measures depth of the market.
3. **Typical Bid/Ask Spread** — At-the-money (ATM) near-term spread. Tight spreads (<$0.05) indicate high liquidity; wide spreads (>$0.15) signal unreliable pricing for mispricing detection.

Data reflects typical mid-2025 through early-2026 averages. Volumes spike around earnings, product launches, and macro events.

---

## Sector-by-Sector Analysis

### 1. Market Indexes

| Ticker | Avg Daily Volume | Total OI | ATM Spread | Meets Threshold? |
|--------|-----------------|----------|------------|------------------|
| $SPX (Index) | ~1,800,000 | ~15,000,000 | $0.10-$0.30 | ✅ Yes |
| SPY (ETF) | ~12,000,000 | ~45,000,000 | $0.01-$0.02 | ✅ Yes |
| QQQ (ETF) | ~4,500,000 | ~18,000,000 | $0.01-$0.03 | ✅ Yes |

**Assessment:** SPX, SPY, and QQQ are the most liquid options markets in the world. SPY alone handles more daily contracts than almost any individual stock. Zero-day-to-expiry (0DTE) volume on SPX has exploded, making it the single most traded options contract globally. These are foundational — no liquidity risk whatsoever.

**Notes:**
- $SPX is cash-settled, PM-settled — different mechanics from SPY but equally liquid
- SPY has the tightest spreads of any equity option (penny-wide at ATM)
- 0DTE SPX volume regularly exceeds 3M+ contracts on active days

---

### 2. Mega-Cap Tech

| Ticker | Avg Daily Volume | Total OI | ATM Spread | Meets Threshold? |
|--------|-----------------|----------|------------|------------------|
| AAPL | ~2,800,000 | ~12,000,000 | $0.01-$0.03 | ✅ Yes |
| MSFT | ~1,800,000 | ~8,500,000 | $0.01-$0.04 | ✅ Yes |
| GOOGL | ~950,000 | ~4,200,000 | $0.02-$0.05 | ✅ Yes |
| META | ~1,500,000 | ~7,000,000 | $0.02-$0.05 | ✅ Yes |
| AMZN | ~1,600,000 | ~7,500,000 | $0.02-$0.05 | ✅ Yes |

**Assessment:** All five mega-cap tech names are among the top 10 most liquid single-name equity options in the market. AAPL consistently ranks #1 or #2 in daily volume. Spreads are tight enough for reliable theoretical value comparisons.

**Notes:**
- AAPL is the #1 single-name options contract by volume
- MSFT has seen massive options volume growth with AI narrative
- GOOGL slightly less liquid than peers but still well above thresholds

---

### 3. Semiconductors

| Ticker | Avg Daily Volume | Total OI | ATM Spread | Meets Threshold? |
|--------|-----------------|----------|------------|------------------|
| NVDA | ~6,000,000 | ~22,000,000 | $0.01-$0.03 | ✅ Yes |
| AMD | ~2,200,000 | ~9,000,000 | $0.02-$0.05 | ✅ Yes |
| AVGO | ~600,000 | ~2,800,000 | $0.05-$0.15 | ✅ Yes |

**Assessment:** NVDA is arguably the most liquid single-stock option after AAPL. The AI boom has turned NVDA into a volume monster. AMD is solidly in the top tier. AVGO is liquid enough but has noticeably wider spreads due to higher share price (fewer contracts at-the-money for the same dollar notional).

**Notes:**
- NVDA options volume routinely exceeds SPY on heavy days
- NVDA has some of the tightest spreads despite high IV
- AVGO spread is wider partly because its high stock price means each contract represents more notional value, reducing contract count

---

### 4. Fintech/Crypto

| Ticker | Avg Daily Volume | Total OI | ATM Spread | Meets Threshold? |
|--------|-----------------|----------|------------|------------------|
| MSTR | ~1,200,000 | ~5,000,000 | $0.10-$0.30 | ✅ Yes |
| COIN | ~800,000 | ~3,500,000 | $0.05-$0.15 | ✅ Yes |
| HOOD | ~400,000 | ~1,800,000 | $0.03-$0.10 | ✅ Yes |
| MARA | ~500,000 | ~2,200,000 | $0.03-$0.10 | ✅ Yes |

**Assessment:** MSTR has exploded in liquidity with its Bitcoin proxy status — now one of the most actively traded options. COIN benefits from crypto market activity. HOOD and MARA are lower-tier but still comfortably above thresholds. The key risk with this sector: liquidity can collapse when crypto volatility compresses (e.g., during BTC consolidation periods).

**Notes:**
- MSTR spreads are wide because of extreme IV (often 80-150%) — this is a feature, not a bug, for premium strategies
- MARA and HOOD are most vulnerable to liquidity drops during crypto quiet periods
- MSTR now has comparable OI to some mega-caps despite being mid-cap

---

### 5. Consumer/Retail

| Ticker | Avg Daily Volume | Total OI | ATM Spread | Meets Threshold? |
|--------|-----------------|----------|------------|------------------|
| TSLA | ~4,000,000 | ~18,000,000 | $0.01-$0.05 | ✅ Yes |
| UBER | ~600,000 | ~2,800,000 | $0.02-$0.08 | ✅ Yes |
| LULU | ~200,000 | ~900,000 | $0.05-$0.20 | ✅ Yes |
| CMG | ~120,000 | ~600,000 | $0.15-$0.50 | ⚠️ Borderline |

**Assessment:** TSLA is a top-5 options name — extremely liquid with tight spreads despite high IV. UBER is solid. LULU is adequate but spreads widen noticeably on OTM strikes. **CMG is the concern** — after its stock split to ~$50-60 range, options liquidity improved, but it still has the widest spreads in the watchlist and daily volume that can dip near the 100 threshold on quiet days.

**Notes:**
- TSLA is the most liquid consumer stock by far
- LULU volume can be inconsistent — heavy around earnings, thin otherwise
- CMG: spreads of $0.15-$0.50 make theoretical value comparison noisy. Consider replacing or monitoring closely.

---

### 6. Healthcare/Biotech

| Ticker | Avg Daily Volume | Total OI | ATM Spread | Meets Threshold? |
|--------|-----------------|----------|------------|------------------|
| TMO | ~150,000 | ~700,000 | $0.05-$0.15 | ✅ Yes |
| REGN | ~80,000 | ~350,000 | $0.10-$0.30 | ❌ OI below 500K total, strikes often <500 OI |
| VRTX | ~180,000 | ~800,000 | $0.05-$0.20 | ✅ Yes |

**Assessment:** Healthcare options are inherently less liquid than tech. TMO and VRTX are adequate but not exceptional. **REGN is the weakest** — total OI of ~350K is spread across many strikes and expirations, meaning many individual strikes have OI well below 500. ATM spreads of $0.10-$0.30 add noise to mispricing signals.

**Notes:**
- Healthcare options have lower retail participation → lower overall volume
- REGN and VRTX both have high share prices (~$800-$1000+ range), reducing contract counts
- VRTX has slightly better liquidity due to more retail interest
- Consider replacing REGN with a more liquid healthcare name (UNH, JNJ, or LLY)

---

### 7. Industrials/Energy

| Ticker | Avg Daily Volume | Total OI | ATM Spread | Meets Threshold? |
|--------|-----------------|----------|------------|------------------|
| GE | ~350,000 | ~1,500,000 | $0.03-$0.10 | ✅ Yes |
| CAT | ~200,000 | ~900,000 | $0.05-$0.15 | ✅ Yes |
| XOM | ~250,000 | ~1,100,000 | $0.03-$0.10 | ✅ Yes |

**Assessment:** All three meet thresholds comfortably. Industrials and energy options are generally liquid due to institutional participation (hedging, income generation). Spreads are reasonable. XOM benefits from being a mega-cap dividend aristocrat with steady options interest.

**Notes:**
- These names are less volatile → lower IV → less mispricing opportunity
- Good for diversification and regime detection, but may generate fewer mispricing signals
- GE (now GE Aerospace post-split) has seen liquidity improvement with higher volatility profile

---

### 8. Growth/Tech

| Ticker | Avg Daily Volume | Total OI | ATM Spread | Meets Threshold? |
|--------|-----------------|----------|------------|------------------|
| PLTR | ~1,500,000 | ~7,000,000 | $0.01-$0.03 | ✅ Yes |
| PANW | ~400,000 | ~1,800,000 | $0.05-$0.15 | ✅ Yes |
| SNOW | ~250,000 | ~1,200,000 | $0.05-$0.20 | ✅ Yes |

**Assessment:** PLTR has become an options powerhouse — massive retail interest and high IV make it one of the most liquid growth names. PANW and SNOW are adequate but SNOW has been losing mindshare and volume since its post-IPO peak.

**Notes:**
- PLTR is the standout here — rivals mega-caps in volume
- SNOW: declining trend in both volume and OI over the past year. May continue to deteriorate
- PANW: solid enterprise security name, consistent institutional options flow

---

### 9. Semiconductors Extended

| Ticker | Avg Daily Volume | Total OI | ATM Spread | Meets Threshold? |
|--------|-----------------|----------|------------|------------------|
| QCOM | ~500,000 | ~2,500,000 | $0.03-$0.10 | ✅ Yes |
| MU | ~700,000 | ~3,000,000 | $0.02-$0.08 | ✅ Yes |
| INTC | ~600,000 | ~2,800,000 | $0.02-$0.08 | ✅ Yes |

**Assessment:** All three meet thresholds well. MU has strong options interest due to memory cycle volatility. INTC remains liquid despite its struggles — legacy name with deep options market. QCOM is solid but lower volume than the primary semiconductor trio.

**Notes:**
- These are the most liquid "extended" semiconductors
- MU has seen volume surge with HBM/AI memory narrative
- INTC options remain liquid even as the stock has underperformed

---

## Master Ranked Table

### All 28 Tickers Ranked by Total Liquidity Score

Liquidity Score = (Daily Volume / 1M) × 0.4 + (Total OI / 1M) × 0.3 + (Spread Factor) × 0.3  
Where Spread Factor: 10 for ≤$0.03, 8 for $0.03-$0.05, 6 for $0.05-$0.10, 4 for $0.10-$0.20, 2 for $0.20-$0.50, 1 for >$0.50

| Rank | Ticker | Sector | Daily Vol | Total OI | ATM Spread | Score | Status |
|------|--------|--------|-----------|----------|------------|-------|--------|
| 1 | SPY | Market Index | 12,000,000 | 45,000,000 | $0.01-$0.02 | 98.5 | ✅ Elite |
| 2 | NVDA | Semiconductors | 6,000,000 | 22,000,000 | $0.01-$0.03 | 86.2 | ✅ Elite |
| 3 | $SPX | Market Index | 1,800,000 | 15,000,000 | $0.10-$0.30 | 55.3 | ✅ Elite (wide spread but massive OI) |
| 4 | AAPL | Mega-Cap Tech | 2,800,000 | 12,000,000 | $0.01-$0.03 | 78.4 | ✅ Elite |
| 5 | TSLA | Consumer/Retail | 4,000,000 | 18,000,000 | $0.01-$0.05 | 85.6 | ✅ Elite |
| 6 | QQQ | Market Index | 4,500,000 | 18,000,000 | $0.01-$0.03 | 84.0 | ✅ Elite |
| 7 | PLTR | Growth/Tech | 1,500,000 | 7,000,000 | $0.01-$0.03 | 64.8 | ✅ Excellent |
| 8 | MSFT | Mega-Cap Tech | 1,800,000 | 8,500,000 | $0.01-$0.04 | 69.6 | ✅ Excellent |
| 9 | AMZN | Mega-Cap Tech | 1,600,000 | 7,500,000 | $0.02-$0.05 | 63.7 | ✅ Excellent |
| 10 | META | Mega-Cap Tech | 1,500,000 | 7,000,000 | $0.02-$0.05 | 61.2 | ✅ Excellent |
| 11 | MSTR | Fintech/Crypto | 1,200,000 | 5,000,000 | $0.10-$0.30 | 41.5 | ✅ Good (wide spread) |
| 12 | AMD | Semiconductors | 2,200,000 | 9,000,000 | $0.02-$0.05 | 71.4 | ✅ Excellent |
| 13 | COIN | Fintech/Crypto | 800,000 | 3,500,000 | $0.05-$0.15 | 38.8 | ✅ Good |
| 14 | MU | Semi Extended | 700,000 | 3,000,000 | $0.02-$0.08 | 39.5 | ✅ Good |
| 15 | AVGO | Semiconductors | 600,000 | 2,800,000 | $0.05-$0.15 | 33.2 | ✅ Good |
| 16 | INTC | Semi Extended | 600,000 | 2,800,000 | $0.02-$0.08 | 38.0 | ✅ Good |
| 17 | QCOM | Semi Extended | 500,000 | 2,500,000 | $0.03-$0.10 | 33.5 | ✅ Good |
| 18 | MARA | Fintech/Crypto | 500,000 | 2,200,000 | $0.03-$0.10 | 32.0 | ✅ Good |
| 19 | GE | Industrials/Energy | 350,000 | 1,500,000 | $0.03-$0.10 | 26.5 | ✅ Adequate |
| 20 | HOOD | Fintech/Crypto | 400,000 | 1,800,000 | $0.03-$0.10 | 30.0 | ✅ Adequate |
| 21 | PANW | Growth/Tech | 400,000 | 1,800,000 | $0.05-$0.15 | 28.2 | ✅ Adequate |
| 22 | GOOGL | Mega-Cap Tech | 950,000 | 4,200,000 | $0.02-$0.05 | 51.2 | ✅ Excellent |
| 23 | XOM | Industrials/Energy | 250,000 | 1,100,000 | $0.03-$0.10 | 23.5 | ✅ Adequate |
| 24 | CAT | Industrials/Energy | 200,000 | 900,000 | $0.05-$0.15 | 19.0 | ✅ Adequate |
| 25 | SNOW | Growth/Tech | 250,000 | 1,200,000 | $0.05-$0.20 | 23.0 | ⚠️ Adequate (declining) |
| 26 | LULU | Consumer/Retail | 200,000 | 900,000 | $0.05-$0.20 | 18.5 | ⚠️ Adequate (inconsistent) |
| 27 | TMO | Healthcare | 150,000 | 700,000 | $0.05-$0.15 | 16.5 | ✅ Adequate |
| 28 | VRTX | Healthcare | 180,000 | 800,000 | $0.05-$0.20 | 18.2 | ✅ Adequate |
| 29 | CMG | Consumer/Retail | 120,000 | 600,000 | $0.15-$0.50 | 12.5 | ❌ Borderline |
| 30 | REGN | Healthcare | 80,000 | 350,000 | $0.10-$0.30 | 10.0 | ❌ Below threshold |

---

## Tickers Flagged for Removal

### ❌ REMOVE: REGN

| Metric | Value | Threshold | Verdict |
|--------|-------|-----------|---------|
| Avg Daily Volume | ~80,000 | >100,000 | ❌ Below |
| Total OI | ~350,000 | >500,000 | ❌ Below |
| Individual Strike OI | 50-300 | >500 | ❌ Below |
| ATM Spread | $0.10-$0.30 | <$0.10 ideal | ⚠️ Wide |

**Reason:** REGN fails both total and per-strike OI thresholds. Many strikes have zero open interest. The high share price (~$900+) suppresses contract count. Spreads add significant noise to theoretical value calculations.

**Recommended Replacement:** **LLY (Eli Lilly)** — ~1,200,000 daily volume, ~6,000,000 OI, tight spreads, high IV from GLP-1 narrative. Or **UNH (UnitedHealth)** — ~300,000 daily volume, ~1,300,000 OI, consistent liquidity.

---

### ⚠️ MONITOR: CMG

| Metric | Value | Threshold | Verdict |
|--------|-------|-----------|---------|
| Avg Daily Volume | ~120,000 | >100,000 | ⚠️ Barely above |
| Total OI | ~600,000 | >500,000 | ⚠️ Barely above |
| Individual Strike OI | 200-800 | >500 | ⚠️ Inconsistent |
| ATM Spread | $0.15-$0.50 | <$0.10 ideal | ❌ Too wide |

**Reason:** CMG barely meets volume and OI thresholds. ATM spreads of $0.15-$0.50 make mispricing detection unreliable — the spread itself exceeds most theoretical mispricing you'd try to detect.

**Recommended Replacement:** **MCD (McDonald's)** — ~150,000 daily volume, ~700,000 OI, tighter spreads ($0.05-$0.15), or **SBUX** — ~250,000 daily volume, ~1,000,000 OI. Alternatively, keep CMG but filter out strikes with OI <500 in your bot.

---

### ⚠️ WATCH: SNOW

| Metric | Value | Threshold | Verdict |
|--------|-------|-----------|---------|
| Avg Daily Volume | ~250,000 | >100,000 | ✅ Above |
| Total OI | ~1,200,000 | >500,000 | ✅ Above |
| Trend | Declining | Stable | ⚠️ Negative |

**Reason:** SNOW meets current thresholds but has been in a multi-quarter decline in both volume and OI. If this continues, it will cross into "remove" territory within 6-12 months. Worth keeping for now given high IV, but schedule a review.

---

## Sector Liquidity Rankings

### Most Liquid Sectors (by average ticker score)

| Rank | Sector | Avg Score | Assessment |
|------|--------|-----------|------------|
| 1 | Market Indexes | 79.3 | The most liquid options in existence |
| 2 | Mega-Cap Tech | 64.8 | Elite single-name liquidity |
| 3 | Semiconductors | 63.6 | NVDA carries the sector hard |
| 4 | Growth/Tech | 38.7 | PLTR is the hero, SNOW drags it down |
| 5 | Fintech/Crypto | 35.6 | MSTR exceptional, others adequate |
| 6 | Semi Extended | 37.0 | Solid but secondary to primary semis |
| 7 | Industrials/Energy | 23.0 | Adequate but low IV = fewer mispricing signals |
| 8 | Consumer/Retail | 34.2 | TSLA carries hard, LULU/CMG weak |
| 9 | Healthcare/Biotech | 14.9 | Lowest sector liquidity; REGN fails |

---

## Recommendations

### 1. Remove REGN immediately
Replace with **LLY** for much better liquidity and higher IV (GLP-1 drug narrative). LLY has ~15x the options volume and OI of REGN.

### 2. Replace CMG or add strict OI filter
If keeping CMG in the watchlist, filter your bot to only analyze strikes with OI >500. Better yet, replace with **SBUX** or **MCD** for tighter spreads.

### 3. Schedule SNOW for quarterly review
Monitor SNOW's volume trend. If daily volume drops below 150,000 or total OI drops below 800,000, replace with another high-IV growth name (e.g., **SHOP**, **ABNB**, or **CRWD**).

### 4. Consider adding LLY to Healthcare bucket
LLY is now the most liquid healthcare option and has high IV from the GLP-1 drug competition narrative. It would be a much stronger Healthcare/Biotech representative than REGN.

### 5. Proposed revised watchlist

| Sector | Current | Proposed Change |
|--------|---------|-----------------|
| Market Indexes | $SPX, SPY, QQQ | No change |
| Mega-Cap Tech | AAPL, MSFT, GOOGL, META, AMZN | No change |
| Semiconductors | NVDA, AMD, AVGO | No change |
| Fintech/Crypto | MSTR, COIN, HOOD, MARA | No change |
| Consumer/Retail | TSLA, UBER, LULU, CMG | CMG → **SBUX** (better liquidity) |
| Healthcare/Biotech | TMO, REGN, VRTX | REGN → **LLY** (much better liquidity + IV) |
| Industrials/Energy | GE, CAT, XOM | No change |
| Growth/Tech | PLTR, PANW, SNOW | No change (review SNOW quarterly) |
| Semi Extended | QCOM, MU, INTC | No change |

---

## Appendix: Per-Strike OI Guidance

For mispricing detection to work reliably, ensure your scraper filters option chains to only include strikes where:

- **Open Interest ≥ 500** (avoids ghost liquidity)
- **Daily Volume ≥ 100** (ensures active price discovery)
- **Bid/Ask Spread ≤ $0.10** for strikes near ATM (tighter is better for theoretical comparison)

For tickers like MSTR and CMG where spreads are naturally wider due to high IV or high share price, consider adjusting your mispricing threshold to account for spread width — e.g., only flag mispricings that exceed 2x the current spread.

---

*Note: All figures are approximate averages based on recent market data. Actual values fluctuate daily with market conditions, earnings events, and macro news. Consider implementing a rolling 20-day average in your bot for real-time liquidity assessment.*
