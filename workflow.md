# tos_options — Workflow

The end-to-end system for researching, backtesting, and trading
SPY credit spreads. Everything feeds into ThinkOrSwim for manual
execution.

---

## Architecture Overview

```
                        DATA LAYER
                        ==========
  Polygon S3 ──► options-backtest/parquet/   (flat files, 6 months)
  Schwab API ──► Postgres DB (desktop 5433)  (live greeks, OI, IV)

                      RESEARCH LAYER
                      ==============
  s3_test/            Data exploration, schema docs
  scripts/            Standalone backtest scripts
  algo/               Modular pipeline (9 modules)

                      EXECUTION LAYER
                      ===============
  spread_hunter/      Live scanner (Docker, 15-min scan cycle)
  discord/            Alerts via webhook
  schwab/             API client, models
  TOS                 Manual entry using OCC symbols from output
```


## Data Sources

| Source           | What                       | Where                          | Notes                         |
|------------------|----------------------------|--------------------------------|-------------------------------|
| Polygon flat files | OHLCV + basic options     | `options-backtest/parquet/`    | SPY only, Jul-Dec 2025        |
| Schwab scraper   | Full chain: greeks, OI, IV | Postgres on desktop:5433       | Live, every 15 min in Docker  |
| spy_daily.csv    | SPY daily bars + SMA(20)   | `data/spy_daily.csv`           | Extracted from options ATM    |

Polygon stock flat files are 403 on standard plan. SPY daily prices
are estimated from ATM put strikes across DTEs — ~$1 granularity,
good enough for trend/DOW analysis.


## Backtest Scripts

### scripts/backtest_spreads.py
Single-config backtester. One spread type at a time with full trade
detail and OCC symbols.

```bash
# Baseline (hold to expiry)
python3 scripts/backtest_spreads.py --months 6

# With stop-loss + profit target
python3 scripts/backtest_spreads.py --months 6 --stop-loss 50 --profit-target 75

# Bear calls
python3 scripts/backtest_spreads.py --months 6 --bear-call

# Both sides, export to CSV
python3 scripts/backtest_spreads.py --months 6 --both --csv trades.csv

# Compare all exit strategies side-by-side
python3 scripts/backtest_spreads.py --months 6 --compare-exits

# Allow overlapping positions
python3 scripts/backtest_spreads.py --months 6 --overlap
```

Output: table of trades with entry/exit dates, strikes, credit, P&L,
OCC symbols. Summary stats (WR, PF, maxDD, avg hold).

### scripts/backtest_grid.py
Grid search across OTM x DTE x stop x target x DOW x trend.
Single-pass collection, in-memory splitting — ~10x faster than
naive per-combo scan.

```bash
# Default grid (min 10 trades)
python3 scripts/backtest_grid.py --csv grid.csv

# Require 20+ trades per combo
python3 scripts/backtest_grid.py --csv grid.csv --min-trades 20 --top 40

# Quick mode (fewer combos)
python3 scripts/backtest_grid.py --quick
```

Output: ranked table of combos by profit factor, CSV with all results.


## Algo Pipeline (algo/)

9-module composable pipeline. Toggle any module on/off for A/B testing.

```
  1. generators      Build raw bull put + bear call candidates
  2. trend_filter    SMA(20) direction → keep one side
  3. iv_rank_filter  Only sell when IV rank 30-95%
  4. earnings_filter Black out around earnings dates
  5. wall_detector   Detect OI/volume walls
  6. wall_proximity  Reject if short strike near wall
  7. scoring         Composite score (ROC, delta, theta, liquidity, distance)
  8. stop_loss       Tag with SL/target levels (50% SL, 75% target)
  9. risk_manager    Position size, circuit breakers, 1 position at a time
```

Config presets:
- `baseline_config()`    — raw signals, no filters
- `trend_only_config()`  — trend filter only
- `full_stack_config()`  — everything enabled

Run via:
```bash
python3 scripts/run_pipeline.py --config baseline|trend_only|full_stack
```


## Proven Strategy Parameters

Based on 6-month flat-file backtest (Jul-Dec 2025):

```
  Underlying:      SPY
  Spread type:     Bull put credit
  Strike width:    $5
  OTM distance:    ~1.5%
  DTE at entry:    7
  Stop-loss:       50% of max loss
  Profit target:   75% of credit
  Overlap:         No (one position at a time)
```

