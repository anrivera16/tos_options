# Bull Put Credit Spread Strategy

5-7 DTE SPY Bull Put Credit Spread -- detailed strategy document based on 6-month backtest (Jul-Dec 2025).

---

## Overview

**What:** Sell a put spread on SPY every trading day, holding to expiry.

**Why:** Credit spreads define your max risk upfront. Short duration minimizes gamma exposure and theta decay works in your favor. SPY has the most liquid options chain in the world.

**Goal:** Generate consistent income with defined risk. Target 3-5% monthly return on capital at risk.

---

## Trade Structure

A **bull put credit spread** (also called a short put vertical) involves:

1. **SELL** 1 put at strike K_short (higher strike)
2. **BUY**  1 put at strike K_long  (lower strike, protection)

Both legs share the same expiration date.

```
Example:  SPY trading at $680

  SELL  675P @ $3.50   (short leg)
  BUY   670P @ $1.50   (long leg)
  
  Net credit received: $2.00 ($200 per contract)
  Spread width:        $5.00 ($500 per contract)
  Max risk:            $3.00 ($300 per contract) = width - credit
  Breakeven:           $673.00 = K_short - credit
```

### Profit/Loss Diagram

```
Profit
  $200 |---------*
        |         \
  $0    |          \---------*----------------
        |                     \
 -$300  |                      *-------------
        |______________________________________
        K_long    K_short    K_short-credit
        $670      $675       $673
                         Underlying at expiry
```

- **Max profit** = credit received ($200). Achieved when SPY stays above K_short at expiry.
- **Max loss** = width - credit ($300). Realized when SPY drops below K_long at expiry.
- **Breakeven** = K_short - credit ($673). SPY must close above this to profit.

---

## Entry Rules

### Timing
- Enter at market open (9:30 AM ET) each trading day
- No day-of-week filter -- the backtest enters every day

### Expiration Selection
- Target **7 DTE** (calendar days to expiration)
- Acceptable range: **5-7 DTE**
- Prefer the expiry closest to 7 DTE when multiple are available
- Standard SPY options expire Monday/Wednesday/Friday, plus 0DTE daily

### Strike Selection

**Short leg (the one you sell):**
- Target approximately **15 delta** (OTM put)
- In practice, since we don't have real-time Greeks from the daily aggregate data, we approximate delta by ranking all available puts by strike distance from ATM
- The short put should be **2-5% below** the current SPY price

**Long leg (the one you buy for protection):**
- Strike = K_short - $5.00
- This defines your max loss and caps risk

**Spread width:** $5.00

### Position Sizing
- 1 contract per trade with $20K bankroll
- Each spread risks approximately $200-300 per contract
- Capital at risk per trade: ~1-1.5% of bankroll
- No overlapping positions are summed in the backtest (each day is independent)

---

## Exit Rules

### Primary: Hold to Expiry
- The default approach: no early exit
- Let theta decay work through the full duration
- Both legs expire OTM = keep full credit

### Considered but NOT currently implemented:
- **50% profit target:** Close when spread price drops to 50% of credit received
- **Stop loss at 2x credit:** Close if spread price doubles from entry
- These require intraday data (minute aggs) to model realistically

---

## Backtest Results (Jul-Dec 2025)

### Overall Performance

```
Metric                    Value
------------------------  --------
Total trades              120
Win rate                  60.8%
Total P&L (per contract)  $5,298
Average P&L per trade     $44.15
Average credit received   $245.75
Average max risk          $253.73
Average DTE               7.0
Expectancy per trade      $44.15
Projected annual (52wk)   $2,296
Risk:Reward ratio         1:0.97
```

### Monthly Breakdown

```
Month   Trades  W/L    Win%   P&L        Credits   R:R     Return/Risk
------  ------  -----  ----   --------   -------   -----   -----------
Jul 25    22    14/8    64%   +$1,289    $5,022    1:1.19    21.6%
Aug 25    20    11/9    55%   +$  541    $3,908    1:1.56     8.9%
Sep 25    21    19/2    90%   +$2,851    $3,711    1:1.83    42.0%
Oct 25    21    11/10   52%   -$  332    $4,119    1:1.55    -5.2%
Nov 25    18    10/8    56%   +$1,304    $6,758    1:0.33    58.2%
Dec 25    18    8/10    44%   -$  355    $5,972    1:0.51   -11.7%
```

### Outcome Distribution

```
Outcome         Count   Avg P&L     Description
-------------   -----   --------    --------------------------------
FULL_WIN          55    +$193       Both legs expire OTM, keep full credit
PARTIAL_WIN       16    +$159       Short leg slightly ITM, still profitable
PARTIAL_LOSS      26    -$144       Short leg ITM eats into credit
MAX_LOSS          23    -$179       Both legs deep ITM, max loss hit
```

### Key Observations

1. **September was the best month** (90% win rate, $2,851 profit). Steady uptrend with low volatility. Perfect environment for credit spreads.

2. **October and December were net negative.** Elevated volatility (SPY dropped ~5% mid-October, sell-off resumed in December). Credit spreads get hurt in trending down markets.

3. **Win rate is only part of the story.** At 60.8%, you win more than you lose, but the average win ($187) nearly equals the average loss ($177). This means the edge is thin -- one bad streak can wipe weeks of gains.

4. **18 trades had anomalous data** where the raw P&L exceeded theoretical bounds. These were bounded to max profit/loss in the backtest, but the data quality from daily aggregates is imperfect.

