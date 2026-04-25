# Changelog

## 2026-04-14 — Options Chain Strategy Catalog

### Completed
- Analyzed SCHEMA.md and mapped all available data: per-contract fields (greeks, IV, OI, volume), 3 aggregate tables (by_strike, by_expiry, by_bucket), and existing infra (regime classifier, GEX calculations, Strategy/Signal base classes)
- Produced 3 strategy research files covering 25 concrete strategies across 3 dimensions:
  - **Exposure & Flow** (8 strategies): GEX Magnet, Gamma Flip Breakout, DEX Imbalance, VEX/TEX Harvesting, OI Wall S/R, PCR Extremes, Volume Spike Detection, GEX Regime Trading framework
  - **Volatility & Greeks** (8 strategies): IV Term Structure Calendars, Skew Trading, IV Rank Mean Reversion, RV vs IV Arbitrage, Theta Harvesting, Vega-Weighted Straddles, IV Surface Anomaly Detection, Vol Compression/Expansion
  - **0DTE & Time-Series** (9 strategies): 0DTE Straddle Selling, Iron Butterfly, Gamma Scalping, Expiration Pinning/Max Pain, Intraday GEX Migration, OI Change Detection, IV Crush Calendar, Historical GEX Patterns, Snapshot Delta Rate-of-Change

### Artifacts
- `outputs/.research/options-chain-strategies-research-exposure.md` — GEX/DEX/OI wall/PCR strategies
- `outputs/.research/options-chain-strategies-research-vol.md` — IV surface/term structure/greeks strategies
- `outputs/.research/options-chain-strategies-research-0dte.md` — 0DTE intraday + multi-snapshot time-series strategies
- `outputs/.plans/options-chain-strategies.md` — research plan

### Key Findings
- `theoreticalOptionValue` vs `mark` divergence is a unique Schwab-specific edge for mispricing detection (not available from most providers)
- GEX Regime Trading is the master framework — all other strategies should be conditioned on the existing regime classifier
- Multi-snapshot strategies (OI change, GEX migration, snapshot deltas) require accumulated historical data but are high-value
- Every strategy mapped to exact schema fields and existing infrastructure (regime classifier, Strategy/Signal base classes, z0dte modules)

### Next Steps
- [ ] Implement GEX Regime Trading framework (Strategy orchestrator that activates strategies per regime)
- [ ] Add max pain signal to z0dte/signals/
- [ ] Build OI diff function for day-over-day positioning detection
- [ ] Create IV term structure monitor signal
- [ ] Add snapshot delta (rate-of-change) as a meta-signal mixin

## 2026-04-10 — Databento $125 Credit Optimization Strategy

### Completed
- Researched Databento Historical API, pricing model, OPRA dataset schemas, and credit mechanics
- Identified schema hierarchy from cheapest (OHLCV-1d, definitions, statistics) to most expensive (CMBP-1 full tick)
- Built concrete $125 budget allocation across 7 data categories
- Created cost explorer script (`databento_cost_explorer.py`) to price requests before executing
- Documented 6 cost-saving tactics: `limit` parameter, narrow time windows, parent symbology, batch downloads, `get_record_count()`, local DBN storage

### Key Finding
- OPRA CMBP-1 is **terabytes/day** — would blow $125 instantly
- OHLCV-1d + CBBO-1m + targeted trades gives best coverage for backtesting
- Batch download (vs streaming) allows free re-downloads for 30 days
- `metadata.get_cost()` and `metadata.get_billable_size()` are FREE — always use before downloading

### Artifacts
- `outputs/databento-125-credit-strategy.md` — full strategy guide with code examples

### Next Steps
- [ ] Run cost explorer script with actual API key to get precise per-schema costs
- [ ] Download definitions first to identify target 0DTE/SPXW contracts
- [ ] Pull daily OHLCV for broad screening, then surgical intraday pulls

## 2026-04-10 — SPX 0DTE Chain Capture Research

### Completed
- Deep research on SPX 0DTE/1DTE options chain capture via Polygon.io (Massive API)
- Confirmed Polygon endpoint: `GET /v3/snapshot/options/I:SPX` supports full chain with greeks, IV, OI, quotes
- Identified 7 concrete strategies rated by 15-minute delay tolerance
- Documented SPX vs SPY structural differences
- Mapped required codebase changes in `z0dte/` module (schema, API source, ingestion)

### Artifacts
- `outputs/spx-0dte-chain-capture-strategies.md` — main research brief (18 sources cited)
- `outputs/spx-0dte-chain-capture-strategies.provenance.md` — provenance record
- `outputs/.plans/spx-0dte-chain-capture-strategies.md` — research plan

### Next Steps
- [ ] Verify exact Polygon plan tier for options data
- [ ] Update `massive_api.py` to use correct chain snapshot endpoint
- [ ] Add SPX support to normalizer and schema
- [ ] Implement max pain signal (`signal_max_pain` table)
- [ ] Backtest delay-tolerance ratings against actual 15-min delayed data