Results (27 trades):
```
  Win rate:        96% (26W 1L)
  Total P&L:       $9.69/share
  Profit factor:   4.31
  Max drawdown:    $2.93/share
  Avg hold:        4.0 days
```

Position sizing: 2% of $50K = $1,000 risk per trade.
At 2 contracts: ~$1,938 total P&L over 6 months.


## Overlap Decision

Tested overlapping positions (enter new trade before previous exits):

```
                    Trades  P&L      PF    MaxDD
  Non-overlap         27    $9.69   4.31   $2.93
  Overlap uncapped   125    $23.61  1.75   $13.61
  Overlap cap 3       80    $10.27  1.43   $10.38
```

Verdict: No overlap. Correlation risk kills the edge — when SPY dumps,
all positions get hit simultaneously. The 50% stop triggers on each
one independently, compounding losses. Non-overlap gives better PF
and manageable drawdown.


## Research Loop

The process for refining the strategy:

```
  1. Pick ONE question
     "Does stop-loss improve PF?"
     "Does DOW matter?"
     "Does trend filter help?"

  2. Backtest it
     Use backtest_spreads.py for single configs
     Use backtest_grid.py for parameter sweeps

  3. Study the losers
     Every losing trade has a story
     Look for patterns: same DOW? Same trend? Same IV regime?

  4. Form new hypothesis
     If pattern found → add module or tweak config
     If no pattern → move on, don't overfit

  5. Repeat
     Only change one variable at a time
     Always compare to baseline (no filters)
```

Completed research:
- [x] Hold-to-expiry baseline
- [x] Stop-loss comparison (50% SL is the big win: PF 3.1 → 4.8)
- [x] Profit target (75% captures gains, reduces hold time)
- [x] Overlap analysis (no benefit, more risk)
- [x] Grid search (OTM x DTE x stop x target x DOW x trend)
- [x] Day-of-week analysis (no meaningful edge)
- [x] Trend filter (inconclusive, only 128 days of data)

Still to research:
- [ ] Delta-based entry (need Postgres greeks)
- [ ] IV rank gate (need proper IV history)
- [ ] OI wall proximity (need Postgres OI data)
- [ ] Multi-ticker (QQQ, IWM — uncorrelated underliers)


## Infrastructure

```
  Laptop (Mac)
    - Runs scripts locally
    - Python 3.12
    - Tailscale: 100.94.211.110

  Desktop (Windows)
    - Docker: Postgres 16 (port 5433) + scraper
    - Tailscale: 100.82.57.80
    - DB migration done, Mac .env points to desktop over Tailscale
    - File share: \\100.94.211.110\

  Docker (on desktop)
    - Postgres 16 Alpine
    - Schwab scraper (every 15 min)
    - spread_hunter live scanner
```

Gotcha: `docker compose exec -T <service> python -c "..."` gets blocked
by security tool. Use `docker compose logs` or `docker compose exec -T db psql`.


## File Map

```
tos_options/
├── algo/                   Modular backtest pipeline (9 modules)
│   ├── config.py           All knobs + presets
│   ├── pipeline.py         Ties modules together
│   ├── types.py            Shared dataclasses
│   ├── generators.py       Module 1: signal generation
│   ├── trend_filter.py     Module 2: SMA direction
│   ├── iv_rank_filter.py   Module 3: IV rank gate
│   ├── earnings_filter.py  Module 4: earnings blackout
│   ├── wall_detector.py    Module 5: OI wall detection
│   ├── wall_proximity.py   Module 6: wall proximity filter
│   ├── scoring.py          Module 7: composite scoring
│   ├── stop_loss.py        Module 8: stop-loss/target tagging
│   ├── risk_manager.py     Module 9: position sizing + circuit breakers
│   └── README.md           Module reference
│
├── scripts/
│   ├── backtest_spreads.py Single-config backtester
│   ├── backtest_grid.py    Grid search backtester
│   ├── run_pipeline.py     Algo pipeline runner
│   ├── live_scanner.py     Live spread scanner
│   └── ...                 Other utilities
│
├── spread_hunter/           Live scanner (Docker, 15-min cycle)
├── schwab/                  API client
├── gex/                     GEX calculations + DB storage
├── discord/                 Webhook alerts
├── s3_test/                 Data exploration
├── options-backtest/        Parquet flat files
├── data/                    spy_daily.csv + derived data
└── tests/                   Test suite
```