5. **The strikes are too tight in high-vol months.** In November/December, the short leg was only 0-2% OTM (versus 3-5% in calmer months). The delta proxy picks strikes closer to ATM when IV is elevated, which increases loss frequency.

---

## Risk Management

### Per-Trade Risk
- Max loss per spread = $5.00 - credit received ≈ $250-350
- This is known at entry and cannot be exceeded
- No margin calls, no unlimited risk

### Portfolio Risk
- With daily entries, you may have up to 7 overlapping positions
- Worst case: 7 simultaneous max losses = ~$2,100 (10.5% of $20K)
- In practice, consecutive max losses are rare (the backtest shows at most 5 in a row, late July)

### Market Regime Risk
- This strategy profits from range-bound to bullish markets
- Sustained downtrends are the primary risk (see Oct and Dec results)
- Consider reducing position size or skipping trades during:
  - Major economic events (CPI, FOMC, jobs reports)
  - VIX > 25
  - SPY below its 20-day moving average

### Position Sizing Guidelines
```
Bankroll    Contracts    Max Daily Risk    Notes
---------   ----------   ---------------   -----
$10,000     1            ~$300             Conservative start
$20,000     1-2          ~$500             Current level
$25,000     2            ~$600             Add QQQ
$35,000     2-3          ~$800             Add individual names
```

---

## Strategy Parameters (Current Defaults)

```
Parameter          Default    Range         Notes
-----------        -------    ----------    --------------------------
Ticker             SPY        SPY only      Most liquid, tightest spreads
Spread width       $5.00      $1 - $10     Wider = more premium, more risk
Delta (short)      ~15        10 - 25      Lower delta = further OTM, safer
DTE                7          5 - 7        Short duration, less gamma risk
Entry time         Open       Open/Close   Daily open price used
Exit               Expiry     Expiry/50%   Hold to expiry by default
Contracts          1          1 - 3        Based on bankroll
```

---

## Known Limitations

### Data Quality
- **Daily aggregates only.** No intraday price action. Cannot model stop-losses or timed entries.
- **Delta is approximated.** Real delta requires IV surface (not available in Polygon day aggs). We rank strikes by percentile as a proxy, which breaks down in high-vol regimes.
- **No bid/ask spread data.** The open/close prices are aggregate midpoints. Real fills include slippage, typically $0.05-0.10 per leg on SPY.
- **Weekend/holiday gap risk.** Friday close to Monday open gaps are not modeled. A gap down Monday can move the spread significantly.

### Backtest Assumptions
- Entry at daily open price (may not be achievable in practice)
- No commissions ($0.65/contract is typical at TDA, so ~$1.30 per spread)
- No assignment/early exercise risk
- No earnings or event risk modeling
- Each day is an independent trade (in reality, positions overlap)

### Strategy Weaknesses
- **Directional bias:** Profits from flat-to-bullish. Loses in sustained downtrends.
- **Thin edge:** Avg win ≈ avg loss means the margin for error is small.
- **No volatility filter:** The strategy enters every day regardless of VIX or market regime.
- **Strike selection in high-vol:** The delta proxy picks strikes too close to ATM when IV expands, leading to more losses.

---

## Improvement Ideas

### Near-term (testable with current data)
1. **Volatility filter:** Skip trades when SPY is below its 20-day MA. This would have avoided much of the Oct/Dec drawdown.
2. **Wider spreads:** $10 wide instead of $5 gives more room for error and higher credit, but requires more capital per trade.
3. **Further OTM:** Target 10 delta instead of 15. Higher win rate, less premium per trade.
4. **Day-of-week filter:** Only enter Monday/Wednesday for Friday/Monday expiry. Weekend theta decay is "free."

### Medium-term (requires additional data)
1. **50% profit target:** Close at 50% of credit received. Locks in profits earlier, frees capital for new trades.
2. **Minute-level data:** Model realistic fill prices, intraday stop-outs, and optimal entry timing.
3. **Real Greeks:** Use Polygon's snapshot API for actual delta/theta/IV at entry.

### Long-term (strategy expansion)
1. **Iron condors:** Add bear call spreads above to profit from range-bound markets in both directions.
2. **QQQ:** Second underlier with different sector exposure.
3. **Dynamic sizing:** Increase contracts after wins, decrease after losses (anti-martingale).

---

## File Reference

```
options-backtest/
  strategy.py        Core logic (compute_pnl, classify_trade, select_spread)
  test_strategy.py   32 unit tests covering all edge cases
  backtest.py        Main backtest runner
  report.py          Monthly detailed report with open/close per leg
  trade_list.py      Compact trade list by month
  download.py        S3 data downloader
  ingest.py          Raw CSV -> filtered Parquet pipeline
  raw/               Downloaded daily aggregate files (all tickers)
  parquet/           Filtered data (SPY only, monthly files)
  backtest_results.csv   Trade-by-trade results
```

---

## Data Source

Polygon.io S3 Flatfiles via `files.massive.com`

Endpoint: `s3://flatfiles/us_options_opra/day_aggs_v1/`

Schema per row:
```
ticker, volume, open, close, high, low, window_start, transactions
```

Ticker format: `O:SPY260116P00580000` (O: prefix + OCC format: symbol + YYMMDD + C/P + 8-digit strike x1000)

---

*Strategy document v1.0 -- April 2026*
*Based on backtest of SPY 5-7 DTE $5-wide bull put credit spreads, Jul-Dec 2025*
