# Volatility Surface Trading Examples - Detailed Walkthrough

## Using 1-Minute Options Chain Data to Find Edges

This document walks through **4 concrete trades** using realistic market data from April 8, 2026.

---

## Trade 1: Calendar Spread Arbitrage

### Entry Setup (10:00 AM)

You're monitoring the SPX options chain every minute. You notice something odd in the term structure:

```
SPX = 5432.10

CALL PRICES (5430 strike):
  30 DTE (May 8):  $119.28   IV = 17.30%
  60 DTE (June 8): $174.00   IV = 17.50%

OBSERVATION: 
  30 DTE IV is HIGHER than 60 DTE IV
  This is backwards (normally far-term vol > near-term)
  The market is saying "2020 will be more volatile than 2021" - unlikely
```

### The Trade

**Action:** Sell the expensive 30 DTE, buy the cheap 60 DTE

```
SELL 1x May 8 5430 Call @ $119.28  (collect premium)
BUY  1x June 8 5430 Call @ $174.00 (pay premium)
_________________________________________
NET COST: $174.00 - $119.28 = $54.72 (you pay to put on the trade)
```

### Position Greeks

```
Position: Long June, Short May (calendar spread)

Delta:      ~0.00 (both calls have similar delta, so mostly cancels)
Theta:      +$0.51/day (near-term decays faster than far-term = positive for you)
Vega:       +2.52 (if vol WIDENS [30-60 DTE spread increases], you win)
Gamma:      -0.0004 (small negative)
```

### Why This Works

**Thesis:** The term structure violation will correct. You'll profit when:
1. 30 DTE IV falls (moves toward far-term IV)
2. 60 DTE IV rises (moves away from near-term IV)
3. Theta decay works in your favor (near-term decays faster)

### What Happens (Next 24 Hours)

**Time: April 8, 14:00 (4 hours later)**
```
SPX = 5433.50 (up $1.40)
May 5430 Call: $118.50 (was $119.28) → you're up $0.78
June 5430 Call: $173.80 (was $174.00) → you're down $0.20
Net P&L: $0.78 - $0.20 = +$0.58 ✓ PROFIT

Delta: +0.015 (nearly flat, as expected)
Theta: +0.51/day (time decay still helping you)
```

**Time: April 9, 10:00 (24 hours later)**
```
SPX = 5431.00 (down $1.10)

IV Surface has normalized:
  May 8 5430 Call:  IV = 16.80%   Price = $117.50
  June 8 5430 Call: IV = 17.20%   Price = $173.00

You're up:
  On the short May:  $119.28 - $117.50 = +$1.78
  On the long June:  $173.00 - $174.00 = -$1.00
  Total P&L: +$0.78

Return: $0.78 / $54.72 = +1.4% in 24 hours
Annualized: +510% (if you could repeat this daily)
```

### Key Insight

With **1-minute data**, you spotted this mispricing within minutes of it appearing. Most traders won't notice until it's corrected (hours or days later). Your edge is **real-time surface monitoring**.

---

## Trade 2: Butterfly Volatility Arbitrage

### Entry Setup (10:00 AM)

You're watching the volatility smile (how IV changes across strikes). You notice it's unusually curved:

```
SPX = 5432.10

30 DTE CALL PRICES:
Strike | IV      | Call Price
-------|---------|----------
5430   | 17.30%  | $119.28
5460   | 17.32%  | $104.24  (only +2 bps higher IV for +30 strike)
5490   | 17.35%  | $90.52   (+5 bps total)

OBSERVATION:
The smile is TOO FLAT. In a normal market, OTM calls should have
incrementally higher IV as you go further OTM. But the curve isn't
smooth - it's accelerating. This creates a butterfly opportunity.
```

### The Trade (1:2:1 Ratio)

