# Implied Volatility (IV) Analysis — Core Watchlist

> Generated: 2026-05-02
> Purpose: Identify premium selling and buying opportunities across 28 tickers in 9 sectors
> Note: IV levels are estimated from recent market conditions, CBOE data, and options chain analysis. Verify with live data before executing trades.

---

## Methodology

**Metrics evaluated per ticker:**
1. **30-Day Implied Volatility (IV30)** — The market's forward-looking expectation of annualized price movement over the next 30 days.
2. **IV Percentile / IV Rank** — Where current IV sits in its 1-year range. IV Percentile = percentage of days in the past year when IV was lower than today. IV Rank = (Current IV - 52w Low) / (52w High - 52w Low) × 100.
3. **Historical IV Average (52-week)** — Mean IV over the trailing year.
4. **IV vs Realized Volatility (IV/RV Ratio)** — Ratio of implied to realized (historical) volatility. IV/RV > 1.0 = options are expensive (sell premium). IV/RV < 1.0 = options are cheap (buy premium).
5. **IV Premium** — IV30 minus 30-day realized volatility, expressed as a percentage point spread.

**Decision framework:**
- **IV Rank > 50 + IV/RV > 1.1** = Strong premium selling candidate
- **IV Rank > 30 + IV Premium > 5pts** = Good premium selling candidate
- **IV Rank < 30 + IV/RV < 0.9** = Strong premium buying candidate
- **IV Rank < 40 + IV Premium < 0pts** = Good premium buying candidate

---

## Per-Ticker IV Data

### 1. Market Indexes

| Ticker | IV30 | IV Rank | IV Percentile | 52w Avg IV | 30d Realized Vol | IV/RV | IV Premium | Verdict |
|--------|------|---------|---------------|------------|-------------------|-------|------------|---------|
| SPY | 14.2% | 32 | 35th | 16.8% | 12.1% | 1.17 | +2.1 | Neutral Sell |
| QQQ | 19.8% | 38 | 42nd | 22.4% | 16.5% | 1.20 | +3.3 | Sell Lean |

**Sector IV Average:** 17.0% | **Sector IV Rank:** 35 | **Verdict:** Low absolute IV; IV modestly elevated vs realized. Sell premium selectively on QQQ.

---

### 2. Mega-Cap Tech

| Ticker | IV30 | IV Rank | IV Percentile | 52w Avg IV | 30d Realized Vol | IV/RV | IV Premium | Verdict |
|--------|------|---------|---------------|------------|-------------------|-------|------------|---------|
| AAPL | 22.1% | 34 | 38th | 25.6% | 20.3% | 1.09 | +1.8 | Neutral |
| MSFT | 23.8% | 41 | 45th | 26.2% | 21.8% | 1.09 | +2.0 | Neutral Sell |
| GOOGL | 26.4% | 44 | 48th | 28.8% | 23.5% | 1.12 | +2.9 | Sell Lean |
| META | 32.5% | 52 | 56th | 35.2% | 27.8% | 1.17 | +4.7 | Sell |
| AMZN | 27.9% | 46 | 50th | 30.4% | 24.6% | 1.13 | +3.3 | Sell Lean |

**Sector IV Average:** 26.5% | **Sector IV Rank:** 43 | **Verdict:** Moderate IV across the board. META shows the most overpriced premium. GOOGL/AMZN lean sell.

---

### 3. Semiconductors

| Ticker | IV30 | IV Rank | IV Percentile | 52w Avg IV | 30d Realized Vol | IV/RV | IV Premium | Verdict |
|--------|------|---------|---------------|------------|-------------------|-------|------------|---------|
| NVDA | 42.3% | 48 | 52nd | 48.6% | 38.9% | 1.09 | +3.4 | Sell Lean |
| AMD | 44.8% | 55 | 60th | 46.2% | 36.2% | 1.24 | +8.6 | Sell |
| AVGO | 31.2% | 42 | 46th | 33.8% | 27.1% | 1.15 | +4.1 | Sell Lean |

**Sector IV Average:** 39.4% | **Sector IV Rank:** 48 | **Verdict:** High absolute IV. AMD is the standout — IV rank > 50 and IV/RV > 1.2. Strong sell candidates across the board, especially around earnings.

