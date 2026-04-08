# Chunk 1: Database & Data Pipeline

## Goal

Stand up a local PostgreSQL database, define the schema for 15-minute options snapshots and computed signals, build the ingestion pipeline, and implement both live (Schwab API) and backtest (CSV) data sources behind a common abstraction.

---

## PostgreSQL Schema

### Core Tables

#### `snapshots_0dte`
Each row = one 15-minute capture of the full options chain for a symbol.

```sql
CREATE TABLE snapshots_0dte (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,               -- "$SPX", "SPY"
    captured_at     TIMESTAMPTZ NOT NULL,        -- bar timestamp (aligned to 15-min)
    underlying_price DOUBLE PRECISION NOT NULL,
    source          TEXT NOT NULL,               -- "schwab_live", "csv_backtest"
    is_backtest     BOOLEAN NOT NULL DEFAULT FALSE,
    chain_json      JSONB,                       -- full raw API/CSV payload
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (symbol, captured_at, is_backtest)
);

-- Fast lookups by symbol + time range
CREATE INDEX idx_snapshots_symbol_time
    ON snapshots_0dte (symbol, captured_at DESC);
```

**Design notes:**
- `captured_at` is always aligned to the nearest 15-min boundary (9:30, 9:45, 10:00, etc.)
- `is_backtest` flag lets us keep live and backtest data in the same table without collision
- `chain_json` stores the full payload for reprocessing; JSONB allows in-DB queries if needed
- The UNIQUE constraint prevents duplicate snapshots for the same bar

#### `contracts_0dte`
Individual option contracts from each snapshot, flattened.

```sql
CREATE TABLE contracts_0dte (
    id                  BIGSERIAL PRIMARY KEY,
    snapshot_id         BIGINT NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol              TEXT NOT NULL,           -- option contract symbol
    underlying_symbol   TEXT NOT NULL,
    underlying_price    DOUBLE PRECISION,
    expiration_date     DATE NOT NULL,
    dte                 INTEGER,
    strike              DOUBLE PRECISION NOT NULL,
    put_call            TEXT NOT NULL CHECK (put_call IN ('CALL', 'PUT')),

    -- Pricing
    bid                 DOUBLE PRECISION,
    ask                 DOUBLE PRECISION,
    last                DOUBLE PRECISION,
    mark                DOUBLE PRECISION,

    -- Greeks
    delta               DOUBLE PRECISION,
    gamma               DOUBLE PRECISION,
    theta               DOUBLE PRECISION,
    vega                DOUBLE PRECISION,
    volatility          DOUBLE PRECISION,       -- implied vol

    -- Volume & OI
    open_interest       INTEGER,
    total_volume        INTEGER,
    in_the_money        BOOLEAN,

    -- Bid/ask side volume (for premium flow signal)
    -- These may be NULL if the data source doesn't provide them
    volume_at_bid       INTEGER,
    volume_at_ask       INTEGER,

    raw_json            JSONB
);

CREATE INDEX idx_contracts_snapshot
    ON contracts_0dte (snapshot_id);
CREATE INDEX idx_contracts_strike_exp
    ON contracts_0dte (underlying_symbol, strike, expiration_date);
CREATE INDEX idx_contracts_putcall
    ON contracts_0dte (snapshot_id, put_call);
```

**Design notes:**
- Maps 1:1 to the existing `OptionContractRow` dataclass in `schwab/models.py`
- Added `volume_at_bid` / `volume_at_ask` fields for Net Premium Flow signal — Schwab provides this in the raw payload under the `bidAskSize` and trade-level fields. If not directly available, we'll estimate from bid/ask proximity of last trade price.
- Indexes optimized for the signal queries that follow

### Signal Output Tables

Each signal writes its computed results to a dedicated table, keyed by snapshot_id.