```
BUY  1x 5430 Call @ $119.28
SELL 2x 5460 Call @ $104.24 each = $208.48
SELL 1x 5490 Call @ $90.52

NET CREDIT: -$119.28 + $208.48 + $90.52 = +$179.72
(You get paid $179.72 to put on the trade! This is rare and great.)
```

### Position Greeks

```
Delta:  -0.91 (slightly short, can hedge with long spot)
Gamma:  -0.003 (negative: you lose if spot moves far in either direction)
Theta:  +4.17/day (huge positive: time decay works for you)
Vega:   -12.42 (you're short vega: profit if smile FLATTENS)
```

### Why This Works

**Thesis:** The smile curvature is too steep. When it normalizes (flattens), OTM calls become cheaper relative to ATM, and you profit.

This is a **vega-negative, gamma-negative, theta-positive** trade: you win if vol contracts or the smile flattens, but you lose if spot moves dramatically or smile steepens.

### What Happens (Next 6 Hours)

**Time: April 8, 16:00**
```
SPX = 5433.00 (up $0.90)

IV Smile HAS FLATTENED:
Strike | New IV  | New Price | Change
-------|---------|-----------|--------
5430   | 17.15%  | $118.10   | -$1.18
5460   | 17.10%  | $103.40   | +$0.84 (down, as expected)
5490   | 17.08%  | $89.80    | +$0.72 (down!)

Your P&L:
  Long 5430: -$1.18 (lost on long)
  Short 2x 5460: +$1.68 (gained on shorts)
  Short 5490: +$0.72 (gained on short)
  Total: -$1.18 + $1.68 + $0.72 = +$1.22 ✓ PROFIT

Return on initial credit: $1.22 / $179.72 = +0.68% in 6 hours
Annualized: +27% (if you repeat daily)
```

### The Risk

If the smile **steepens** (OTM calls get MORE expensive), you lose:

```
Alternate Scenario: IV Smile STEEPENS
Strike | New IV  | New Price
-------|---------|----------
5430   | 17.50%  | $121.00
5460   | 17.80%  | $106.50
5490   | 18.20%  | $92.00

Your P&L:
  Long 5430: -$1.72
  Short 2x 5460: -$4.52
  Short 5490: -$2.96
  Total: -$9.20 LOSS

But you still have the theta from 4 hours, which offsets some loss.
```

---

## Trade 3: Skew-Based Long Straddle

### Entry Setup (10:00 AM)

News alert: There's unusual activity in 0DTE put buying. The skew is widening.

```
30 DTE OPTIONS AT 5430 STRIKE:
  Call IV: 17.30%
  Put IV:  18.10%   (80 bps HIGHER than call)

SKEW = Put IV - Call IV = 80 bps

Normal skew is 30-50 bps. 80 bps signals JUMP RISK.
Traders are pricing in crash protection.
```

### The Trade

You believe: If skew is this wide, realized vol will expand (the market will be volatile).

```
BUY 1x 5430 Call  @ $119.28
BUY 1x 5430 Put   @ $97.03
__________________________
TOTAL COST: $216.31 (you pay for the straddle)
```

### Position Greeks

```
Delta:  +0.086 (slightly long, but nearly flat for an ATM straddle)
Gamma:  +0.0029 (you profit from large spot moves in either direction)
Theta:  -3.59/day (theta decay works against you; this is the cost)
Vega:   +12.35 (you profit if IV increases - that's your bet)
```

### Why This Works

**Thesis:** Skew expansion signals volatility will increase. If realized vol > implied vol over the next few days, you profit despite theta decay.

This is the **classic volatility bet**: you're long vega (betting vol increases), paying theta decay as the cost.

### What Happens (Next 5 Hours)

**Scenario A: Vol Expands (You Win)**

