# algo/ — Modular Credit Spread Pipeline

Composable pipeline for backtesting SPY credit spread strategies. Each
decision layer is an independent module — toggle any combination on/off
to measure each component's contribution to the edge.


## Strategy

Sell bull put credit spreads and bear call credit spreads on SPY:

| Parameter       | Value              |
|-----------------|--------------------|
| Underlying      | SPY                |
| Strike width    | $5                 |
| Short leg delta | 0.10-0.20          |
| DTE at entry    | 5-9 days           |
| IV rank range   | 30-95%             |
| Risk per trade  | 2-3% of $50K       |

Design spec: `s3_test/algo_analysis.md`


## File Structure

```
algo/
│
├── __init__.py            Package marker
│
├── types.py               Shared dataclasses used across all modules
│                          ┌─────────────────┬──────────────────────────────────┐
│                          │ CandidateSpread  │ One spread candidate flowing      │
│                          │                  │ through the pipeline. Carries     │
│                          │                  │ legs, greeks, pricing, and        │
│                          │                  │ pipeline state (pass/reject/tags) │
│                          ├─────────────────┼──────────────────────────────────┤
│                          │ OIWall           │ A support/resistance level from   │
│                          │                  │ OI/volume concentration           │
│                          ├─────────────────┼──────────────────────────────────┤
│                          │ PipelineResult   │ Output of one pipeline run:       │
│                          │                  │ candidate counts at each stage,   │
│                          │                  │ ranked + rejected lists           │
│                          ├─────────────────┼──────────────────────────────────┤
│                          │ BacktestResult   │ Full backtest summary: win rate,  │
│                          │                  │ P&L, drawdown, profit factor,     │
│                          │                  │ rejections by module              │
│                          └─────────────────┴──────────────────────────────────┘
│
├── config.py              All knobs in one place
│                          ┌─────────────────┬──────────────────────────────────┐
│                          │ GeneratorConfig  │ delta range, DTE range, strike   │
│                          │                  │ width, min OI/volume, min ROC    │
│                          ├─────────────────┼──────────────────────────────────┤
│                          │ TrendConfig      │ SMA period, slope lookback,      │
│                          │                  │ neutral action                    │
│                          ├─────────────────┼──────────────────────────────────┤
│                          │ IVRankConfig     │ IV rank min/max (default 30-95%)  │
│                          ├─────────────────┼──────────────────────────────────┤
│                          │ EarningsConfig   │ blackout days before/after        │
│                          ├─────────────────┼──────────────────────────────────┤
│                          │ WallConfig       │ top N walls, min OI, weights     │
│                          ├─────────────────┼──────────────────────────────────┤
│                          │ ProximityConfig  │ proximity threshold %, direction │
│                          ├─────────────────┼──────────────────────────────────┤
│                          │ ScoringConfig    │ weights for each scoring factor  │
│                          ├─────────────────┼──────────────────────────────────┤
│                          │ RiskConfig       │ bankroll, risk %, position limit  │
│                          ├─────────────────┼──────────────────────────────────┤
│                          │ PipelineConfig   │ Master config composing all of    │
│                          │                  │ the above + name, db_url          │
│                          │                  │ .with_module() toggles modules    │
│                          │                  │ .describe() prints active/inactive│
│                          └─────────────────┴──────────────────────────────────┘
│                          Also includes preset configs:
│                          - baseline_config()    raw signals only, no filters
│                          - trend_only_config()  trend filter only
│                          - full_stack_config()  everything enabled
│
├── generators.py          MODULE 1 — Signal Generator
│                          Takes raw DB rows (option chain data) and builds
│                          candidate spreads. No filtering here — just
│                          construction.
│
│                          Input:  DB rows with strike, put_call, dte, greeks,
│                                  bid/ask/mark, OI, volume
│                          Output: list[CandidateSpread]
│
│                          Builds:
│                          - Bull put credits: sell higher put, buy lower put
│                          - Bear call credits: sell lower call, buy higher call
│
│                          Pre-filters applied at generation:
│                          - DTE in 5-9 range
│                          - Short leg delta in 0.10-0.20
│                          - Min OI and volume per leg
│                          - Min ROC%
│
├── trend_filter.py        MODULE 2 — Trend Filter
│                          Determines market direction from SMA(20) on daily
│                          closes. Bullish = puts only, bearish = calls only.
│
│                          Input:  candidates + price_history (daily closes)
│                          Output: filtered candidates
│
│                          Logic:
│                          - price > SMA(20) AND slope positive → BULLISH
│                          - price < SMA(20) AND slope negative → BEARISH
│                          - otherwise → NEUTRAL (configurable keep/none)
│
├── iv_rank_filter.py      MODULE 3 — IV Rank Gate
│                          Only sell premium when IV rank is in the sweet spot.
│                          Passes through if < 5 historical IV points.
│
│                          Input:  candidates + current_iv + historical_ivs
│                          Output: filtered candidates
│
│                          IV rank = percentile of current IV in recent range
│                          Default: reject if < 30% (cheap) or > 95% (extreme)
│
├── earnings_filter.py     MODULE 4 — Earnings Filter
│                          Black out trading around earnings for major SPY
│                          holdings (AAPL, MSFT, AMZN, etc).
│
│                          Input:  candidates (uses entry_date + expiration_date)
│                          Output: filtered candidates
│
│                          Static calendar in DEFAULT_EARNINGS_DATES dict.
│                          Update quarterly. Blackout window is configurable
│                          (default 1 day before/after).
│
├── wall_detector.py       MODULE 5 — OI/Volume Wall Detector
│                          Identifies support/resistance from OI concentrations.
│
│                          Input:  per-strike OI/volume aggregated from chain rows
│                          Output: list[OIWall] (top N by combined score)
│
│                          Scoring: 70% OI weight + 30% volume weight, normalized.
│                          Wall type: put-heavy strikes = support, call-heavy = resistance.
│
├── wall_proximity.py      MODULE 6 — Wall Proximity Filter
│                          Rejects spreads whose short strike is too close to a wall.
│
│                          Input:  candidates + walls from Module 5
│                          Output: filtered candidates
│
│                          Logic:
│                          - Bull puts → check support walls below short strike
│                          - Bear calls → check resistance walls above short strike
│                          - Reject if distance < threshold (default 1% of price)
│
├── scoring.py             MODULE 7 — Scoring & Ranking
│                          Composite score from 5 factors, each normalized 0-1.
│
│                          Factors (default weights):
│                          - ROC%              35%   (higher = better)
│                          - Delta center      20%   (closer to 0.15 ideal)
│                          - Theta efficiency  20%   (|theta|/daily_credit)
│                          - Liquidity         15%   (log-scaled OI)
│                          - Distance OTM     10%   (safety margin)
│
│                          Input:  passed candidates
│                          Output: same candidates sorted by composite_score desc
│
├── risk_manager.py        MODULE 8 — Risk Manager
│                          Position sizing, circuit breakers, portfolio tracking.
│
│                          RiskManager class tracks:
│                          - Open positions (max 4 concurrent)
│                          - Daily P&L ($500 limit)
│                          - Weekly P&L ($1,000 limit)
│                          - Position size (2-3% of bankroll per trade)
│
│                          Input:  ranked candidates
│                          Output: approved trades (takes top 1 per cycle)
│
└── pipeline.py            BacktestPipeline — ties everything together
                           Runs the full pipeline over historical snapshots.
                           Each snapshot goes through all modules in order.

                           Usage:
                               from algo.pipeline import BacktestPipeline
                               from algo.config import full_stack_config

                               pipeline = BacktestPipeline(full_stack_config())
                               results = pipeline.run_on_snapshots(snapshots)
                               results.compute_summary()

                           Each snapshot dict needs:
                               rows: list[dict]        # option chain data
                               underlying_price: float  # SPY price
                               timestamp: str           # ISO timestamp
                               price_history: list      # daily closes (for trend)
                               historical_ivs: list     # IV readings (for rank)
                               current_iv: float        # current ATM IV
```

