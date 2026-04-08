CREATE TABLE snapshots_0dte (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,
    underlying_price DOUBLE PRECISION NOT NULL,
    source          TEXT NOT NULL,
    is_backtest     BOOLEAN NOT NULL DEFAULT FALSE,
    chain_json      JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (symbol, captured_at, is_backtest)
);

CREATE INDEX idx_snapshots_symbol_time
    ON snapshots_0dte (symbol, captured_at DESC);

CREATE TABLE contracts_0dte (
    id                  BIGSERIAL PRIMARY KEY,
    snapshot_id         BIGINT NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol              TEXT NOT NULL,
    underlying_symbol   TEXT NOT NULL,
    underlying_price    DOUBLE PRECISION,
    expiration_date     DATE NOT NULL,
    dte                 INTEGER,
    strike              DOUBLE PRECISION NOT NULL,
    put_call            TEXT NOT NULL CHECK (put_call IN ('CALL', 'PUT')),

    bid                 DOUBLE PRECISION,
    ask                 DOUBLE PRECISION,
    last                DOUBLE PRECISION,
    mark                DOUBLE PRECISION,

    delta               DOUBLE PRECISION,
    gamma               DOUBLE PRECISION,
    theta               DOUBLE PRECISION,
    vega                DOUBLE PRECISION,
    volatility          DOUBLE PRECISION,

    open_interest       INTEGER,
    total_volume        INTEGER,
    in_the_money        BOOLEAN,

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

CREATE TABLE signal_premium_flow (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     BIGINT NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,

    call_premium_at_ask   DOUBLE PRECISION NOT NULL,
    call_premium_at_bid   DOUBLE PRECISION NOT NULL,
    put_premium_at_ask    DOUBLE PRECISION NOT NULL,
    put_premium_at_bid    DOUBLE PRECISION NOT NULL,
    net_premium_flow      DOUBLE PRECISION NOT NULL,

    cumulative_flow       DOUBLE PRECISION NOT NULL,

    flow_velocity         DOUBLE PRECISION,
    price_at_bar          DOUBLE PRECISION,

    UNIQUE (snapshot_id)
);

CREATE TABLE signal_iv_slope (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     BIGINT NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,

    front_expiry        DATE NOT NULL,
    front_atm_iv        DOUBLE PRECISION NOT NULL,
    back_expiry         DATE NOT NULL,
    back_atm_iv         DOUBLE PRECISION NOT NULL,

    iv_slope            DOUBLE PRECISION NOT NULL,
    iv_slope_ratio      DOUBLE PRECISION,
    slope_change        DOUBLE PRECISION,

    slope_regime        TEXT,

    UNIQUE (snapshot_id)
);

CREATE TABLE signal_oi_walls (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     BIGINT NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,
    strike          DOUBLE PRECISION NOT NULL,

    call_oi             INTEGER NOT NULL,
    put_oi              INTEGER NOT NULL,
    total_oi            INTEGER NOT NULL,

    call_volume         INTEGER NOT NULL DEFAULT 0,
    put_volume          INTEGER NOT NULL DEFAULT 0,

    wall_type           TEXT,
    wall_strength       DOUBLE PRECISION,
    dealer_hedge_direction TEXT,
    distance_from_spot  DOUBLE PRECISION,

    UNIQUE (snapshot_id, strike)
);

CREATE TABLE signal_gamma_decay (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     BIGINT NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,

    total_gex           DOUBLE PRECISION NOT NULL,
    atm_gex             DOUBLE PRECISION,

    gex_delta           DOUBLE PRECISION,
    gex_acceleration    DOUBLE PRECISION,

    acceleration_regime TEXT,
    is_spike            BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (snapshot_id)
);