```
Time: April 8, 15:00

Bad news hits (Fed announcement). SPX drops to 5410. Vol SURGES.

New market:
  ATM IV: 21.5% (was 17.3%, up 420 bps!)
  5430 Call: Now worth $45.00 (was $119.28)
  5430 Put:  Now worth $95.00 (was $97.03)

New straddle value: $45 + $95 = $140

Your P&L: $140 - $216 = -$76... WAIT, you're DOWN?!

What happened: 
- The call lost value because spot moved DOWN (bad for long call)
- The put gained value but not enough to offset call loss
- THETA DECAY worked against you: $3.59/day * 5hrs = -$0.75

BUT THIS IS WRONG! Let me recalculate...

Actually, when spot moves to 5410:
  5430 Call is now OTM by $20 → value is intrinsic (≈$0) + time value (≈$5)
  5430 Put is now ITM by $20 → value is intrinsic ($20) + time value (≈$10)
  
Straddle = $5 + $30 = $35 → P&L = $35 - $216 = -$181 LOSS

This shows: Straddle buying is HARD. You need BOTH vol expansion AND
spot to stay near strike. If spot moves away, put gain ≠ call loss.
```

**Scenario B: Vol Expands, Spot Stays (You Win HUGE)**

```
Time: April 8, 15:00

Vol spikes but spot only moves to 5425 (down just $7).

New market:
  ATM IV: 21.5%
  5430 Call: worth $35.00
  5430 Put:  worth $38.00 (no longer ATM, but less OTM than call)
  
Straddle value: $35 + $38 = $73

P&L: $73 - $216 = -$143 LOSS

Still negative! Why? Theta decay is KILLING you. The straddle has
lost $3.59/day * 5 hours = $0.75 to theta alone. Plus the spot
moved away from the strike slightly.

For a straddle to win, you need MASSIVE vol expansion. Your break-even
is roughly when realized vol doubles while spot stays flat.
```

### Key Insight

**Straddle buying is hard because:**
1. You pay theta every day
2. Spot is binary: if it moves away, you lose even if vol expands
3. You need gamma profit (spot volatility) + vega profit (IV expansion) to overcome theta

**The winners:**
- Straddles work when vol EXPLODES (>50% increase)
- Or when spot stays pinned and vol expands moderately
- In crises (March 2020, Volmageddon) they can profit 50%+

---

## Trade 4: 0DTE Theta Harvest

### Entry Setup (14:00 - 2 Hours to Close)

The final 2 hours of trading are different. Theta acceleration becomes extreme.

```
0DTE SPX STRADDLE (expires 16:00 today):
Strike 5430:
  0DTE Call: $19.66   (almost all time value, no intrinsic since OTM)
  0DTE Put:  $16.88   (same, OTM)
  
TOTAL: $36.54

30 DTE STRADDLE (for comparison):
  30 DTE Call: $119.28
  30 DTE Put:  $97.03
  TOTAL: $216.31

The 0DTE straddle is 1/6 the cost of 30 DTE!
But expires in 2 hours. Theta acceleration is EXTREME.
```

### The Trade

You believe: Spot will stay near 5430 for the final 2 hours. You'll collect theta.

```
SELL 1x 0DTE 5430 Call @ $19.66
SELL 1x 0DTE 5430 Put  @ $16.88
__________________________
COLLECT: $36.54 (credit received immediately)
```

### Position Greeks

```
Delta:  -1.00 (VERY SHORT - highly leveraged bet on spot staying put)
Gamma:  +0.35 (EXTREMELY HIGH - tiny spot moves cause huge rebalancing)
Theta:  +$0.0175/min = $1.05/hour (absolutely massive!)
Vega:   +0.001 (basically zero - IV surface is irrelevant at 0DTE)
```

### The Mechanics

Each minute, the straddle loses value due to time decay:

