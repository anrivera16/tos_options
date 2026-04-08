# 0DTE Intraday Options Analytics Module

## Purpose

Track SPX/SPY options data every 15 minutes and compute four analytics signals that reveal dealer positioning, directional pressure, and volatility regime shifts in real time. The system supports both **live trading** (Schwab API) and **backtesting** (CSV files), with strategies fully abstracted from the data source.

---

## Architecture Overview

```
                    +------------------+
                    |   Data Sources   |
                    +--------+---------+
                             |
              +--------------+--------------+
              |                             |
     +--------v--------+          +--------v--------+
     | LiveDataSource   |          | CSVDataSource    |
     | (Schwab API)     |          | (Backtest CSVs)  |
     +---------+--------+          +--------+--------+
               |                            |
               +------------+---------------+
                            |
                   +--------v--------+
                   | DataSource ABC  |
                   | (common iface)  |
                   +--------+--------+
                            |
               +------------+------------+
               |            |            |
        +------v--+  +-----v-----+  +---v--------+
        | Ingest  |  | Signals   |  | Aggregator |
        | Pipeline|  | Engine    |  | (15-min    |
        |         |  |           |  |  rollups)  |
        +---------+  +-----------+  +------------+
               |            |            |
               +------------+------------+
                            |
                   +--------v--------+
                   |   PostgreSQL    |
                   |   (local)      |
                   +-----------------+
                            |
                   +--------v--------+
                   |   Strategies    |
                   |   (consume      |
                   |    signals)     |
                   +-----------------+
```

### Key Design Principles

1. **DataSource Abstraction** — Live and backtest share the same interface. Strategies never know where data came from.
2. **Signal Independence** — Each of the 4 signals is a self-contained module. They read from the database and write computed results back.
3. **Strategy Decoupling** — Trading strategies consume signal outputs only. They don't touch raw data or know about the ingestion method.
4. **PostgreSQL as the Single Source of Truth** — All raw snapshots and computed signals land in Postgres. Both live and backtest pipelines write to the same schema.

---

## Module Structure

```
z0dte/
  README.md                          # This file
  __init__.py
  docs/
    01_database_and_data_pipeline.md  # PostgreSQL schema + ingestion
    02_net_premium_flow.md            # Signal 1: bid/ask premium pressure
    03_iv_term_structure.md           # Signal 2: IV slope front vs back
    04_oi_walls.md                    # Signal 3: dynamic OI support/resistance
    05_gamma_decay_rate.md            # Signal 4: GEX rate of change
  db/
    schema.sql                        # Full PostgreSQL DDL
    migrations/                       # Schema versioning
    connection.py                     # Connection pool + helpers
  sources/
    __init__.py
    base.py                           # DataSource ABC
    live.py                           # LiveDataSource (Schwab API)
    csv_loader.py                     # CSVDataSource (backtest)
  ingestion/
    __init__.py
    pipeline.py                       # 15-min snapshot orchestrator
    normalizer.py                     # Raw data → canonical format
  signals/
    __init__.py
    base.py                           # Signal ABC
    net_premium_flow.py               # Signal 1
    iv_term_structure.py              # Signal 2
    oi_walls.py                       # Signal 3
    gamma_decay_rate.py               # Signal 4
  strategies/
    __init__.py
    base.py                           # Strategy ABC
  tests/
    conftest.py
    fixtures/                         # Sample CSV + JSON snapshots
    test_ingestion.py
    test_signals.py
    test_csv_loader.py
```

---

## The Four Signals

| # | Signal | What It Measures | Key Insight |
|---|--------|-----------------|-------------|
| 1 | **Net Premium Flow** | Dollar-weighted call vs put premium at bid/ask | Who's crossing the spread = conviction vs liquidation |
| 2 | **IV Term Structure Slope** | Front expiry ATM IV vs next expiry ATM IV | Steepening = imminent move expected; flattening = calm |
| 3 | **Put/Call OI Walls** | Highest OI concentration strikes, updated intraday | Dealer hedging creates dynamic support/resistance |
| 4 | **Gamma Decay Rate** | Rate of change of GEX per 15-min bar | Acceleration spikes = dealer hedging dominates price |

---

## PostgreSQL (Local Instance)

We use PostgreSQL instead of the existing SQLite (in `gex/storage.py`) because:
- **Concurrent access** — Live ingestion + signal computation + strategy queries simultaneously
- **Time-series queries** — Better window function performance for 15-min rolling aggregations
- **JSON operators** — Native JSONB for flexible raw data storage
- **Scalability** — Months of 15-min snapshots across multiple symbols

