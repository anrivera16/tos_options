# Options Strategies for the US Stock Market

A brief overview of options strategies drawn from academic research (arXiv) and standard practitioner literature.

---

## 1. Covered Call

**Type:** Income generation
**Outlook:** Neutral to mildly bullish

You own 100 shares of the underlying stock and sell (write) one call option against them. You collect the premium upfront. If the stock stays below the strike at expiration, you keep the premium and your shares. If it rises above the strike, your shares get called away at the strike price.

- **Max profit:** Premium received + (strike - stock purchase price)
- **Max loss:** Stock purchase price - premium received (if stock goes to zero)
- **Risk profile:** Reduces cost basis, caps upside

---

## 2. Protective Put

**Type:** Hedging / Insurance
**Outlook:** Bullish but cautious

You own 100 shares and buy one put option as insurance. If the stock drops, the put gains value, offsetting losses. Think of it as a deductible insurance policy on your portfolio.

- **Max profit:** Unlimited (stock appreciation minus premium paid)
- **Max loss:** (Stock purchase price - strike price) + premium paid
- **Risk profile:** Limits downside while preserving upside

---

## 3. Iron Condor

**Type:** Premium collection / Range-bound
**Outlook:** Neutral

Sell one out-of-the-money put, buy one further OTM put (lower wing). Sell one OTM call, buy one further OTM call (upper wing). You profit when the stock stays within a range between the two short strikes. All four legs expire worthless = you keep all premium.

Research highlight: Huang, Sun & Yang (2025) [arXiv:2501.12397] formulate Iron Condor optimization as a stochastic optimal control problem, analyzing the transient value process of the portfolio rather than just expiration outcomes.

- **Max profit:** Net premium received
- **Max loss:** Difference between strike widths minus net premium
- **Risk profile:** Defined risk, high probability of small profit

---

## 4. Long Straddle

**Type:** Volatility play
**Outlook:** Big move expected (direction unknown)

Buy one ATM call and one ATM put at the same strike and expiration. You profit if the stock moves sharply in either direction, enough to exceed the total cost of both premiums.

- **Max profit:** Unlimited (upside) or (strike - premium) on downside
- **Max loss:** Total premium paid for both options
- **Risk profile:** Expensive to enter; needs a big move to be profitable

---

## 5. Strangle (Delta-Symmetric)

**Type:** Volatility play (cheaper than straddle)
**Outlook:** Big move expected (direction unknown)

Buy an OTM call and an OTM put at different strikes (same expiration). Cheaper than a straddle but requires a larger move to profit.

Research highlight: The delta-symmetric strangle is studied under the Black-Scholes framework [arXiv:2003.03876], providing a measure of relative value for this popular strategy used to mitigate volatility risk.

- **Max profit:** Unlimited upside; substantial downside
- **Max loss:** Total premium paid
- **Risk profile:** Lower cost than straddle, but needs even more volatility

---

## 6. Vertical (Bull/Bear) Spread

**Type:** Directional with defined risk
**Outlook:** Bullish (call spread) or Bearish (put spread)

**Bull Call Spread:** Buy a lower-strike call, sell a higher-strike call (same expiration). You profit if the stock rises, but gains are capped at the upper strike.

**Bear Put Spread:** Buy a higher-strike put, sell a lower-strike put. You profit if the stock falls, but gains are capped at the lower strike.

- **Max profit:** Difference between strikes minus net debit
- **Max loss:** Net premium paid
- **Risk profile:** Cheaper than buying a single call/put, but caps your gain

---

## 7. Wheel Strategy

**Type:** Income generation (systematic)
**Outlook:** Neutral to bullish

1. Sell cash-secured puts on a stock you want to own. Collect premium.
2. If assigned, you now own 100 shares at a discount.
3. Sell covered calls against those shares. Collect more premium.
4. If shares get called away, start over at step 1.

This is a cyclical strategy popular among retail traders for generating consistent income on quality stocks.

- **Max profit:** Premium from puts + premium from calls + capital appreciation
- **Max loss:** Stock purchase price (if assigned and stock goes to zero) minus premiums collected
- **Risk profile:** Disciplined, repeatable income; requires patience and capital

---

## 8. High-Frequency Options Trading with Portfolio Optimization

**Type:** Quantitative / Systematic
**Outlook:** Varies

Research highlight: Bhatia (2024) [arXiv:2408.08866] explores high-frequency options trading on SPY (S&P 500 ETF) enhanced by portfolio optimization. The approach uses advanced statistical techniques to generate consistent positive returns compared to simple long or short option positions.

- **Key idea:** Use intraday signals and optimization to dynamically manage option positions
- **Risk profile:** Requires sophisticated infrastructure and low-latency execution

---

## 9. Delta-Neutral Hedging

**Type:** Risk management / Volatility trading
**Outlook:** Focused on volatility, not direction

Construct a portfolio where the net delta is zero -- gains/losses from the underlying are offset by the options position. You profit from changes in volatility or time decay (theta) rather than directional moves.

Research highlight: Fractional delta hedging with transaction costs is studied in [arXiv:1702.00037], providing pricing formulas for European currency options under discrete-time rebalancing.

- **Max profit:** Depends on volatility spread and gamma/theta balance
- **Max loss:** Transaction costs, adverse gamma, and model risk
- **Risk profile:** Complex; requires continuous monitoring and rebalancing

---

## 10. Semi-Static Hedging with American Options

**Type:** Advanced hedging framework
**Outlook:** Risk management

Research highlight: Bayraktar & Zhou [arXiv:1502.06681, arXiv:1604.04608] develop frameworks for hedging exotic payoffs using a combination of dynamic stock trading and static option positions. Since most traded options on US stocks are American-style, these results are directly applicable to real markets.

- **Key idea:** Use liquid American options as static hedges alongside dynamic stock positions
- **Risk profile:** Model-dependent; reduces hedging cost versus purely dynamic approaches

---

## Key References from arXiv

| ID | Title | Year |
|----|-------|------|
| 2501.12397 | Stochastic Optimal Control of Iron Condor Portfolios | 2025 |
| 2408.08866 | High-Frequency Options Trading with Portfolio Optimization | 2024 |
| 2003.03876 | Relative Value of Delta-Symmetric Strangle | 2020 |
| 1912.04492 | 151 Trading Strategies (book, covers options extensively) | 2019 |
| 1702.00037 | Fractional Delta Hedging with Transaction Costs | 2017 |
| 1604.04608 | Super-Hedging American Options with Semi-Static Strategies | 2016 |
| 1502.06681 | Arbitrage, Hedging & Utility with Semi-Static Strategies | 2015 |

---

## Quick Comparison

| Strategy | Direction | Risk | Income? | Complexity |
|----------|-----------|------|---------|------------|
| Covered Call | Neutral/Bull | Defined | Yes | Low |
| Protective Put | Bull | Defined | No | Low |
| Iron Condor | Neutral | Defined | Yes | Medium |
| Long Straddle | Either | Defined | No | Medium |
| Strangle | Either | Defined | No | Medium |
| Vertical Spread | Bull or Bear | Defined | Possible | Low |
| Wheel | Neutral/Bull | Stock risk | Yes | Medium |
| HF Options | Varies | Variable | Yes | High |
| Delta-Neutral | Neutral | Variable | Yes | High |
| Semi-Static Hedge | Hedge | Defined | No | High |

---

*Research sourced from arXiv (export.arxiv.org) and Semantic Scholar APIs. This document is for educational purposes only -- not financial advice.*
docker compose up -d db scraper-watch spread-hunter
