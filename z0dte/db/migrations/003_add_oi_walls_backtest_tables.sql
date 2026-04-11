CREATE TABLE IF NOT EXISTS oi_walls_backtest_runs (
    id                      BIGSERIAL PRIMARY KEY,
    symbol                  TEXT NOT NULL,
    start_date              DATE NOT NULL,
    end_date                DATE NOT NULL,
    interval_minutes        INTEGER NOT NULL,
    top_n                   INTEGER NOT NULL,
    max_dte                 INTEGER NOT NULL,
    strike_range_pct        DOUBLE PRECISION NOT NULL,
    forward_minutes         JSONB NOT NULL,
    source                  TEXT NOT NULL,
    metadata_json           JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oi_walls_backtest_runs_symbol_dates
    ON oi_walls_backtest_runs (symbol, start_date, end_date);

CREATE TABLE IF NOT EXISTS oi_walls_backtest_events (
    id                      BIGSERIAL PRIMARY KEY,
    run_id                  BIGINT NOT NULL REFERENCES oi_walls_backtest_runs(id) ON DELETE CASCADE,
    symbol                  TEXT NOT NULL,
    captured_at             TIMESTAMPTZ NOT NULL,
    underlying_price        DOUBLE PRECISION NOT NULL,
    snapshot_id             BIGINT REFERENCES snapshots_0dte(id) ON DELETE SET NULL,
    top_call_contract_id    BIGINT REFERENCES contracts_0dte(id) ON DELETE SET NULL,
    top_put_contract_id     BIGINT REFERENCES contracts_0dte(id) ON DELETE SET NULL,
    contract_count          INTEGER NOT NULL,
    strike_count            INTEGER NOT NULL,
    bias                    TEXT NOT NULL,
    is_hit                  BOOLEAN,
    pin_lower               DOUBLE PRECISION,
    pin_upper               DOUBLE PRECISION,
    pin_width               DOUBLE PRECISION,
    pin_width_pct           DOUBLE PRECISION,
    is_pin_hit              BOOLEAN,
    top_call_walls_json     JSONB NOT NULL,
    top_put_walls_json      JSONB NOT NULL,
    forward_returns_json    JSONB NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, captured_at)
);

CREATE INDEX IF NOT EXISTS idx_oi_walls_backtest_events_run_time
    ON oi_walls_backtest_events (run_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_oi_walls_backtest_events_symbol_time
    ON oi_walls_backtest_events (symbol, captured_at DESC);