### Quick Start

```bash
# Install PostgreSQL (macOS)
brew install postgresql@16
brew services start postgresql@16

# Create database
createdb tos_0dte

# Apply schema
psql tos_0dte < z0dte/db/schema.sql
```

Connection config via environment variables:
```
ZDT_DB_HOST=localhost
ZDT_DB_PORT=5432
ZDT_DB_NAME=tos_0dte
ZDT_DB_USER=<your_user>
ZDT_DB_PASSWORD=<optional>
```

---

## Data Flow: Live Mode

```
Every 15 minutes (market hours 9:30-16:00 ET):

1. Scheduler triggers pipeline
2. LiveDataSource.fetch_snapshot(symbol="$SPX")
     → calls schwab/api.get_option_chain()
     → normalizes via schwab/models.flatten_option_chain()
3. Pipeline writes raw snapshot to `snapshots_0dte` table
4. Pipeline writes individual contracts to `contracts_0dte` table
5. Signal engine runs all 4 signals against new snapshot:
     a. NetPremiumFlow.compute(snapshot_id) → writes to `signal_premium_flow`
     b. IVTermStructure.compute(snapshot_id) → writes to `signal_iv_slope`
     c. OIWalls.compute(snapshot_id) → writes to `signal_oi_walls`
     d. GammaDecayRate.compute(snapshot_id) → writes to `signal_gamma_decay`
6. Strategies (if active) read latest signals and evaluate
```

## Data Flow: Backtest Mode

```
1. User provides CSV file(s) from Schwab export
2. CSVDataSource.load(path="data/2024-03-15_spx.csv")
     → parses CSV into canonical OptionContractRow format
     → generates synthetic timestamps at 15-min intervals
3. Pipeline replays snapshots sequentially:
     → writes to same PostgreSQL tables with backtest flag
4. Signal engine processes identically to live mode
5. Strategies evaluate identically — no code difference
```

---

## Integration with Existing Codebase

### Reused Components

| Existing Module | What We Reuse | Where |
|----------------|---------------|-------|
| `schwab/api.py` | `get_option_chain()`, `get_price_history()` | LiveDataSource |
| `schwab/models.py` | `OptionContractRow`, `flatten_option_chain()` | Normalizer |
| `gex/calculations.py` | `_signed_gamma_exposure()`, `_signed_delta_exposure()`, `_contract_metrics()` | Signals 3 & 4 |
| `schwab/client.py` | `create_client()`, `load_config()` | LiveDataSource auth |

### New Dependencies

```
psycopg[binary]    # PostgreSQL driver (async-ready)
apscheduler        # 15-min job scheduling (live mode)
```

---

## Implementation Chunks

The docs in `z0dte/docs/` are ordered for incremental implementation:

### Chunk 1: Database + Data Pipeline (`01_database_and_data_pipeline.md`)
- Stand up local Postgres
- Define full schema
- Build connection module
- Build ingestion pipeline (normalizer + writer)
- Build CSV loader for backtest
- **Testable milestone:** Load a CSV → query snapshots from psql

### Chunk 2: Net Premium Flow (`02_net_premium_flow.md`)
- Implement bid/ask premium classification
- Cumulative flow line computation
- Divergence detection vs price
- **Testable milestone:** Backtest a day of CSV data → see cumulative premium flow chart

### Chunk 3: IV Term Structure Slope (`03_iv_term_structure.md`)
- ATM IV extraction per expiry
- Front/back slope computation
- Steepen/flatten regime detection
- **Testable milestone:** Query slope time series for a backtest day

### Chunk 4: OI Walls (`04_oi_walls.md`)
- Strike-level OI aggregation
- Dynamic S/R level identification
- Dealer hedging direction overlay
- **Testable milestone:** Get ranked OI wall levels for any snapshot

### Chunk 5: Gamma Decay Rate (`05_gamma_decay_rate.md`)
- GEX per 15-min bar
- First derivative (rate of change)
- Acceleration spike detection
- **Testable milestone:** Flag bars where gamma acceleration exceeds threshold

### Chunk 6: Strategy Framework (future — not yet documented)
- Strategy ABC that consumes signal outputs
- Backtester harness that replays signals
- Live runner that evaluates on each new bar