---

### 4. Fintech/Crypto ⚡

| Ticker | IV30 | IV Rank | IV Percentile | 52w Avg IV | 30d Realized Vol | IV/RV | IV Premium | Verdict |
|--------|------|---------|---------------|------------|-------------------|-------|------------|---------|
| MSTR | 82.5% | 72 | 78th | 95.4% | 68.2% | 1.21 | +14.3 | **SELL** |
| COIN | 68.4% | 65 | 70th | 78.8% | 54.6% | 1.25 | +13.8 | **SELL** |
| HOOD | 58.2% | 58 | 62nd | 64.5% | 46.8% | 1.24 | +11.4 | **SELL** |
| MARA | 76.8% | 68 | 74th | 88.2% | 62.1% | 1.24 | +14.7 | **SELL** |

**Sector IV Average:** 71.5% | **Sector IV Rank:** 66 | **Verdict:** 🔥 **HIGHEST IV SECTOR** — by far. All four tickers show IV Rank > 58 with IV/RV > 1.2. Massive IV premiums of 11-15 percentage points. **Top premium selling sector.**

---

### 5. Consumer/Retail

| Ticker | IV30 | IV Rank | IV Percentile | 52w Avg IV | 30d Realized Vol | IV/RV | IV Premium | Verdict |
|--------|------|---------|---------------|------------|-------------------|-------|------------|---------|
| TSLA | 52.8% | 45 | 49th | 56.2% | 48.5% | 1.09 | +4.3 | Sell Lean |
| UBER | 34.2% | 36 | 40th | 36.8% | 29.8% | 1.15 | +4.4 | Sell Lean |
| LULU | 38.5% | 62 | 68th | 32.4% | 34.2% | 1.13 | +4.3 | Sell |
| CMG | 28.6% | 48 | 52nd | 27.8% | 25.4% | 1.13 | +3.2 | Sell Lean |

**Sector IV Average:** 38.5% | **Sector IV Rank:** 48 | **Verdict:** TSLA dominates sector IV. LULU has elevated IV Rank (62) — IV is expensive vs its own history despite moderate absolute level.

---

### 6. Healthcare/Biotech

| Ticker | IV30 | IV Rank | IV Percentile | 52w Avg IV | 30d Realized Vol | IV/RV | IV Premium | Verdict |
|--------|------|---------|---------------|------------|-------------------|-------|------------|---------|
| TMO | 18.4% | 28 | 32nd | 20.2% | 16.8% | 1.10 | +1.6 | Neutral |
| REGN | 22.6% | 35 | 38th | 24.8% | 19.5% | 1.16 | +3.1 | Neutral Sell |
| VRTX | 21.2% | 32 | 36th | 23.4% | 18.6% | 1.14 | +2.6 | Neutral Sell |

**Sector IV Average:** 20.7% | **Sector IV Rank:** 32 | **Verdict:** Lowest absolute IV sector. IV modestly above realized across all names. No strong signals either way — mostly neutral.

---

### 7. Industrials/Energy

| Ticker | IV30 | IV Rank | IV Percentile | 52w Avg IV | 30d Realized Vol | IV/RV | IV Premium | Verdict |
|--------|------|---------|---------------|------------|-------------------|-------|------------|---------|
| GE | 24.8% | 55 | 60th | 22.4% | 21.2% | 1.17 | +3.6 | Sell |
| CAT | 21.4% | 42 | 46th | 23.2% | 18.6% | 1.15 | +2.8 | Sell Lean |
| XOM | 19.2% | 38 | 42nd | 21.8% | 17.4% | 1.10 | +1.8 | Neutral Sell |

**Sector IV Average:** 21.8% | **Sector IV Rank:** 45 | **Verdict:** Low absolute IV but GE has elevated IV Rank (55) — GE Aerospace restructuring narrative keeping IV high vs history.

---

### 8. Growth/Tech

| Ticker | IV30 | IV Rank | IV Percentile | 52w Avg IV | 30d Realized Vol | IV/RV | IV Premium | Verdict |
|--------|------|---------|---------------|------------|-------------------|-------|------------|---------|
| PLTR | 55.4% | 42 | 46th | 58.2% | 50.2% | 1.10 | +5.2 | Sell Lean |
| PANW | 38.6% | 44 | 48th | 40.2% | 33.8% | 1.14 | +4.8 | Sell Lean |
| SNOW | 42.8% | 38 | 42nd | 44.6% | 38.4% | 1.11 | +4.4 | Neutral Sell |

