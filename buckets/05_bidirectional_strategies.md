# Bidirectional Options Strategy Framework — Sector-Bucket Watchlist

> Generated: 2026-05-02
> Purpose: Define WHEN to BUY options vs SELL options across market regimes and sectors. This is a BIDIRECTIONAL framework — not just selling premium. Buy mispriced cheap options when IV is low, sell expensive options when IV is high.
> Note: This framework is designed to cycle with the market. The current environment (May 2026) is structurally expensive for options across all sectors (IV/RV > 1.0 everywhere), but cycles shift. This document prepares the playbook for BOTH regimes.

---

## Table of Contents

1. [The Core Philosophy: Buy Cheap, Sell Expensive](#1-the-core-philosophy)
2. [When to BUY Options (Long Premium)](#2-when-to-buy-options)
3. [When to SELL Options (Short Premium)](#3-when-to-sell-options)
4. [Regime Detection Dashboard](#4-regime-detection)
5. [Mispriced Option Buying Opportunities](#5-mispriced-option-buying-opportunities)
6. [Per-Sector Playbook](#6-per-sector-playbook)
7. [Position Sizing Framework](#7-position-sizing)
8. [Risk Management Rules](#8-risk-management)
9. [Real-Time Monitoring Checklist](#9-real-time-monitoring)
10. [Decision Flowchart](#10-decision-flowchart)

---

## 1. The Core Philosophy

**Options are insurance contracts. The price of insurance fluctuates based on fear, greed, and uncertainty.**

- When fear is LOW and complacency is HIGH → options are CHEAP → BUY premium
- When fear is HIGH and panic is elevated → options are EXPENSIVE → SELL premium
- The edge comes from recognizing when the market is mispricing future volatility vs. what actually happens

**The IV/RV Ratio is the compass:**
- IV/RV < 0.90 = options are underpriced (buy premium)
- IV/RV = 0.90-1.10 = fairly priced (directional strategies preferred)
- IV/RV > 1.10 = options are overpriced (sell premium)

**The IV Percentile is the clock:**
- IV Percentile < 25 = IV at the LOW end of its annual range
- IV Percentile 25-50 = below-average IV
- IV Percentile 50-75 = above-average IV
- IV Percentile > 75 = IV at the HIGH end of its annual range

**The golden rule:** Combine both metrics. Low IV percentile AND low IV/RV = highest conviction buy. High IV percentile AND high IV/RV = highest conviction sell.

---

## 2. When to BUY Options (Long Premium)

### 2.1 Signal Criteria

#### Primary Signals (need at least 2 of 3)

| Signal | Threshold | What It Means |
|--------|-----------|---------------|
| IV Percentile | < 30 | Options are cheaper than 70%+ of the past year |
| IV / RV Ratio | < 0.90 | Options are underpriced vs. actual stock movement |
| IV Premium | < 0 pts | Implied vol is BELOW realized vol (negative premium) |

#### Secondary Confirmation (at least 1)

| Signal | What to Look For |
|--------|------------------|
| VIX Level | < 14 (broad market complacency) |
| Sector IV Rank | Bottom quartile vs. other sectors |
| Recent IV Compression | IV has been declining for 10+ consecutive days |
| Low Put/Call Ratio | < 0.70 (extreme complacency in that name) |

### 2.2 Before Expected Big Moves (Event-Driven Buying)

**This is the EXCEPTION to the "don't buy before events" rule.** Buy when the market hasn't priced in the expected move yet.

| Event Type | When to Buy | Why It Works |
|------------|-------------|--------------|
| **Earnings** | 5-7 days before, IF IV hasn't spiked yet | IV typically rises 5-8 days before earnings. If you buy early, you capture both the IV expansion AND the directional move. |
| **FDA Decisions** | 3-5 days before PDUFA date | Biotech IV spikes violently before FDA decisions. Buy when IV is still in the 25-35 percentile. |
| **Product Launches** | 2-4 weeks before Apple events, etc. | Tech IV ramps into product launches. The market often underprices the move. |
| **Macro Events** | 1-2 weeks before FOMC, CPI, NFP | Broad market IV rises before macro events. Buy index options (SPY, QQQ) when IV percentile < 30. |
| **Sector Rotation** | When money starts flowing into a low-IV sector | If semis have been quiet (IV < 25th percentile) but chip orders are surging, buy NVDA/AMD calls early. |

### 2.3 Best Sectors/Tickers for Buying Premium (Historically Cheapest IV Periods)

Based on the IV analysis in `02_iv_analysis.md`, here are the names that spend the most time with LOW IV:

| Ticker | Sector | Avg IV Percentile | Why It's Often Cheap | Best Buy Strategy |
|--------|--------|-------------------|---------------------|-------------------|
| **TMO** | Healthcare | 28 (lowest) | Steady, predictable business. Low drama. | Long calls when IV Rank < 30 |
| **SPY** | Index | 32 | The most liquid options in the world. Constantly supplied. | Long puts for hedging when VIX < 14 |
| **AAPL** | Mega-Cap | 34 | Huge options supply, market maker hedging suppresses IV. | Debit spreads, calendars |
| **VRTX** | Healthcare | 32 | Consistent CF franchise, low surprise rate. | Debit spreads on pipeline catalysts |
| **XOM** | Industrials | 38 | Energy IV is mean-reverting. Cheap between geopolitical events. | Long calls on oil breakout setups |
| **CAT** | Industrials | 42 | Tied to economic cycle. IV compresses during steady growth. | Debit spreads on economic data |
| **MSFT** | Mega-Cap | 41 | Azure growth is modeled well. IV stays compressed. | Calendars around steady earnings |

**Key insight:** Healthcare and Mega-Cap Tech names spend the most time in the "cheap IV" zone because their businesses are highly predictable. The market doesn't fear surprises. This makes them IDEAL for buying premium when you have directional conviction.

### 2.4 Best Buying Strategies by Setup

| Market Condition | Strategy | When to Use | Max Risk | Target Return |
|-----------------|----------|-------------|----------|---------------|
| **Directional view + cheap IV** | Long Call/Put | IV Percentile < 25, clear trend | Premium paid | 100-300% |
| **Directional view + moderate IV** | Debit Spread (call or put) | IV Percentile 25-40 | Debit paid | 50-150% |
| **Expecting IV to rise** | Calendar Spread | IV Percentile < 20, stable price | Debit paid | 30-80% (from IV expansion) |
| **Expecting IV to rise + directional** | Diagonal Spread | IV Percentile < 25, bullish/bearish | Debit paid | 40-120% |
| **Expecting big move, unsure direction** | Long Straddle/Strangle | IV Percentile < 15, catalyst pending | Premium paid | Unlimited (calls) / 100%+ (strangle) |
| **Hedging a portfolio** | Long Put (index) | VIX < 14, portfolio fully invested | Premium paid | Insurance value |

### 2.5 BUY Entry Rules

**For Long Calls/Puts:**
1. IV Percentile must be < 30
2. IV/RV must be < 1.0 (ideal) or < 1.05 (acceptable)
3. Technical setup confirms direction (breakout, trend alignment, support/resistance)
4. Entry: Buy at or below mid-price. Never pay the ask.
5. DTE: 45-90 days (need time for thesis to develop and IV to expand)
6. Strike: ATM for pure directional, 1-2 OTM for leverage (but only if IV is truly cheap)

**For Debit Spreads:**
1. IV Percentile 25-45 (moderate, not ultra-cheap)
2. Debit should be < 40% of spread width
3. DTE: 30-60 days
4. Buy the closer-to-ATM leg, sell the further OTM leg
5. Target: 50% of max profit, then close

**For Calendar/Diagonal Spreads:**
1. IV Percentile < 20 (front month IV extremely cheap)
2. Near-term DTE: 7-14 days (short leg)
3. Far-term DTE: 45-90 days (long leg)
4. Same strike for calendars, different strikes for diagonals
5. Profit from: (a) theta decay of short leg, (b) IV expansion in long leg

### 2.6 BUY Exit Rules

| Exit Trigger | Action |
|--------------|--------|
| Profit target reached (100%+ on longs, 50% on spreads) | Close 50-100% of position |
| IV expands to 60th+ percentile | Consider closing — you captured the IV expansion |
| Underlying moves against you 15-20% | Evaluate: thesis broken? If yes, close. If not, hold or average down. |
| DTE < 14 days and position is OTM | Close. Don't let it go to zero. |
| Time stop: 21 days elapsed with no progress | Re-evaluate thesis. Close if thesis is stale. |
| IV/RV flips above 1.15 | Your "cheap" options are now expensive. Consider closing. |

---

## 3. When to SELL Options (Short Premium)

### 3.1 Signal Criteria

#### Primary Signals (need at least 2 of 3)

| Signal | Threshold | What It Means |
|--------|-----------|---------------|
| IV Percentile | > 70 | Options are more expensive than 70%+ of the past year |
| IV / RV Ratio | > 1.15 | Options are overpriced vs. actual stock movement |
| IV Premium | > 5 pts | Implied vol is 5+ points ABOVE realized vol |

#### Secondary Confirmation (at least 1)

| Signal | What to Look For |
|--------|------------------|
| VIX Level | > 20 (elevated fear) |
| Post-Spike | IV just spiked 10+ points in the last 5 days |
| High Put/Call Ratio | > 1.20 (panic buying of puts) |
| Earnings Proximity | 3-7 days before earnings on high-IV name |

### 3.2 After IV Spikes (Mean Reversion Plays)

**This is the highest-probability selling setup.** IV spikes are almost always followed by mean reversion.

| IV Spike Trigger | Typical Spike | How Long Until Reversion | Best Strategy |
|-----------------|---------------|-------------------------|---------------|
| Earnings announcement | +5 to +40 pts | 1-3 days (IV crush) | Sell 1-2 days before earnings, close after |
| Market selloff (>2% SPY drop) | +3 to +8 pts | 3-10 days | Sell broad-based credit spreads or iron condors |
| Geopolitical event | +5 to +15 pts | 1-4 weeks | Sell after the headline shock fades |
| Single-stock crash | +10 to +30 pts | 5-20 days | Sell cash-secured puts if you want the stock |
| Sector panic | +8 to +20 pts | 1-3 weeks | Sell iron condors on the most affected names |

**The IV Reversion Edge:**
- IV spikes 2-3x faster than it compresses
- But IV DOES compress — it always mean-reverts
- By selling into the spike, you collect maximum premium and benefit from the inevitable compression

### 3.3 Best Sectors/Tickers for Selling Premium (Most Reliable Setups)

Based on the IV analysis, these names show the most consistent and exploitable premium:

| Ticker | Sector | Avg IV/RV | Avg IV Premium | Why It's Reliable | Best Sell Strategy |
|--------|--------|-----------|----------------|-------------------|-------------------|
| **MSTR** | Fintech/Crypto | 1.21 | +14.3 pts | Crypto proxy. IV always exceeds realized. Massive premium. | Iron condors, strangles |
| **MARA** | Fintech/Crypto | 1.24 | +14.7 pts | BTC miner. IV premium is the highest in the watchlist. | Cash-secured puts, credit spreads |
| **COIN** | Fintech/Crypto | 1.25 | +13.8 pts | Crypto exchange. IV/RV is the highest ratio. | Put credit spreads |
| **HOOD** | Fintech/Crypto | 1.24 | +11.4 pts | Retail broker. IV consistently overpriced. | Put credit spreads |
| **AMD** | Semiconductors | 1.24 | +8.6 pts | Semi volatility is structurally rich. | Iron condors, strangles |
| **GE** | Industrials | 1.17 | +3.6 pts | IV Rank 55 — expensive vs. own history. | Credit spreads |
| **LULU** | Consumer/Retail | 1.13 | +4.3 pts | IV Rank 62 — very expensive vs. history. | Iron condors |
| **MU** | Semi Extended | 1.18 | +5.4 pts | Memory cycle = predictable IV expansion/crush. | Put credit spreads |
| **TSLA** | Consumer/Retail | 1.09 | +4.3 pts | Always expensive. High absolute IV = big premiums. | Iron condors |
| **NVDA** | Semiconductors | 1.09 | +3.4 pts | AI narrative = consistent demand for calls. | Credit spreads, butterflies |

### 3.4 Best Selling Strategies by Setup

| Market Condition | Strategy | When to Use | Max Risk | Target Return |
|-----------------|----------|-------------|----------|---------------|
| **Neutral outlook + high IV** | Iron Condor | IV Percentile > 60, range-bound stock | Width of one spread minus credit | 25-50% of max profit |
| **Bullish lean + high IV** | Put Credit Spread (Bull Put) | IV Percentile > 50, support holding | Spread width minus credit | 30-60% of max profit |
| **Bearish lean + high IV** | Call Credit Spread (Bear Call) | IV Percentile > 50, resistance holding | Spread width minus credit | 30-60% of max profit |
| **Expecting small move + very high IV** | Iron Butterfly | IV Percentile > 70, tight expected range | Width of one wing minus credit | 50-100% of max profit |
| **Willing to own stock + high IV** | Cash-Secured Put | IV Percentile > 60, want the stock at a discount | Stock purchase if assigned | Premium collected + discounted entry |
| **Own stock + high IV** | Covered Call | IV Percentile > 50, own the shares | Opportunity cost if stock rockets | Premium collected |
| **Pre-earnings IV spike** | Short Strangle | 3-5 days before earnings, IV Percentile > 60 | Unlimited (theoretically) | IV crush + premium decay |

### 3.5 SELL Entry Rules

**For Credit Spreads (Bull Put / Bear Call):**
1. IV Percentile must be > 50 (ideally > 65)
2. IV/RV must be > 1.10
3. Short strike should be at least 0.30 delta (or ~1 SD OTM)
4. Credit received should be >= 1/3 of spread width
5. DTE: 30-45 days (sweet spot for theta decay)
6. Entry: Sell at or above mid-price. Never accept the bid.

**For Iron Condors:**
1. IV Percentile must be > 60
2. Both short strikes should be ~0.20-0.30 delta
3. Total credit should be >= 1/3 of the narrower spread width
4. DTE: 30-45 days
5. Wing width: Use wider wings on high-IV names (MSTR, TSLA) to reduce gamma risk
6. Avoid iron condors within 5 days of earnings

**For Iron Butterflies:**
1. IV Percentile must be > 70 (need maximum premium)
2. Short strikes at ATM (same strike for both call and put)
3. Wings should be 10-15 points wide on names like TSLA/NVDA, 5-10 points on names like AAPL/MSFT
4. DTE: 21-30 days (shorter duration = faster decay)
5. Higher risk than iron condors — size smaller

### 3.6 SELL Exit Rules

| Exit Trigger | Action |
|--------------|--------|
| Profit reaches 50% of max | Close the entire position (or 75% if confident) |
| Profit reaches 25% of max AND DTE < 14 | Close. The remaining theta is minimal, risk increases. |
| Underlying touches short strike | Roll the tested side out in time and/or adjust strike |
| Underlying breaches short strike by > 1 SD | Close or roll to reduce delta. Do NOT let it run. |
| IV collapses below 40th percentile | Consider closing early — you captured the IV compression |
| 21 DTE reached with < 25% profit | Evaluate: hold for theta or close to free capital |
| Loss reaches 2x credit received | Close. Respect the stop. No averaging down on short premium. |

---

## 4. Regime Detection

### 4.1 The Regime Dashboard

Track these metrics DAILY to determine whether the market favors buying or selling premium:

| Metric | BUY Premium Regime | NEUTRAL | SELL Premium Regime | Current (May 2026) |
|--------|-------------------|---------|---------------------|-------------------|
| **VIX** | < 14 | 14-20 | > 20 | ~15-18 (neutral-lean sell) |
| **VIX3M/VIX Ratio** | > 1.10 (contango) | 0.95-1.10 | < 0.95 (backwardation) | ~1.05 (neutral) |
| **SPY IV/RV** | < 0.90 | 0.90-1.10 | > 1.10 | ~1.17 (sell) |
| **% of Tickers with IV/RV > 1.15** | < 25% | 25-60% | > 60% | ~85% (strong sell) |
| **Put/Call Ratio (CBOE)** | > 1.10 (fear) | 0.80-1.10 | < 0.80 (greed) | ~0.85 (neutral) |
| **SKEW Index** | > 140 (tail fear priced) | 130-140 | < 130 | ~135 (neutral) |
| **VVIX (VIX of VIX)** | < 85 | 85-110 | > 110 | ~95 (neutral) |

### 4.2 Regime Classification Rules

**BUY PREMIUM REGIME (Green Light for Long Options):**
- VIX < 14 AND SPY IV/RV < 0.90
- OR: VIX < 15 AND > 50% of watchlist tickers have IV/RV < 1.0
- OR: Market has been trending up for 20+ days with declining IV (complacency)
- Action: Shift allocation to 60% long premium strategies, 40% short

**NEUTRAL REGIME (Balanced):**
- VIX 14-20
- IV/RV mixed across sectors
- Action: 50/50 split. Focus on defined-risk strategies (debit spreads, credit spreads). Avoid naked positions.

**SELL PREMIUM REGIME (Red Light for Long Options):**
- VIX > 20 OR > 60% of tickers have IV/RV > 1.15
- OR: VIX just spiked 5+ points in a week
- Action: Shift allocation to 70% short premium strategies, 30% long. Focus on credit spreads, iron condors, covered calls.

**CURRENT REGIME (May 2026): STRUCTURALLY EXPENSIVE**
- Every single ticker has IV/RV > 1.0
- Fintech/Crypto has IV/RV of 1.24 average
- Market Indexes have IV/RV of 1.19
- This is a SELL PREMIUM regime across the board
- BUY premium opportunities are limited to TMO (IV Rank 28), AAPL (IV Rank 34), VRTX (IV Rank 32)

### 4.3 Sector Rotation Signals

Watch for IV divergences between sectors — they signal rotation:

| Signal | What It Means | Action |
|--------|---------------|--------|
| **Semis IV rising, Healthcare IV falling** | Risk-on rotation into growth | Buy healthcare puts / sell semi calls |
| **Energy IV spiking, Tech IV stable** | Geopolitical event / oil shock | Sell energy premium after spike, buy tech calls on relative weakness |
| **All sectors IV rising together** | Broad market selloff | Buy index puts (cheap hedge before IV gets extreme), then sell individual name premium |
| **Crypto IV spiking, everything else calm** | BTC-specific event | Sell crypto premium (MSTR, COIN, MARA) aggressively |
| **IV compressing across ALL sectors** | Complacency building | Start BUYING premium — the calm before the storm |
| **VIX < 12 AND all sector IV at 1-year lows** | Maximum complacency | BUY straddles/strangles on index and high-beta names. A volatility expansion is inevitable. |

### 4.4 Real-Time Metrics to Flip Strategy

Set up alerts for these threshold crossings:

| Metric | Alert: Flip to BUY | Alert: Flip to SELL |
|--------|-------------------|---------------------|
| VIX | Crosses below 13 | Crosses above 22 |
| VIX 5-day change | Drops 4+ points | Rises 4+ points |
| SPY IV/RV | Drops below 0.85 | Rises above 1.20 |
| Watchlist avg IV/RV | Drops below 0.95 | Rises above 1.20 |
| CBOE Put/Call Ratio | Rises above 1.20 | Drops below 0.65 |
| Any ticker IV Rank | Drops below 15 | Rises above 80 |

---

## 5. Mispriced Option Buying Opportunities

### 5.1 When Mark < Theoretical Value by >5%

**This is the most direct mispricing signal.** If the market is pricing an option below its theoretical fair value, you have a mathematical edge.

**How to detect:**
1. Calculate theoretical value using Black-Scholes with your own IV estimate (use 20-day realized vol as input)
2. Compare to the current mark (mid-price)
3. If mark < theoretical by > 5%, the option is underpriced

**Setup example:**
- NVDA 30-day realized vol: 38.9%
- Current ATM call IV: 35% (below realized!)
- Theoretical value at 38.9% IV: $12.50
- Current mark: $11.20
- Discount: 10.4% → BUY

**This scenario is rare in efficient markets but happens when:**
- Market makers are hedging large flows and skewing prices
- Retail is selling options en masse (e.g., YOLO put selling on meme stocks)
- Overnight gaps create pricing dislocations
- Low liquidity on specific strikes

**Entry rule:** Only buy if the mispricing is confirmed across multiple strikes (not just one odd strike). Size at 0.5-1.0% of portfolio per trade.

### 5.2 When IV Skew is Inverted

**Normal skew:** OTM puts trade at higher IV than OTM calls (fear of downside). This is the "smirk."

**Inverted skew:** OTM calls trade at higher IV than OTM puts. This happens during:
- Meme stock rallies (everyone buying calls)
- Short squeezes
- Euphoric market phases

**The trade:** When skew is inverted, the OTM PUTS are relatively CHEAP.
- Buy OTM puts on names with inverted skew
- You're buying downside protection that the market is underpricing because everyone is focused upside

**How to detect:**
1. Pull the IV chain for a given expiration
2. Calculate the 25-delta put IV minus the 25-delta call IV (skew)
3. Normal skew: 25d put IV - 25d call IV = +3 to +8 points
4. Inverted skew: 25d put IV - 25d call IV = negative or < 0
5. If skew is inverted or near-zero, OTM puts are cheap relative to calls

**Best candidates for inverted skew:**
- Meme stocks during rallies (HOOD, MSTR during BTC runs)
- Names with heavy retail call buying
- Stocks with short squeeze potential

### 5.3 When Earnings IV Hasn't Spiked Yet

**This is a timing play.** The market prices in expected earnings moves, but the IV spike happens gradually.

**The setup:**
1. Identify an upcoming earnings date (5-10 days out)
2. Check current IV percentile — is it still below 40?
3. Check if the historical pre-earnings IV spike hasn't started yet
4. Buy options (calls or puts based on your thesis) before the IV expansion

**Historical IV spike patterns by sector:**

| Sector | IV Spike Starts | Peak Before | Magnitude | Best Time to Buy |
|--------|----------------|-------------|-----------|------------------|
| Mega-Cap Tech | 5-8 days before | 1-2 days before | +5 to +12 pts | 7-10 days before earnings |
| Semiconductors | 7-10 days before | 1-2 days before | +8 to +15 pts | 10-14 days before earnings |
| Fintech/Crypto | 10-15 days before | 1-2 days before | +15 to +40 pts | 12-18 days before earnings |
| Growth/Tech | 7-12 days before | 1-2 days before | +10 to +20 pts | 10-15 days before earnings |
| Consumer/Retail | 5-8 days before | 1-2 days before | +8 to +15 pts | 7-10 days before earnings |
| Healthcare | 3-5 days before | 1-2 days before | +2 to +5 pts | 5-7 days before earnings |
| Industrials | 5-7 days before | 1-2 days before | +4 to +8 pts | 7-10 days before earnings |

**Entry rules for pre-earnings buying:**
1. Enter 5-10 days before the expected IV spike starts
2. Use debit spreads (not naked longs) to limit vega risk if the spike doesn't materialize
3. DTE: Choose expiration that includes the earnings date
4. Exit: Close 1-2 days before earnings to capture the IV expansion (don't hold through the event unless you want binary risk)

### 5.4 Positive Expectancy Buying Setups

These are specific scenarios where buying options has historically had positive expectancy:

| Setup | Description | Expected Edge | Historical Win Rate |
|-------|-------------|---------------|---------------------|
| **Post-earnings IV crush → long straddle** | After earnings, IV crashes 20%+. If the stock keeps moving (trend continuation), a long straddle bought AFTER the crush has positive expectancy because IV is now cheap and the trend may continue. | IV expansion from new trend + directional move | ~55-60% |
| **VIX < 12 → long SPY straddle** | When VIX drops below 12, it's at the 5th percentile. Historically, VIX mean-reverts upward within 30 days 70% of the time. A long straddle on SPY with 45 DTE captures the expansion. | VIX mean reversion | ~65% |
| **Sector IV compression → diagonal on leader** | When a sector's IV compresses to the 15th percentile but the sector leader (e.g., NVDA for semis) is in an uptrend, buy a diagonal (long far-dated call, sell near-dated OTM call). | Theta decay + directional + IV expansion | ~60% |
| **IV rank < 15 + technical breakout** | When a stock's IV is at the absolute floor AND it's breaking out of a consolidation pattern, the move tends to be larger than expected because nobody is positioned for it. | Underpriced volatility + surprise move | ~55-60% |
| **Earnings miss panic → long calls 2-3 days after** | After a bad earnings miss, IV spikes, the stock gaps down, then IV starts to compress. If the miss is an overreaction, buying calls 2-3 days after captures the bounce with declining IV cost. | Mean reversion + IV compression tailwind | ~50-55% |

---

## 6. Per-Sector Playbook

### 6.1 Market Indexes (SPY, QQQ)

| Attribute | Details |
|-----------|---------|
| **Typical IV Range** | SPY: 12-22%, QQQ: 16-30% |
| **Current IV** | SPY: 14.2% (Rank 32), QQQ: 19.8% (Rank 38) |
| **IV/RV** | SPY: 1.17, QQQ: 1.20 |
| **Key Catalysts** | FOMC meetings, CPI/NFP data, geopolitical events, quarterly GDP, treasury auctions |

**When IV is LOW (IV Percentile < 30, VIX < 14):**

| Strategy | Execution |
|----------|-----------|
| **Long Put (Hedge)** | Buy SPY puts 5-10% OTM, 45-60 DTE. This is portfolio insurance at a discount. Cost: 1-2% of portfolio. |
| **Long Straddle** | Buy ATM straddle on SPY when VIX < 12. 45-60 DTE. Target: VIX expansion to 18+. Expected return: 30-60%. |
| **Call Debit Spread (QQQ)** | If tech is in an uptrend but QQQ IV is < 25th percentile, buy call debit spreads. 30-45 DTE. Buy ATM, sell 1 SD OTM. |
| **Calendar Spread** | Sell 7-14 DTE ATM option, buy 45-60 DTE ATM option. Profits from front-month theta decay while long back-month vega. Best when VIX term structure is in contango. |

**When IV is HIGH (IV Percentile > 60, VIX > 20):**

| Strategy | Execution |
|----------|-----------|
| **Put Credit Spread (SPY)** | Sell 0.20 delta put, buy 0.10 delta put. 30-45 DTE. Collect $1-2 credit on $5-wide spread. Target 50% profit. |
| **Iron Condor (QQQ)** | Sell 0.20 delta call spread + 0.20 delta put spread. 30-45 DTE. Collect $2-3 total credit. |
| **Covered Call (if holding ETF)** | If you hold SPY/QQQ shares, sell 0.15-0.20 delta calls, 21-30 DTE. Generate 1-2% monthly income. |

### 6.2 Mega-Cap Tech (AAPL, MSFT, GOOGL, META, AMZN)

| Attribute | Details |
|-----------|---------|
| **Typical IV Range** | AAPL: 18-30%, MSFT: 20-32%, GOOGL: 22-36%, META: 28-48%, AMZN: 24-38% |
| **Current IV** | AAPL: 22.1%, MSFT: 23.8%, GOOGL: 26.4%, META: 32.5%, AMZN: 27.9% |
| **IV/RV** | AAPL: 1.09, MSFT: 1.09, GOOGL: 1.12, META: 1.17, AMZN: 1.13 |
| **Key Catalysts** | Earnings (Jan/Apr/Jul/Oct clusters), product launches (Apple Sept), AI announcements, regulatory news |

**When IV is LOW (IV Percentile < 30):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Long Calls (directional)** | AAPL, MSFT | These have the cheapest IV. Buy 45-60 DTE calls when technical breakout occurs. |
| **Calendar Spreads** | AAPL, MSFT, AMZN | Sell 10-14 DTE, buy 45-60 DTE. Great when IV is in the 15-25th percentile. |
| **Diagonal Spreads** | MSFT, GOOGL | Long 60-90 DTE call at one strike, short 14-21 DTE calls at higher strike. |
| **Long Straddle (pre-product)** | AAPL | Buy 7-10 days before Apple product launch. IV hasn't spiked yet. |

**When IV is HIGH (IV Percentile > 60):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Iron Condor** | META, AMZN | These have the highest IV in the group. Sell 0.20 delta wings, 30-45 DTE. |
| **Credit Spreads** | GOOGL, META | Sell put credit spreads on dips, call credit spreads on rallies. |
| **Covered Calls** | AAPL, MSFT | If you hold shares, sell calls during IV spikes. Great income generator. |
| **Pre-Earnings Strangle Sale** | META, AMZN | Sell strangles 3-5 days before earnings. META has -8 to -14 pt IV crush. |

### 6.3 Semiconductors (NVDA, AMD, AVGO)

| Attribute | Details |
|-----------|---------|
| **Typical IV Range** | NVDA: 35-65%, AMD: 38-60%, AVGO: 25-45% |
| **Current IV** | NVDA: 42.3%, AMD: 44.8%, AVGO: 31.2% |
| **IV/RV** | NVDA: 1.09, AMD: 1.24, AVGO: 1.15 |
| **Key Catalysts** | Earnings (staggered monthly), AI chip demand reports, export restrictions, customer wins (Microsoft, Meta, Google cloud spending) |

**When IV is LOW (IV Percentile < 30):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Long Calls (AI momentum)** | NVDA | When semi IV compresses but AI narrative is strong, buy NVDA calls 45-60 DTE. |
| **Debit Spreads** | AMD, AVGO | Buy call debit spreads. Lower IV makes the debit cheaper. |
| **Calendar Spreads** | AVGO | AVGO has the lowest IV in the group. Sell 10-14 DTE, buy 45-60 DTE. |
| **Long Straddle (pre-earnings)** | NVDA | Buy 10-14 days before NVDA earnings. IV typically spikes +8-15 pts. |

**When IV is HIGH (IV Percentile > 60):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Iron Condor** | AMD, NVDA | AMD has IV/RV of 1.24 — the most overpriced in the sector. Sell wide iron condors. |
| **Put Credit Spread** | NVDA, AVGO | On pullbacks, sell put credit spreads. NVDA has strong support levels. |
| **Pre-Earnings Strangle** | NVDA, AMD | Sell 5-7 days before earnings. NVDA IV crush is -10 to -15 pts. |
| **Butterfly** | AVGO | AVGO tends to have tighter ranges. Sell iron butterflies when IV Rank > 60. |

### 6.4 Fintech/Crypto (MSTR, COIN, HOOD, MARA)

| Attribute | Details |
|-----------|---------|
| **Typical IV Range** | MSTR: 60-140%, COIN: 50-110%, HOOD: 45-90%, MARA: 60-130% |
| **Current IV** | MSTR: 82.5%, COIN: 68.4%, HOOD: 58.2%, MARA: 76.8% |
| **IV/RV** | MSTR: 1.21, COIN: 1.25, HOOD: 1.24, MARA: 1.24 |
| **Key Catalysts** | BTC price, ETH price, crypto regulation, earnings (Feb/May/Aug/Nov clusters), ETF flows, halving events |

**When IV is LOW (IV Percentile < 30) — RARE BUT HIGH-CONVICTION:**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Long Calls (BTC breakout)** | MSTR, COIN | When crypto IV compresses but BTC is breaking out, buy calls. IV is cheapest before the next run. |
| **Long Straddles** | MSTR, MARA | When all four names have IV Percentile < 20 simultaneously, a big move is coming. Buy straddles 45-60 DTE. |
| **Call Debit Spreads** | HOOD | HOOD is the most "normal" of the group. Buy call debit spreads on fintech momentum. |
| **Calendar Spreads** | COIN | Sell 10 DTE, buy 45 DTE. Capture the inevitable IV expansion. |

**When IV is HIGH (IV Percentile > 60) — THE PRIMARY REGIME:**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Iron Condor** | MSTR, COIN, MARA | These names have IV premiums of 11-15 points. Sell WIDE iron condors. 45 DTE minimum (they can move fast). |
| **Cash-Secured Puts** | MARA, COIN | If willing to own the stock, sell CSPs 0.20-0.25 delta. Collect massive premium. |
| **Put Credit Spreads** | HOOD, COIN | On BTC dips, sell put credit spreads. The fear premium is enormous. |
| **Pre-Earnings Strangle** | All four | Sell 5-7 days before earnings. MARA IV crush is -25 to -40 pts. MSTR crush is -20 to -35 pts. |
| **Short Butterflies** | MSTR | When MSTR IV Rank > 70, sell iron butterflies with wide wings (20-30 point wings). |

**⚠️ WARNING:** These are the most dangerous names to trade. BTC can move 10% in a day. Position size at 0.5-1.0% of portfolio per trade maximum. Always use defined risk (spreads, not naked shorts).

### 6.5 Consumer/Retail (TSLA, UBER, LULU, CMG)

| Attribute | Details |
|-----------|---------|
| **Typical IV Range** | TSLA: 40-75%, UBER: 28-48%, LULU: 28-52%, CMG: 22-40% |
| **Current IV** | TSLA: 52.8%, UBER: 34.2%, LULU: 38.5%, CMG: 28.6% |
| **IV/RV** | TSLA: 1.09, UBER: 1.15, LULU: 1.13, CMG: 1.13 |
| **Key Catalysts** | Earnings (Jan/Apr/Jul/Oct for TSLA/CMG), delivery numbers (TSLA), retail sales data, consumer sentiment, Fed policy (rates affect consumer spending) |

**When IV is LOW (IV Percentile < 30):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Long Calls (TSLA momentum)** | TSLA | When TSLA IV drops to the 20-25th percentile and the stock is trending up, buy calls 45-60 DTE. |
| **Call Debit Spreads** | CMG, UBER | CMG and UBER have more predictable businesses. Buy debit spreads on confirmed trends. |
| **Calendar Spreads** | CMG | CMG is the most predictable name in the sector. Calendars work well during IV compression. |
| **Long Straddle (pre-delivery)** | TSLA | Buy 5-7 days before TSLA delivery numbers. The move is often bigger than expected. |

**When IV is HIGH (IV Percentile > 60):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Iron Condor** | TSLA, LULU | LULU has IV Rank 62 — very expensive vs. history. TSLA always has high premium. |
| **Put Credit Spread** | UBER, CMG | These have steady uptrends. Sell put credit spreads on pullbacks. |
| **Covered Call** | CMG | If you hold CMG shares, sell calls during IV spikes. CMG's steady growth makes this ideal. |
| **Pre-Earnings Strangle** | TSLA | TSLA IV crush is -10 to -15 pts. Sell strangles 3-5 days before. |

### 6.6 Healthcare/Biotech (TMO, REGN, VRTX)

| Attribute | Details |
|-----------|---------|
| **Typical IV Range** | TMO: 16-25%, REGN: 20-32%, VRTX: 19-30% |
| **Current IV** | TMO: 18.4%, REGN: 22.6%, VRTX: 21.2% |
| **IV/RV** | TMO: 1.10, REGN: 1.16, VRTX: 1.14 |
| **Key Catalysts** | Earnings (Feb/May/Aug/Nov), FDA decisions, clinical trial results, M&A, Medicare pricing policy |

**When IV is LOW (IV Percentile < 30):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Long Calls (pipeline catalysts)** | REGN, VRTX | When IV is < 25th percentile and a pipeline catalyst is 2-4 weeks out, buy calls. Healthcare IV doesn't spike until close to the event. |
| **Debit Spreads** | TMO, VRTX | TMO has the lowest IV in the entire watchlist (Rank 28). Buy call debit spreads on steady growth. |
| **Long Straddle (pre-FDA)** | REGN | Buy 5-7 days before PDUFA dates. IV will spike as the date approaches. |
| **Calendar Spreads** | TMO | TMO is the steadiest name. Calendars during low IV periods generate consistent returns. |

**When IV is HIGH (IV Percentile > 60):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Credit Spreads** | REGN | REGN has the highest IV in healthcare. Sell credit spreads when IV Rank > 60. |
| **Covered Calls** | VRTX | If you hold VRTX shares, sell calls during IV spikes. CF franchise provides steady income. |
| **Iron Condor** | REGN, VRTX | Healthcare moves are small. Iron condors with tight wings work well. |
| **Put Credit Spread** | TMO | TMO rarely drops more than 5% in a month. Sell put credit spreads confidently. |

**Note:** Healthcare has the SMALLEST IV crush (3-5 pts) and smallest moves (2-4%). This makes it a poor sector for earnings IV strategies but excellent for steady theta selling and strategic buying during low IV.

### 6.7 Industrials/Energy (GE, CAT, XOM)

| Attribute | Details |
|-----------|---------|
| **Typical IV Range** | GE: 20-35%, CAT: 18-30%, XOM: 15-26% |
| **Current IV** | GE: 24.8%, CAT: 21.4%, XOM: 19.2% |
| **IV/RV** | GE: 1.17, CAT: 1.15, XOM: 1.10 |
| **Key Catalysts** | Earnings (tight clusters in Apr/Jul/Oct/Jan), GDP data, oil prices, defense spending, infrastructure bills, China economic data |

**When IV is LOW (IV Percentile < 30):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Long Calls (economic recovery)** | CAT, GE | When industrial IV compresses but PMI/manufacturing data is improving, buy calls. |
| **Call Debit Spreads** | XOM | When oil is stable/rising and XOM IV is < 25th percentile, buy call debit spreads. |
| **Calendar Spreads** | XOM | XOM is the most predictable. Calendars during low IV generate steady returns. |
| **Long Straddle (pre-GDP)** | GE, CAT | Buy 5-7 days before major GDP or PMI releases if IV hasn't spiked. |

**When IV is HIGH (IV Percentile > 60):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Credit Spreads** | GE | GE has IV Rank 55 and IV above its 52-week average. Sell credit spreads. |
| **Iron Condor** | CAT, GE | Industrials have tight ranges. Iron condors with 10-15 point wings work well. |
| **Covered Calls** | XOM | XOM pays a dividend AND you can sell calls. Double income. |
| **Put Credit Spread** | CAT | CAT has strong support at economic cycle bottoms. Sell puts on dips. |

### 6.8 Growth/Tech (PLTR, PANW, SNOW)

| Attribute | Details |
|-----------|---------|
| **Typical IV Range** | PLTR: 40-80%, PANW: 32-52%, SNOW: 35-58% |
| **Current IV** | PLTR: 55.4%, PANW: 38.6%, SNOW: 42.8% |
| **IV/RV** | PLTR: 1.10, PANW: 1.14, SNOW: 1.11 |
| **Key Catalysts** | Earnings (Feb/May/Aug/Nov clusters, 2-4 weeks after mega-caps), government contracts (PLTR), cybersecurity breaches (PANW), data cloud adoption (SNOW), AI spending |

**When IV is LOW (IV Percentile < 30):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Long Calls (AI momentum)** | PLTR | PLTR is retail-driven and can explode. When IV is cheap and AI narrative is hot, buy calls 45-60 DTE. |
| **Call Debit Spreads** | PANW, SNOW | These have more predictable businesses. Buy debit spreads on confirmed trends. |
| **Calendar Spreads** | PANW | PANW has the steadiest growth. Calendars work well during IV compression. |
| **Long Straddle (pre-earnings)** | PLTR | PLTR IV crush is -12 to -18 pts (biggest in growth tech). Buy straddles 10-14 days before. |

**When IV is HIGH (IV Percentile > 60):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Iron Condor** | PLTR, SNOW | PLTR has IV of 55%+ and can move wildly. Sell WIDE iron condors (20+ point wings). |
| **Credit Spreads** | PANW | PANW is the most predictable growth name. Sell credit spreads with confidence. |
| **Pre-Earnings Strangle** | PLTR, SNOW | PLTR IV crush is -12 to -18 pts. Sell strangles 3-5 days before earnings. |
| **Covered Call** | PANW | If you hold PANW shares, sell calls during IV spikes. Cybersecurity demand is structural. |

### 6.9 Semiconductors Extended (QCOM, MU, INTC)

| Attribute | Details |
|-----------|---------|
| **Typical IV Range** | QCOM: 24-40%, MU: 30-52%, INTC: 28-48% |
| **Current IV** | QCOM: 28.4%, MU: 36.2%, INTC: 32.8% |
| **IV/RV** | QCOM: 1.17, MU: 1.18, INTC: 1.15 |
| **Key Catalysts** | Earnings (fills gaps in main semi calendar), memory pricing (MU), handset cycles (QCOM), foundry turnaround (INTC), AI chip demand |

**When IV is LOW (IV Percentile < 30):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Long Calls (memory cycle)** | MU | Memory is cyclical. When MU IV is cheap and memory prices are rising, buy calls. |
| **Call Debit Spreads** | QCOM | QCOM has steady handset business. Buy debit spreads on iPhone cycle strength. |
| **Calendar Spreads** | QCOM | QCOM is the most predictable of the three. Calendars during low IV work well. |
| **Long Straddle (pre-earnings)** | MU | MU has the biggest moves. Buy straddles 10-14 days before earnings. |

**When IV is HIGH (IV Percentile > 60):**

| Strategy | Best Tickers | Execution |
|----------|-------------|-----------|
| **Iron Condor** | MU, INTC | Both have IV Ranks > 50. Sell iron condors. MU has wider expected range. |
| **Put Credit Spread** | QCOM | QCOM has steady fundamentals. Sell put credit spreads on pullbacks. |
| **Cash-Secured Put** | INTC | INTC is a turnaround story. If you want the stock at a discount, sell CSPs and collect fat premium. |
| **Pre-Earnings Strangle** | MU, INTC | Both have -6 to -10 pt IV crush. Sell 3-5 days before earnings. |

---

## 7. Position Sizing

### 7.1 Buying Premium (Long Options)

| Strategy | Max Position Size | Portfolio Allocation | Notes |
|----------|------------------|---------------------|-------|
| **Long Calls/Puts** | 1-2% of portfolio per trade | Max 10% total in long premium | High risk of 100% loss. Size accordingly. |
| **Debit Spreads** | 2-3% of portfolio per trade | Max 15% total in debit spreads | Defined risk. Can size slightly larger than naked longs. |
| **Calendar Spreads** | 2-4% of portfolio per trade | Max 15% total | Lower risk than naked longs. Defined max loss = debit paid. |
| **Diagonal Spreads** | 2-3% of portfolio per trade | Max 10% total | Defined risk on the long leg. Short leg has unlimited risk. |
| **Long Straddles/Strangles** | 1-2% of portfolio per trade | Max 8% total | Very expensive. Only use when IV is extremely cheap (Percentile < 15). |
| **Portfolio Hedging (long puts)** | 0.5-1% of portfolio | Max 5% | This is insurance. Cost should be manageable. |

### 7.2 Selling Premium (Short Options)

| Strategy | Max Position Size | Portfolio Allocation | Notes |
|----------|------------------|---------------------|-------|
| **Credit Spreads** | 3-5% of portfolio per trade | Max 25% total in credit spreads | Defined risk. Can size larger than long premium. |
| **Iron Condors** | 3-5% of portfolio per trade | Max 20% total | Defined risk. Size based on the narrower spread width. |
| **Iron Butterflies** | 2-3% of portfolio per trade | Max 10% total | Higher gamma risk. Size smaller than iron condors. |
| **Cash-Secured Puts** | 5-10% of portfolio per trade | Max 30% total | You must be willing to own the stock. Cash must be reserved. |
| **Covered Calls** | As needed (if you own the stock) | N/A | No additional capital required. Income on existing positions. |
| **Short Strangles** | 1-2% of portfolio per trade | Max 5% total | UNLIMITED RISK. Size very small. Only for experienced traders. |

### 7.3 Allocation by Regime

| Regime | Long Premium Allocation | Short Premium Allocation | Neutral/Hedge |
|--------|-----------------------|-------------------------|---------------|
| **BUY Premium (VIX < 14)** | 60% | 25% | 15% (portfolio hedges) |
| **NEUTRAL (VIX 14-20)** | 40% | 40% | 20% (hedges + cash) |
| **SELL Premium (VIX > 20)** | 20% | 65% | 15% (tail risk hedges) |
| **PANIC (VIX > 30)** | 10% | 70% | 20% (protective puts + cash) |

### 7.4 Per-Ticker Exposure Limits

| Ticker Type | Max Single Ticker Exposure | Max Sector Exposure |
|-------------|---------------------------|---------------------|
| **Mega-Cap (AAPL, MSFT, GOOGL)** | 5% of portfolio | 15% total |
| **High IV (MSTR, MARA, COIN)** | 2% of portfolio | 8% total |
| **Mid IV (NVDA, TSLA, PLTR)** | 3% of portfolio | 12% total |
| **Low IV (TMO, XOM, CAT)** | 5% of portfolio | 15% total |
| **Index (SPY, QQQ)** | 8% of portfolio | 15% total |

**Correlation adjustment:** If you have positions in NVDA, AMD, AND AVGO simultaneously, treat them as ONE position for sizing purposes. They are highly correlated. Reduce individual sizes by 30-50%.

---

## 8. Risk Management

### 8.1 Universal Rules

1. **Never risk more than 2% of portfolio on a single directional bet** (long call/put)
2. **Always define your max loss before entering** — if you can't calculate it, don't take the trade
3. **Never average down on a losing short premium position** — close or roll, don't add
4. **Respect stops:** Long options → close if thesis breaks. Short options → close at 2x credit
5. **No more than 5 concurrent positions per sector** — diversification matters
6. **Earnings blackout:** Don't open new premium selling positions within 2 days of earnings on that name
7. **Weekly review:** Every Sunday, review all open positions. Close any where the thesis is stale.

### 8.2 Buying Premium Specific Rules

| Rule | Detail |
|------|--------|
| **Max holding period** | 45 days for directional, 30 days for calendars |
| **Time stop** | Close if no progress after 21 days |
| **IV expansion stop** | Close if IV reaches 70th+ percentile (you captured the expansion) |
| **Profit target** | 100% on longs, 50% on debit spreads |
| **Loss limit** | 50% of premium paid (or thesis broken) |
| **Never buy** | Options with < 7 DTE unless it's a specific event play |

### 8.3 Selling Premium Specific Rules

| Rule | Detail |
|------|--------|
| **Profit target** | 50% of max profit (or 25% if DTE < 14) |
| **Loss stop** | 2x credit received |
| **Rolling rule** | If tested, roll out 1-2 weeks for a credit. Never roll for a debit. |
| **Adjustment rule** | If delta exceeds 0.40 on the short side, add a hedge or close |
| **Never sell** | Naked options (strangles/straddles) without a defined stop loss |
| **Earnings rule** | Close all earnings premium selling positions before the announcement OR be prepared for the binary outcome |

---

## 9. Real-Time Monitoring Checklist

### 9.1 Daily Checks (5 minutes)

- [ ] VIX level and 5-day change
- [ ] SPY IV/RV ratio
- [ ] Put/Call ratio (CBOE total)
- [ ] Any IV Rank crossings (any ticker crossing above 70 or below 20)
- [ ] Earnings this week and next week
- [ ] Open positions: any approaching profit targets or loss stops

### 9.2 Weekly Checks (15 minutes)

- [ ] Recalculate IV/RV for all 28 tickers
- [ ] Check sector IV averages for regime shifts
- [ ] Review VIX term structure (contango vs backwardation)
- [ ] Check for upcoming catalysts (earnings, FDA, product launches, macro events)
- [ ] Review position sizing vs. limits
- [ ] Identify any new mispricing opportunities (mark vs theoretical)
- [ ] Update the regime dashboard

### 9.3 Monthly Checks (30 minutes)

- [ ] Full re-run of IV analysis (regenerate `02_iv_analysis.md`)
- [ ] Check if any tickers have changed their IV behavior profile
- [ ] Review win rate and profitability by strategy type
- [ ] Adjust position sizing based on recent performance
- [ ] Evaluate if sector composition needs updating
- [ ] Review and update this playbook based on new learnings

---

## 10. Decision Flowchart

```
START: What's the current regime?
│
├─ VIX < 14 AND IV/RV < 0.90 → BUY PREMIUM REGIME
│  │
│  ├─ Does the ticker have IV Percentile < 30?
│  │  ├─ YES → Long calls/puts or debit spreads
│  │  └─ NO → Wait for IV to compress further
│  │
│  ├─ Is there a catalyst in 5-15 days?
│  │  ├─ YES → Buy options early (before IV spikes)
│  │  └─ NO → Use calendar/diagonal spreads
│  │
│  └─ Allocation: 60% long premium, 25% short, 15% hedge
│
├─ VIX 14-20 → NEUTRAL REGIME
│  │
│  ├─ Check each ticker individually:
│  │  ├─ IV Percentile < 30 → BUY on this name
│  │  ├─ IV Percentile > 60 → SELL on this name
│  │  └─ IV Percentile 30-60 → Wait or use defined-risk spreads
│  │
│  └─ Allocation: 40% long, 40% short, 20% hedge/cash
│
└─ VIX > 20 OR >60% tickers have IV/RV > 1.15 → SELL PREMIUM REGIME
   │
   ├─ Rank tickers by IV/RV and IV Premium
   │  ├─ Top 5 (highest IV/RV) → Aggressive selling (iron condors, strangles)
   │  ├─ Next 10 (moderate IV/RV) → Credit spreads
   │  └─ Bottom 5 (lowest IV/RV) → Selective buying only
   │
   ├─ Any IV just spiked 10+ points?
   │  ├─ YES → Sell immediately (mean reversion play)
   │  └─ NO → Wait for spike or sell systematically
   │
   └─ Allocation: 20% long, 65% short, 15% tail hedge
```

---

## Appendix: Quick Reference Cards

### BUY Premium Quick Card

```
┌─────────────────────────────────────────────────┐
│  WHEN TO BUY OPTIONS                            │
├─────────────────────────────────────────────────┤
│  Green light:                                   │
│  ☐ IV Percentile < 30                           │
│  ☐ IV/RV < 0.90                                 │
│  ☐ VIX < 14                                     │
│  ☐ Catalyst in 5-15 days                        │
│                                                 │
│  Strategies:                                    │
│  • IV < 20: Long straddles, calendars           │
│  • IV 20-30: Long calls/puts, debit spreads     │
│  • Pre-catalyst: Buy before IV spikes           │
│                                                 │
│  Best names to buy:                             │
│  TMO, AAPL, VRTX, XOM, CAT, CMG                 │
│                                                 │
│  Position size: 1-3% per trade                  │
│  DTE: 30-90 days                                │
│  Exit: 50-100% profit or 50% loss               │
└─────────────────────────────────────────────────┘
```

### SELL Premium Quick Card

```
┌─────────────────────────────────────────────────┐
│  WHEN TO SELL OPTIONS                           │
├─────────────────────────────────────────────────┤
│  Green light:                                   │
│  ☐ IV Percentile > 60                           │
│  ☐ IV/RV > 1.15                                 │
│  ☐ VIX > 20                                     │
│  ☐ IV just spiked 10+ points                    │
│                                                 │
│  Strategies:                                    │
│  • IV > 70: Iron condors, butterflies           │
│  • IV 50-70: Credit spreads, CSPs               │
│  • Pre-earnings: Short strangles                │
│                                                 │
│  Best names to sell:                            │
│  MSTR, MARA, COIN, HOOD, AMD, GE, LULU          │
│                                                 │
│  Position size: 3-5% per trade                  │
│  DTE: 21-45 days                                │
│  Exit: 50% max profit or 2x credit loss         │
└─────────────────────────────────────────────────┘
```

---

*This framework is a living document. Update it as new data arrives from the continuous scraping pipeline. The IV levels and percentiles change daily — the STRATEGIES and RULES here are timeless, but the specific thresholds should be recalibrated quarterly based on realized performance.*

*Last updated: 2026-05-02*
*Cross-references: 01_liquidity_analysis.md, 02_iv_analysis.md, 03_correlation_analysis.md, 04_earnings_analysis.md*