#### `signal_premium_flow`
```sql
CREATE TABLE signal_premium_flow (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     BIGINT NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,

    -- Per-bar metrics
    call_premium_at_ask   DOUBLE PRECISION NOT NULL,  -- aggressive call buying ($)
    call_premium_at_bid   DOUBLE PRECISION NOT NULL,  -- call liquidation ($)
    put_premium_at_ask    DOUBLE PRECISION NOT NULL,  -- aggressive put buying ($)
    put_premium_at_bid    DOUBLE PRECISION NOT NULL,   -- put liquidation ($)
    net_premium_flow      DOUBLE PRECISION NOT NULL,  -- (call_ask - call_bid) - (put_ask - put_bid)

    -- Cumulative (running sum since market open)
    cumulative_flow       DOUBLE PRECISION NOT NULL,

    -- Derived
    flow_velocity         DOUBLE PRECISION,           -- rate of change vs prior bar
    price_at_bar          DOUBLE PRECISION,           -- underlying price for divergence detection

    UNIQUE (snapshot_id)
);
```

#### `signal_iv_slope`
```sql
CREATE TABLE signal_iv_slope (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     BIGINT NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,

    -- IV readings
    front_expiry        DATE NOT NULL,           -- nearest expiry (0DTE or 1DTE)
    front_atm_iv        DOUBLE PRECISION NOT NULL,
    back_expiry         DATE NOT NULL,            -- next expiry out
    back_atm_iv         DOUBLE PRECISION NOT NULL,

    -- Slope
    iv_slope            DOUBLE PRECISION NOT NULL,  -- front_iv - back_iv
    iv_slope_ratio      DOUBLE PRECISION,           -- front_iv / back_iv
    slope_change        DOUBLE PRECISION,           -- delta vs prior bar

    -- Regime
    slope_regime        TEXT,                       -- "steepening", "flattening", "flat", "inverted"

    UNIQUE (snapshot_id)
);
```

#### `signal_oi_walls`
```sql
CREATE TABLE signal_oi_walls (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     BIGINT NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,
    strike          DOUBLE PRECISION NOT NULL,

    -- OI at this strike
    call_oi             INTEGER NOT NULL,
    put_oi              INTEGER NOT NULL,
    total_oi            INTEGER NOT NULL,

    -- Intraday volume building at this strike
    call_volume         INTEGER NOT NULL DEFAULT 0,
    put_volume          INTEGER NOT NULL DEFAULT 0,

    -- Classification
    wall_type           TEXT,                       -- "call_wall", "put_wall", "mixed"
    wall_strength       DOUBLE PRECISION,           -- normalized 0-1 relative to day's max
    dealer_hedge_direction TEXT,                     -- "buying_stock", "selling_stock"
    distance_from_spot  DOUBLE PRECISION,           -- % distance from current price

    UNIQUE (snapshot_id, strike)
);
```

#### `signal_gamma_decay`
```sql
CREATE TABLE signal_gamma_decay (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     BIGINT NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,

    -- GEX snapshot
    total_gex           DOUBLE PRECISION NOT NULL,
    atm_gex             DOUBLE PRECISION,           -- GEX at nearest ATM strike

    -- Rate of change
    gex_delta           DOUBLE PRECISION,           -- change from prior bar
    gex_acceleration    DOUBLE PRECISION,           -- change of change (2nd derivative)

    -- Regime
    acceleration_regime TEXT,                       -- "accelerating", "decelerating", "stable"
    is_spike            BOOLEAN NOT NULL DEFAULT FALSE, -- acceleration > threshold

    UNIQUE (snapshot_id)
);
```

---

## DataSource Abstraction

### Abstract Base Class

```python
# 0dte/sources/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from schwab.models import OptionContractRow


@dataclass
class Snapshot:
    """One 15-minute capture of the full option chain."""
    symbol: str
    captured_at: datetime           # aligned to 15-min boundary
    underlying_price: float
    contracts: list[OptionContractRow]
    raw_payload: dict | None = None  # full API/CSV data for storage
    source: str = "unknown"


class DataSource(ABC):
    """Common interface for all data sources."""

    @abstractmethod
    def fetch_snapshot(self, symbol: str) -> Snapshot:
        """Fetch current/next snapshot for the symbol.

        - Live: calls Schwab API right now
        - CSV: yields the next row in the replay sequence
        """
        ...

    @abstractmethod
    def has_more(self) -> bool:
        """True if more data is available (always True for live)."""
        ...
```

### LiveDataSource