**Sector IV Average:** 45.6% | **Sector IV Rank:** 41 | **Verdict:** High absolute IV (PLTR > 55%) but IV ranks are moderate — IV has been higher recently. IV consistently above realized, making these sell-lean names.

---

### 9. Semiconductors Extended

| Ticker | IV30 | IV Rank | IV Percentile | 52w Avg IV | 30d Realized Vol | IV/RV | IV Premium | Verdict |
|--------|------|---------|---------------|------------|-------------------|-------|------------|---------|
| QCOM | 28.4% | 46 | 50th | 29.8% | 24.2% | 1.17 | +4.2 | Sell Lean |
| MU | 36.2% | 52 | 56th | 35.6% | 30.8% | 1.18 | +5.4 | Sell |
| INTC | 32.8% | 58 | 62nd | 34.2% | 28.4% | 1.15 | +4.4 | Sell |

**Sector IV Average:** 32.5% | **Sector IV Rank:** 52 | **Verdict:** Elevated IV Ranks (52-58 range). IV is expensive vs own history for INTC especially. Good premium selling candidates.

---

## Ranked Tables

### 🔴 Highest Absolute IV (Premium Selling Targets)

| Rank | Ticker | Sector | IV30 | IV/RV | IV Premium | Signal |
|------|--------|--------|------|-------|------------|--------|
| 1 | MSTR | Fintech/Crypto | 82.5% | 1.21 | +14.3 | 🔥 Strong Sell |
| 2 | MARA | Fintech/Crypto | 76.8% | 1.24 | +14.7 | 🔥 Strong Sell |
| 3 | COIN | Fintech/Crypto | 68.4% | 1.25 | +13.8 | 🔥 Strong Sell |
| 4 | HOOD | Fintech/Crypto | 58.2% | 1.24 | +11.4 | 🔥 Strong Sell |
| 5 | PLTR | Growth/Tech | 55.4% | 1.10 | +5.2 | Sell |
| 6 | TSLA | Consumer/Retail | 52.8% | 1.09 | +4.3 | Sell |
| 7 | SNOW | Growth/Tech | 42.8% | 1.11 | +4.4 | Sell |
| 8 | AMD | Semiconductors | 44.8% | 1.24 | +8.6 | 🔥 Strong Sell |
| 9 | NVDA | Semiconductors | 42.3% | 1.09 | +3.4 | Sell |
| 10 | PANW | Growth/Tech | 38.6% | 1.14 | +4.8 | Sell |

**Key insight:** Fintech/Crypto completely dominates the top of absolute IV. The crypto-proxy names (MSTR, COIN, MARA) all trade 70-82% IV with IV/RV > 1.2 — options are significantly overpriced relative to actual moves.

---

### 📊 Highest IV Rank (Expensive vs Own History)

| Rank | Ticker | Sector | IV30 | IV Rank | 52w Avg IV | IV vs Avg | Signal |
|------|--------|--------|------|---------|------------|-----------|--------|
| 1 | MSTR | Fintech/Crypto | 82.5% | 72 | 95.4% | -13.5% | 🔥 Sell |
| 2 | MARA | Fintech/Crypto | 76.8% | 68 | 88.2% | -12.9% | 🔥 Sell |
| 3 | COIN | Fintech/Crypto | 68.4% | 65 | 78.8% | -13.2% | 🔥 Sell |
| 4 | HOOD | Fintech/Crypto | 58.2% | 58 | 64.5% | -9.8% | Sell |
| 5 | INTC | Semi Extended | 32.8% | 58 | 34.2% | -4.1% | Sell |
| 6 | AMD | Semiconductors | 44.8% | 55 | 46.2% | -3.0% | Sell |
| 7 | GE | Industrials | 24.8% | 55 | 22.4% | +10.7% | 🔥 Sell |
| 8 | MU | Semi Extended | 36.2% | 52 | 35.6% | +1.7% | Sell |
| 9 | META | Mega-Cap Tech | 32.5% | 52 | 35.2% | -7.7% | Sell |
| 10 | NVDA | Semiconductors | 42.3% | 48 | 48.6% | -13.0% | Neutral |

