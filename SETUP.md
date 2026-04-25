# TOS Options — Schwab API Aggregation Platform

Real-time options data pipeline that scrapes the Schwab/TDA API, stores everything in PostgreSQL, and runs automated scanners for trading opportunities. Built with Docker Compose.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
│                                                         │
│  ┌──────────────┐   every 5 min    ┌────────────────┐   │
│  │ scraper-watch│ ───────────────► │ PostgreSQL DB  │   │
│  │              │                  │   (port 5433)  │   │
│  │ Schwab OAuth │   every 5 min    │                │   │
│  │ API client   │ ───────────────► │ 1.2M contracts │   │
│  └──────────────┘                  │ 1,156 snapshots│   │
│                                    │ 497 MB total   │
│  ┌──────────────────┐              └───────┬────────┘   │
│  │ universe-scanner │ ◄── reads DB ────────┘            │
│  │ (every 30 min)   │─ posts top picks to Discord       │
│  └──────────────────┘                                    │
│                                                         │
│  ┌──────────────┐              ┌──────────────────┐     │
│  │scanner-watch │ ◄── reads DB─│ spread-hunter    │     │
│  │(every 5 min) │              │ (every 15 min)   │     │
│  └──────────────┘              └──────────────────┘     │
│      │                              │                    │
│      └──── both post alerts to Discord ────┘            │
│                                                         │
│  ┌──────────────────────────────────────┐               │
│  │ options-backtest (offline)           │               │
│  │ 425 GB historical data + backtester  │               │
│  └──────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────┘
         │                              │
    Schwab API                    Discord Webhooks
    (OAuth tokens)               (alerts & picks)