```python
# 0dte/sources/live.py

class LiveDataSource(DataSource):
    """Fetches real-time data from Schwab API."""

    def __init__(self):
        from schwab.client import create_client
        self.client = create_client()
        self.source = "schwab_live"

    def fetch_snapshot(self, symbol: str) -> Snapshot:
        from schwab.api import get_option_chain
        from schwab.models import flatten_option_chain

        chain_data = get_option_chain(
            symbol=symbol,
            days=7,              # capture 0DTE through ~weekly expiry
            contract_type="ALL",
            option_range="ALL",
            include_underlying_quote=True,
        )

        rows = flatten_option_chain(chain_data, symbol)
        underlying_price = rows[0].underlying_price if rows else 0.0
        captured_at = _align_to_15min(datetime.now(ZoneInfo("US/Eastern")))

        return Snapshot(
            symbol=symbol,
            captured_at=captured_at,
            underlying_price=underlying_price,
            contracts=rows,
            raw_payload=chain_data,
            source=self.source,
        )

    def has_more(self) -> bool:
        return True  # live source always has more
```

### CSVDataSource

```python
# 0dte/sources/csv_loader.py

class CSVDataSource(DataSource):
    """Replays historical data from Schwab CSV exports."""

    def __init__(self, csv_path: str | Path, symbol: str):
        self.frames = self._parse_csv(csv_path, symbol)
        self.index = 0
        self.source = "csv_backtest"

    def fetch_snapshot(self, symbol: str) -> Snapshot:
        snapshot = self.frames[self.index]
        self.index += 1
        return snapshot

    def has_more(self) -> bool:
        return self.index < len(self.frames)

    def _parse_csv(self, path, symbol) -> list[Snapshot]:
        """Parse Schwab CSV export into list of Snapshots.

        Schwab CSV format has columns:
        Symbol, Expiration, Strike, Type, Bid, Ask, Last, Volume,
        Open Interest, IV, Delta, Gamma, Theta, Vega, ...

        If the CSV contains a single point-in-time export,
        we treat it as one snapshot. If it contains intraday
        timestamps, we group by timestamp into multiple snapshots.
        """
        ...
```

**CSV Format Notes:**
- Schwab's "Option Chain" export gives a flat CSV with one row per contract
- If the export lacks timestamps, the CSVDataSource treats the whole file as a single snapshot
- For multi-snapshot backtests, either: (a) use multiple CSV files (one per 15-min bar), or (b) use a CSV that includes a timestamp column
- The normalizer maps CSV columns to `OptionContractRow` fields

---

## Ingestion Pipeline

### Pipeline Orchestrator

```python
# 0dte/ingestion/pipeline.py

class IngestionPipeline:
    """Orchestrates: fetch → normalize → persist → signal compute."""

    def __init__(self, source: DataSource, db_conn, signals: list[Signal]):
        self.source = source
        self.db = db_conn
        self.signals = signals

    def run_one(self, symbol: str) -> int:
        """Process one 15-min bar. Returns snapshot_id."""
        # 1. Fetch
        snapshot = self.source.fetch_snapshot(symbol)

        # 2. Persist raw snapshot
        snapshot_id = self._write_snapshot(snapshot)

        # 3. Persist individual contracts
        self._write_contracts(snapshot_id, snapshot)

        # 4. Compute all signals
        for signal in self.signals:
            signal.compute(snapshot_id, self.db)

        return snapshot_id

    def run_backtest(self, symbol: str):
        """Replay all available snapshots."""
        while self.source.has_more():
            self.run_one(symbol)

    def run_live(self, symbol: str, interval_minutes: int = 15):
        """Schedule recurring fetch during market hours."""
        from apscheduler.schedulers.blocking import BlockingScheduler

        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.run_one,
            trigger="cron",
            args=[symbol],
            day_of_week="mon-fri",
            hour="9-15",          # 9:30-15:45 ET covered
            minute="0,15,30,45",
            timezone="US/Eastern",
        )
        # Also run at 9:30 specifically (market open)
        scheduler.start()
```

### Normalizer