```
14:00 - Entry
Straddle value: $36.54

14:15 (15 minutes later)
Straddle value: $36.54 - ($1.05/hour * 0.25 hours) = $36.54 - $0.26 = $36.28
Your P&L if you close: $36.54 - $36.28 = +$0.26 ✓ PROFIT (in 15 min!)

14:30 (30 minutes later)
Straddle value: $36.54 - $0.52 = $36.02
Your P&L: +$0.52 ✓

15:00 (60 minutes)
Straddle value: $36.54 - $1.05 = $35.49
Your P&L: +$1.05 ✓

15:45 (105 minutes)
Straddle value: $36.54 - $1.84 = $34.70
Your P&L: +$1.84 ✓

15:55 (115 minutes - 5 min to close)
Straddle value: $36.54 - $2.01 = $34.53
Your P&L: +$2.01 ✓

16:00 (at expiration)
Spot is at 5432 (near strike)
Straddle value: $0 (expired at-the-money)
YOUR FINAL P&L: +$36.54 ✓✓✓

PROFIT: $36.54 / $36.54 = 100% return in 2 hours!
```

### The Risk

```
14:30 (30 minutes in)
Spot SUDDENLY DROPS to 5410 (down $22)

NOW THINGS ARE DIFFERENT:
  0DTE 5430 Call: worthless ($0, OTM)
  0DTE 5430 Put:  ITM by $20 → worth ~$20 (intrinsic)
  
Straddle value: $0 + $20 = $20

Your P&L: $36.54 - $20 = +$16.54 PROFIT (you're still up!)

Why? Because puts have intrinsic value. The floor on your loss is the 
distance to the next strike. If you sold a 5430 straddle and spot
drops to 5400, your loss is $30 (the strike width).

Maximum loss on 5430 short straddle: $30 per contract
Profit potential: $36.54 (full credit)
Risk-reward: $30 at risk to make $36.54 → 122% return

This is why 0DTE is so risky: massive leverage. A 2% spot move can 
wipe out your profit or create huge losses.
```

### Key Insight

**0DTE theta harvesting is:**
- ✅ Highest hourly profit potential ($1-2/hour on $30-40 straddles)
- ✅ Profitable in calm markets (spot range-bound)
- ❌ Catastrophic if spot moves >3% (which it will sometimes)
- ❌ Requires active management (rebalancing every 15-30 min if spot moves)
- ❌ Leverage risk: $1 premium collected = up to $25 loss if spot moves

---

## Summary: Edge Potential with 1-Minute Data

| Strategy | Edge | Time Horizon | Return | Frequency | Risk |
|----------|------|--------------|--------|-----------|------|
| **Calendar Spread** | Term structure violations | 1-7 days | 1-5% | 5-10/week | Low (small, defined risk) |
| **Butterfly** | Smile curvature mispricings | 6-24 hours | 0.5-2% | 3-8/week | Medium (short gamma) |
| **Straddle** | Vol expansion prediction | 1-5 days | -20% to +50% | 5-10/week | High (theta decay vs vega) |
| **0DTE Theta** | Intraday time decay | Minutes to hours | 50-200% | 15-20/day | Very High (gamma leverage) |

---

## How to Build This

1. **Get 1-minute options chain data**
   - OptionMetrics, Cboe, or custom API scraper
   
2. **Calculate the volatility surface**
   - Fit IV smile across strikes and expirations
   - Track changes minute-by-minute

3. **Detect anomalies**
   - Calendar spread violations: |IV_near - IV_far| > threshold
   - Butterfly violations: Second derivative of smile curve
   - Skew widening: (Put IV - Call IV) spikes
   - 0DTE theta: Real-time Greeks on 0DTE options

4. **Execute multi-leg orders**
   - Use broker APIs to send simultaneous orders
   - Track position Greeks in real-time
   - Set exit rules (P&L target or time-based)

5. **Risk management**
   - Calendar spreads: Low capital, hold for days
   - Butterflies: Need capital for potential short gamma loss
   - Straddles: High vega risk; need vol forecast confidence
   - 0DTE: Must actively hedge gamma or limit size

---

## Code Files Included

- `volatility_surface_trader.py` - Full pricing and Greeks engine
- `detailed_backtest.py` - Scenario simulations
- CSV exports of backtest results for your own analysis

Run `python detailed_backtest.py` to generate backtest data.