## Pipeline Flow

```
DB rows (option chain) + SPY price + price history + IV history
         │
         ▼
  ┌──────────────────┐
  │ 1. generators.py │  Build raw bull put + bear call candidates
  │    (always on)   │  Filter: DTE, delta, liquidity, min ROC
  └────────┬─────────┘
           │  raw candidates
           ▼
  ┌──────────────────┐
  │ 2. trend_filter  │  SMA(20) direction → keep one side only
  │    (toggleable)  │
  └────────┬─────────┘
           │  direction-filtered
           ▼
  ┌──────────────────┐
  │ 3. iv_rank_filter│  Only sell when IV rank 30-95%
  │    (toggleable)  │
  └────────┬─────────┘
           │  IV-filtered
           ▼
  ┌──────────────────┐
  │ 4. earnings_filter│ Black out around earnings dates
  │    (toggleable)  │
  └────────┬─────────┘
           │  earnings-filtered
           ▼
  ┌──────────────────┐
  │ 5. wall_detector │  Detect OI walls (shared across candidates)
  │    (toggleable)  │
  └────────┬─────────┘
           │  walls list
           ▼
  ┌──────────────────┐
  │ 6. wall_proximity│ Reject if short strike near wall
  │    (toggleable)  │
  └────────┬─────────┘
           │  wall-filtered
           ▼
  ┌──────────────────┐
  │ 7. scoring.py    │  Composite score + rank by score
  │    (toggleable)  │
  └────────┬─────────┘
           │  ranked candidates
           ▼
  ┌──────────────────┐
  │ 8. risk_manager  │  Position size, circuit breakers
  │    (toggleable)  │  Takes top 1 approved trade per cycle
  └────────┬─────────┘
           │
           ▼
      Trade taken (or no trade this cycle)
```

## Backtest Matrix

Toggle modules on/off to measure each one's contribution:

| Test              | Config                    | Question                            |
|-------------------|---------------------------|-------------------------------------|
| Baseline          | baseline_config()         | Raw signals. Win rate? ROC?         |
| Trend only        | trend_only_config()       | Does trend improve win rate?        |
| IV Rank only      | custom: iv_rank ON only   | Does IV rank filter help?           |
| Walls only        | custom: walls+proximity   | Do OI walls matter?                 |
| Full stack        | full_stack_config()       | Everything on. Compare to baseline. |


## Relationship to Existing Code

```
tos_options/
├── algo/                ← NEW (this package)
│                         Research + backtesting only
│                         Independent of live scanner
│
├── spread_hunter/       ← EXISTING (live scanner)
│                         15-min scans, Discord alerts
│                         Unchanged, still runs in Docker
│                         Can import from algo/ later if desired
│
├── schwab/              ← SHARED (API client, models)
├── gex/                 ← SHARED (DB access, storage)
├── scripts/             ← EXISTING entry points
└── s3_test/             ← Data exploration + algo_analysis.md
```

The algo package reuses:
- DB connection pattern from `gex/storage.py`
- Option chain row format from Schwab scraper
- Leg data structure concepts from `spread_hunter/spread_types.py`

But it does NOT import from spread_hunter — it's fully self-contained
so you can modify it without breaking the live scanner.