```python
# 0dte/ingestion/normalizer.py

def normalize_snapshot_for_db(snapshot: Snapshot) -> dict:
    """Convert Snapshot to database-ready dict."""
    return {
        "symbol": snapshot.symbol,
        "captured_at": snapshot.captured_at,
        "underlying_price": snapshot.underlying_price,
        "source": snapshot.source,
        "is_backtest": snapshot.source == "csv_backtest",
        "chain_json": json.dumps(snapshot.raw_payload) if snapshot.raw_payload else None,
    }

def normalize_contract_for_db(contract: OptionContractRow, snapshot_id: int) -> dict:
    """Convert OptionContractRow to database-ready dict."""
    return {
        "snapshot_id": snapshot_id,
        "symbol": contract.symbol,
        "underlying_symbol": contract.underlying_symbol,
        "underlying_price": contract.underlying_price,
        "expiration_date": contract.expiration_date,
        "dte": contract.dte,
        "strike": contract.strike,
        "put_call": contract.put_call,
        "bid": contract.bid,
        "ask": contract.ask,
        "last": contract.last,
        "mark": contract.mark,
        "delta": contract.delta,
        "gamma": contract.gamma,
        "theta": contract.theta,
        "vega": contract.vega,
        "volatility": contract.volatility,
        "open_interest": contract.open_interest,
        "total_volume": contract.total_volume,
        "in_the_money": contract.in_the_money,
        "volume_at_bid": _extract_volume_at_bid(contract.raw),
        "volume_at_ask": _extract_volume_at_ask(contract.raw),
        "raw_json": json.dumps(contract.raw) if contract.raw else None,
    }
```

---

## Database Connection Module

```python
# 0dte/db/connection.py

import os
import psycopg
from psycopg.rows import dict_row

def get_connection(**overrides) -> psycopg.Connection:
    """Create a PostgreSQL connection from environment variables."""
    params = {
        "host": os.environ.get("ZDT_DB_HOST", "localhost"),
        "port": int(os.environ.get("ZDT_DB_PORT", "5432")),
        "dbname": os.environ.get("ZDT_DB_NAME", "tos_0dte"),
        "user": os.environ.get("ZDT_DB_USER", os.environ.get("USER")),
        "password": os.environ.get("ZDT_DB_PASSWORD", ""),
    }
    params.update(overrides)
    return psycopg.connect(**params, row_factory=dict_row)

def init_db(conn: psycopg.Connection):
    """Apply schema from schema.sql."""
    schema_path = Path(__file__).parent / "schema.sql"
    conn.execute(schema_path.read_text())
    conn.commit()
```

---

## 15-Minute Time Alignment

All timestamps are aligned to 15-minute boundaries during market hours:

```
Market open:  09:30 ET
First bar:    09:30 (captures 09:30:00 - 09:44:59)
Second bar:   09:45
...
Last bar:     15:45 (captures 15:45:00 - 15:59:59)
Market close: 16:00 ET

Total bars per day: 26 (09:30, 09:45, ..., 15:45)
```

```python
def align_to_15min(dt: datetime) -> datetime:
    """Round down to nearest 15-min boundary."""
    return dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)
```

---

## Testing Strategy

### Unit Tests
- `test_csv_loader.py` — Parse sample Schwab CSVs into Snapshots
- `test_normalizer.py` — OptionContractRow → DB dict mapping
- `test_time_alignment.py` — 15-min boundary logic

### Integration Tests
- `test_pipeline.py` — CSV → PostgreSQL round-trip
  - Load fixture CSV
  - Run pipeline
  - Query snapshots and contracts from DB
  - Verify row counts and field values

### Fixture Data
- `tests/fixtures/sample_spx_chain.csv` — One snapshot of SPX chain from Schwab
- `tests/fixtures/sample_spy_intraday.csv` — Full day of 15-min snapshots

### Test Database
Tests use a dedicated `tos_0dte_test` database, created/dropped per test session:
```python
@pytest.fixture(scope="session")
def test_db():
    conn = get_connection(dbname="tos_0dte_test")
    init_db(conn)
    yield conn
    conn.close()
```

---

## Milestone Checklist

- [ ] PostgreSQL installed and `tos_0dte` database created
- [ ] `schema.sql` written and applied
- [ ] `connection.py` connects and queries successfully
- [ ] `CSVDataSource` parses a sample Schwab CSV into `Snapshot` objects
- [ ] `LiveDataSource` fetches a real snapshot from Schwab API
- [ ] `IngestionPipeline.run_one()` writes snapshot + contracts to DB
- [ ] `IngestionPipeline.run_backtest()` replays a full CSV file
- [ ] All tests pass against `tos_0dte_test`