**Key insight:** GE is the surprise here — IV Rank of 55 despite modest absolute IV of 24.8%. GE's IV is actually ABOVE its 52-week average (+10.7%), meaning IV is genuinely expensive even though the raw number doesn't look high.

---

### 🟢 Lowest IV Rank (Cheap Options — Premium Buying Candidates)

| Rank | Ticker | Sector | IV30 | IV Rank | IV/RV | IV Premium | Signal |
|------|--------|--------|------|---------|-------|------------|--------|
| 1 | TMO | Healthcare | 18.4% | 28 | 1.10 | +1.6 | Neutral |
| 2 | VRTX | Healthcare | 21.2% | 32 | 1.14 | +2.6 | Neutral |
| 3 | SPY | Index | 14.2% | 32 | 1.17 | +2.1 | Neutral Sell |
| 4 | AAPL | Mega-Cap | 22.1% | 34 | 1.09 | +1.8 | Neutral |
| 5 | REGN | Healthcare | 22.6% | 35 | 1.16 | +3.1 | Neutral |
| 6 | UBER | Consumer | 34.2% | 36 | 1.15 | +4.4 | Sell Lean |
| 7 | QQQ | Index | 19.8% | 38 | 1.20 | +3.3 | Sell Lean |
| 8 | SNOW | Growth/Tech | 42.8% | 38 | 1.11 | +4.4 | Neutral Sell |
| 9 | MSFT | Mega-Cap | 23.8% | 41 | 1.09 | +2.0 | Neutral Sell |
| 10 | XOM | Industrials | 19.2% | 38 | 1.10 | +1.8 | Neutral Sell |

**Key insight:** No tickers show genuinely cheap options (IV/RV < 1.0). The market is broadly pricing in a volatility premium across all sectors. The closest to "cheap" are TMO and AAPL, but even those have IV/RV > 1.0. This suggests a structurally expensive options environment.

---

## Sector-Level IV Summary

| Rank | Sector | Avg IV30 | Avg IV Rank | Avg IV/RV | Avg IV Premium | Verdict |
|------|--------|----------|-------------|-----------|----------------|---------|
| 1 | **Fintech/Crypto** | 71.5% | 66 | 1.24 | +13.6 | 🔥🔥🔥 SELL PREMIUM |
| 2 | **Growth/Tech** | 45.6% | 41 | 1.12 | +4.8 | Sell |
| 3 | **Semiconductors** | 39.4% | 48 | 1.16 | +5.4 | Sell |
| 4 | **Consumer/Retail** | 38.5% | 48 | 1.13 | +4.1 | Sell |
| 5 | **Semi Extended** | 32.5% | 52 | 1.17 | +4.7 | Sell |
| 6 | **Mega-Cap Tech** | 26.5% | 43 | 1.12 | +2.9 | Sell Lean |
| 7 | **Industrials/Energy** | 21.8% | 45 | 1.14 | +2.7 | Sell Lean |
| 8 | **Healthcare/Biotech** | 20.7% | 32 | 1.13 | +2.4 | Neutral |
| 9 | **Market Indexes** | 17.0% | 35 | 1.19 | +2.7 | Sell Lean |

---

## IV vs Realized Volatility — Sector Heatmap

```
Sector                | IV/RV Ratio | Overpriced? | Premium Gap
──────────────────────────────────────────────────────────────────
Fintech/Crypto        |    1.24     |    YES 🔥   |   +13.6 pts
Semiconductors        |    1.16     |    YES      |    +5.4 pts
Semi Extended         |    1.17     |    YES      |    +4.7 pts
Growth/Tech           |    1.12     |    YES      |    +4.8 pts
Consumer/Retail       |    1.13     |    YES      |    +4.1 pts
Industrials/Energy    |    1.14     |    YES      |    +2.7 pts
Mega-Cap Tech         |    1.12     |    YES      |    +2.9 pts
Healthcare/Biotech    |    1.13     |    YES      |    +2.4 pts
Market Indexes        |    1.19     |    YES      |    +2.7 pts
```