```

---

## Services

All defined in `docker-compose.yml`, built from a single `Dockerfile` (Python 3.12-slim).

### Always-On Services

| Service | Schedule | Description |
|---------|----------|-------------|
| **db** | always on | PostgreSQL 15. Exposed on host port 5433. Stores all scraped options data. |
| **scraper-watch** | every 5 min, 9:30 AM–4:00 PM ET | Scrapes full options chains from Schwab API. Base tickers: $SPX, SPY, QQQ. Dynamically adds universe scanner picks each cycle. |
| **scanner-watch** | every 5 min, 9:00 AM–4:00 PM ET | Runs the live scanner — unusual activity, IV spikes, volume anomalies. Posts alerts to Discord. |
| **spread-hunter** | every 15 min, 9:30 AM–4:00 PM ET | Builds vertical spreads (bull put credits, bear call credits, iron condors, iron flys, calendars). Scores and posts top opportunities to Discord. |
| **universe-scanner** | pre-market 9:15 AM + every 30 min | Scans the full market for high-momentum names using price change, relative volume, and news activity. Saves top 8 picks to `config/dynamic_tickers.json` for the scraper to pick up. Posts picks to Discord. |

### One-Shot Services

| Service | Description |
|---------|-------------|
| **cli** | CLI tool (`cli.py`) — IV term structure, status checks, etc. |
| **options-backtest** | Offline backtesting engine with 425 GB of historical data (Polygon.io flat files) |

---

## Data Flow

### Scraping Pipeline

1. **scraper-watch** authenticates via Schwab OAuth (tokens mount at `/root/.schwabdev`, refresh every ~7 days)
2. Each cycle loads base tickers ($SPX, SPY, QQQ) + dynamic tickers from `config/dynamic_tickers.json`
3. For each ticker, calls the Schwab options chains API with configured strike count and DTE range
4. Writes raw chain data to `snapshots` table, individual contracts to `option_contracts` table
5. GEX calculations (Gamma Exposure, Delta Exposure, Vanna Exposure, Theta Exposure) computed and stored in aggregate tables

### Universe Scanner Pipeline

1. Fetches full market screener from Schwab API (top movers by price change %)
2. Filters for: price > $1, avg volume > 500K, options available
3. Scores each name: momentum + relative volume + options liquidity
4. Top 8 names saved to `config/dynamic_tickers.json`
5. Scraper picks these up on next cycle

### Spread Hunter Pipeline

1. Fetches latest contracts from DB (no API calls — pure DB queries)
2. Pre-filters legs with wide delta band (0.02–0.40), OI > 100, volume > 50
3. Applies tight delta filter (0.10–0.25) to SHORT leg only during spread construction
4. Builds 5 spread types: bull put credit, bear call credit, iron condor, iron fly, calendar
5. Scores each spread by ROI, risk/reward, liquidity, IV rank
6. Posts top opportunities to Discord

---

## Database Schema

PostgreSQL 15, ~497 MB, 6 custom indexes.

### `snapshots` — one row per ticker per scrape

| Column | Type | Description |
|--------|------|-------------|
| id | bigint (PK) | Auto-increment |
| symbol | text | Ticker symbol (e.g. "SPY", " $SPX") |
| captured_at | text | ISO timestamp of scrape |
| underlying_price | float | Price at time of scrape |
| source | text | "schwab_api" |
| chain_json | text | Full raw API response |

### `option_contracts` — one row per individual option contract

| Column | Type | Description |
|--------|------|-------------|
| id | bigint (PK) | Auto-increment |
| snapshot_id | bigint (FK) | Links to snapshots |
| symbol | text | Full OCC symbol (e.g. "SPY_042522P700") |
| underlying_symbol | text | Base ticker (e.g. "SPY") |
| underlying_price | float | Price when scraped |
| expiration_date | text | Option expiration |
| dte | integer | Days to expiration |
| strike | float | Strike price |
| put_call | text | "PUT" or "CALL" |
| bid / ask / last / mark | float | Pricing |
| delta / gamma / theta / vega | float | Greeks (from Schwab) |
| volatility | float | Implied volatility |
| open_interest | integer | OI |
| total_volume | integer | Day's volume |
| in_the_money | integer | ITM flag |
| raw_json | text | Full contract JSON |

### Aggregate Tables (GEX)

- `aggregates_by_strike` — net GEX/DEX/VEX/TEX per strike
- `aggregates_by_expiry` — net GEX/DEX/VEX/TEX per expiration + PCR, ATM IV
- `aggregates_by_bucket` — custom bucket aggregations

### Indexes (6 total, ~94 MB)

```
idx_oc_snapshot_putcall_strike   — (snapshot_id, put_call, strike)
idx_oc_snapshot_putcall_dte      — (snapshot_id, put_call, dte)
idx_oc_snapshot_putcall_vol      — (snapshot_id, put_call, volatility)
idx_oc_symbol                    — (underlying_symbol)
idx_snap_symbol_captured         — (symbol, captured_at)
idx_snap_captured                — (captured_at)
```

Query speedup: ~180x (56ms → 0.31ms on typical spread hunter queries).

---

## Auth

- Uses the **schwabdev** Python library for Schwab/TDA OAuth2 flow
- Tokens stored at `~/.schwabdev/tokens.db` on host, mounted into containers
- Tokens expire ~every 7 days — re-auth is interactive (30-second code window)
- All services share the same token mount

---

## Project Structure

```
tos_options/
├── docker-compose.yml          # All services defined here
├── Dockerfile                  # Single image, Python 3.12-slim
├── requirements.txt            # Python dependencies
├── cli.py                      # CLI tool (IV term structure, status, etc.)
│
├── schwab/                     # Schwab API client wrapper
│   ├── api.py                  # High-level API functions
│   ├── client.py               # OAuth client setup
│   └── models.py               # Data models
│
├── gex/                        # Gamma Exposure calculations
│   ├── calculations.py         # Core GEX/DEX/VEX/TEX math
│   ├── iv_term.py              # IV term structure module
│   ├── storage.py              # DB connection helpers
│   └── chart.py                # Chart generation
│
├── spread_hunter/              # Spread analysis engine
│   ├── spread_types.py         # Dataclasses: Leg, VerticalSpread, SignalFilter
│   ├── spread_builder.py       # Builds 5 spread types from DB data
│   ├── signal_filters.py       # Delta, IV rank, SMA, OI/volume filters
│   ├── spread_scoring.py       # Scoring and ranking
│   └── spread_display.py       # Console + Discord formatting
│
├── discord/                    # Discord webhook integration
│   └── webhook.py              # send_message() helper
│
├── scripts/                    # Service entrypoints + utilities
│   ├── options_scraper.py      # scraper-watch main loop
│   ├── live_scanner.py         # scanner-watch main loop
│   ├── spread_hunter.py        # spread-hunter main loop
│   ├── universe_scanner.py     # universe-scanner main loop
│   ├── status_check.py         # System health checker
│   ├── premium_decay_chart.py  # Premium decay visualization
│   └── tos_trade_log.py        # TOS-ready trade details with OCC symbols
│
├── config/                     # Runtime config
│   ├── dynamic_tickers.json    # Universe scanner output
│   └── watchlist.yaml          # Manual watchlist
│
├── options-backtest/           # Offline backtesting (separate system)
│   ├── backtest.py             # Main backtest engine
│   ├── strategy.py             # Strategy definitions
│   ├── ingest.py               # Polygon.io flat file ingestion
│   └── ...                     # 425 GB historical data
│
└── tests/                      # Test suite
    ├── test_cli.py
    ├── test_gex.py
    ├── test_models.py
    ├── test_schwab_api.py
    └── test_storage.py
```

---

## Storage Projections

| Ticker Count | Daily Contracts | Monthly | Yearly |
|-------------|----------------|---------|--------|
| 3 (base only) | ~600K | 12M | 40 GB |
| 11 (+8 dynamic) | ~750K | 15M | 49 GB |
| 30+ | ~1.2M | 24M | 80 GB |

Retention policy can cap at ~20 GB indefinitely by pruning snapshots older than 30 days.

---

## Quick Start

```bash
# 1. Set up auth tokens
# First time: interactive OAuth flow (get code from Schwab)
cp .env.example .env
# Edit .env with your Schwab app key, Discord webhook URL, etc.

# 2. Start everything
docker compose up -d

# 3. Check status
docker compose ps
docker compose logs scraper-watch --tail 20

# 4. Rebuild after code changes
docker compose build && docker compose up -d
```

---

## Key Design Decisions

- **No API calls in analysis services** — spread-hunter and scanner-watch read only from the DB. Only scraper-watch and universe-scanner hit the Schwab API.
- **Dynamic tickers loaded per-cycle** — the scraper reads `config/dynamic_tickers.json` on every 5-min cycle, so universe scanner picks are always fresh.
- **Tight delta on short leg only** — pre-filter uses a wide band (0.02–0.40), then the tight 0.10–0.25 range is applied to the SHORT leg during spread construction. The long leg naturally has lower delta.
- **Single Dockerfile** — all services share one image with different entrypoint commands.
- **Token refresh is manual** — OAuth tokens expire ~7 days. Re-auth requires an interactive browser flow (30-second code window).