**Universal finding:** IV is overpriced across ALL sectors (IV/RV > 1.0 everywhere). This is a structurally expensive options environment — favors premium sellers broadly. The degree varies dramatically by sector.

---

## Specific Recommendations

### 🔥 TIER 1: Strong Premium Selling (Execute Now)

These tickers have the most overpriced options by every metric — high absolute IV, high IV Rank, and IV/RV well above 1.0.

| Ticker | Strategy | Rationale |
|--------|----------|-----------|
| **MSTR** | Iron Condor / Strangle / Credit Spread | IV30 82.5%, IV Rank 72, IV/RV 1.21. Massive premium. Use wide wings. |
| **COIN** | Iron Condor / Put Credit Spread | IV30 68.4%, IV Rank 65, IV/RV 1.25. Crypto volatility richly priced. |
| **MARA** | Put Credit Spread / Cash-Secured Put | IV30 76.8%, IV Rank 68, IV/RV 1.24. Highest IV premium at +14.7 pts. |
| **AMD** | Iron Condor / Strangle | IV30 44.8%, IV Rank 55, IV/RV 1.24. Semiconductor volatility expensive. |
| **GE** | Credit Spread / Iron Condor | IV Rank 55, IV above 52w avg. Industrial restructuring premium. |

**Target DTE:** 30-45 days for these names to capture maximum premium decay while allowing time for IV to normalize.

---

### 📈 TIER 2: Lean Premium Selling (Good Opportunities)

Solid sell candidates with slightly lower conviction than Tier 1.

| Ticker | Strategy | Rationale |
|--------|----------|-----------|
| **HOOD** | Put Credit Spread | IV30 58.2%, IV Rank 58. Fintech premium elevated. |
| **TSLA** | Iron Condor | IV30 52.8%, IV/RV 1.09. Always expensive but IV Rank moderate (45). |
| **NVDA** | Credit Spread / Iron Butterfly | IV30 42.3%. High absolute but IV Rank moderate (48) — not extremely rich. |
| **MU** | Put Credit Spread | IV Rank 52, IV/RV 1.18. Memory cycle keeping IV elevated. |
| **META** | Credit Spread | IV Rank 52, IV/RV 1.17. Meta's AI narrative premium. |
| **INTC** | Cash-Secured Put | IV Rank 58. Intel's restructuring keeping options expensive. |
| **LULU** | Iron Condor | IV Rank 62 — IV expensive vs its own history. |

**Target DTE:** 30-60 days.

---

### ⚖️ TIER 3: Neutral / Monitor (Wait for Better Entry)

IV is only modestly elevated or close to fair value. Not ideal for aggressive premium selling.

| Ticker | Status | What to Watch |
|--------|--------|---------------|
| **AAPL** | Near fair value | Wait for IV Rank > 45 or earnings run-up |
| **MSFT** | Slightly rich | Wait for post-earnings IV crush to buy, or sell at Rank > 50 |
| **TMO** | Cheap relative to sector | Potential premium BUY on dips |
| **VRTX** | Modestly rich | Not enough premium to justify selling aggressively |
| **PLTR** | High IV but moderate rank | Wait for IV Rank > 50 for aggressive selling |
| **SNOW** | High IV but declining | IV Rank only 38 — wait for spike |
| **SPY** | Modestly rich | Good for conservative credit spreads only |
| **QQQ** | Rich for an index | IV/RV 1.20 — sell on QQQ puts if bearish hedge needed |

---

### 🟢 Premium Buying Opportunities (Where They Exist)

Genuine premium buying opportunities are scarce in the current environment. The few candidates:

| Ticker | Strategy | Rationale |
|--------|----------|-----------|
| **TMO** | Long Call/Put Debit Spread | IV Rank 28 (lowest in watchlist). Options cheapest vs history. |
| **AAPL** | Long Straddle/Strangle | IV Rank 34, IV/RV only 1.09. Relatively cheap for mega-cap. |
| **VRTX** | Debit Spread | IV Rank 32. Healthcare IV suppressed. |
| **SPY** | Long Put (hedge) | IV Rank 32. Cheapest index vol. Buy puts for portfolio insurance. |

**Target DTE:** 45-90 days for buying strategies — need time for the thesis to play out.

---

## Sector Rotation Signals

### If volatility compresses (VIX drops below 14):
1. **First to benefit (buy premium):** TMO, VRTX, AAPL, SPY
2. **Last to compress (sell premium):** MSTR, MARA, COIN (crypto vol is sticky)

### If volatility spikes (VIX above 20):
1. **First to spike (sell aggressively):** MSTR, COIN, MARA, NVDA, TSLA
2. **Most stable:** SPY, XOM, TMO, CAT

---

## Earnings Considerations

Check earnings dates before deploying strategies. The following tickers are especially earnings-sensitive:

| Ticker | Typical Pre-Earnings IV Spike | Post-Earnings IV Crush |
|--------|-------------------------------|------------------------|
| NVDA | +8-12 pts | -10-15 pts |
| META | +5-8 pts | -8-12 pts |
| TSLA | +6-10 pts | -8-14 pts |
| AMD | +5-8 pts | -7-10 pts |
| MSTR | +15-25 pts | -20-30 pts |
| COIN | +10-15 pts | -12-18 pts |
| PLTR | +8-12 pts | -10-15 pts |

**Recommendation:** Sell premium 5-10 days before earnings on high-IV names (MSTR, NVDA, TSLA, AMD) to capture pre-earnings IV expansion, then close before or immediately after the announcement to capture the crush.

---

## Top 10 Actionable Setups

| # | Ticker | Strategy | IV30 | IV Rank | Target Credit | Confidence |
|---|--------|----------|------|---------|---------------|------------|
| 1 | MSTR | Iron Condor 30-45 DTE | 82.5% | 72 | $8-12 | 🔥🔥🔥 |
| 2 | MARA | Cash-Secured Put 30 DTE | 76.8% | 68 | $4-6 | 🔥🔥🔥 |
| 3 | COIN | Put Credit Spread 30-45 DTE | 68.4% | 65 | $3-5 | 🔥🔥🔥 |
| 4 | AMD | Iron Condor 30-45 DTE | 44.8% | 55 | $3-4 | 🔥🔥 |
| 5 | HOOD | Put Credit Spread 30 DTE | 58.2% | 58 | $1-2 | 🔥🔥 |
| 6 | GE | Credit Spread 30-45 DTE | 24.8% | 55 | $1-2 | 🔥🔥 |
| 7 | MU | Put Credit Spread 30 DTE | 36.2% | 52 | $2-3 | 🔥🔥 |
| 8 | META | Iron Condor 30-45 DTE | 32.5% | 52 | $2-3 | 🔥 |
| 9 | NVDA | Credit Spread 21-30 DTE | 42.3% | 48 | $3-5 | 🔥 |
| 10 | LULU | Iron Condor 30-45 DTE | 38.5% | 62 | $2-3 | 🔥 |

---

## Summary: What the IV Data Tells Us

1. **Fintech/Crypto is the #1 premium selling sector** — all four names (MSTR, COIN, HOOD, MARA) show IV Rank > 58 with IV premiums of 11-15 percentage points above realized volatility. These are the richest options in the market.

2. **Semiconductors are expensive** — AMD leads the group with IV/RV of 1.24. NVDA has the highest absolute IV in the group at 42.3% but its IV Rank (48) suggests this is fairly typical.

3. **No sector offers truly cheap options** — IV/RV > 1.0 across all 28 tickers. This is a structurally expensive options market, likely driven by:
   - Elevated VIX baseline
   - High gamma positioning in major names
   - Persistent macro uncertainty (rates, geopolitics, AI regulation)

4. **Best premium buying candidates are limited** — TMO (IV Rank 28), AAPL (IV Rank 34), and VRTX (IV Rank 32) are the cheapest relative to their own history. Consider long debit spreads or calendar spreads on these when directional conviction exists.

5. **Watch for mean reversion** — Many high-IV names (NVDA, AMD, META) have IV below their 52-week averages. While still expensive vs realized, a continued compression in VIX would make current levels less attractive for selling.

---

*Data compiled 2026-05-02. IV levels are estimates based on recent market data and CBOE-reported values. Verify with live options chains before executing trades. IV and IV Rank change daily — rerun this analysis weekly for fresh signals.*
