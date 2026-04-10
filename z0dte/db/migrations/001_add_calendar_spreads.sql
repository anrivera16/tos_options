-- Migration: Add Calendar Spread Signals and Trades Tracking
-- Date: 2026-04-08
-- Purpose: Schema extensions for calendar spread detection and position tracking

CREATE TABLE IF NOT EXISTS signal_calendar_violations (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    front_expiry DATE NOT NULL,
    front_atm_strike NUMERIC(7,2),
    front_atm_iv NUMERIC(6,4),
    back_expiry DATE NOT NULL,
    back_atm_strike NUMERIC(7,2),
    back_atm_iv NUMERIC(6,4),
    iv_slope NUMERIC(6,4),
    violation_severity NUMERIC(6,4),
    is_violation BOOLEAN DEFAULT FALSE,
    violation_basis_points INTEGER,
    front_dte INTEGER,
    back_dte INTEGER,
    underlying_price NUMERIC(8,2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_violations_symbol_time ON signal_calendar_violations(symbol, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_violations_active ON signal_calendar_violations(is_violation, captured_at DESC);

CREATE TABLE IF NOT EXISTS signal_calendar_opportunities (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    violation_id INTEGER REFERENCES signal_calendar_violations(id) ON DELETE SET NULL,
    opportunity_score NUMERIC(6,4) NOT NULL,
    severity_score NUMERIC(6,4),
    theta_score NUMERIC(6,4),
    iv_regime_score NUMERIC(6,4),
    momentum_score NUMERIC(6,4),
    confidence NUMERIC(6,4),
    entry_signal VARCHAR(50),
    suggested_strike NUMERIC(7,2),
    suggested_quantity INTEGER DEFAULT 1,
    estimated_entry_cost NUMERIC(10,2),
    estimated_max_profit NUMERIC(10,2),
    optimal_hold_days INTEGER,
    days_to_roll INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opportunities_symbol_score ON signal_calendar_opportunities(symbol, opportunity_score DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_confidence ON signal_calendar_opportunities(confidence DESC, captured_at DESC);

CREATE TABLE IF NOT EXISTS calendar_spread_trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(36) UNIQUE NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    entry_timestamp TIMESTAMP NOT NULL,
    entry_snapshot_id INTEGER REFERENCES snapshots_0dte(id),
    entry_opportunity_id INTEGER REFERENCES signal_calendar_opportunities(id),
    entry_price NUMERIC(10,2) NOT NULL,
    entry_reason VARCHAR(255),
    front_expiry DATE NOT NULL,
    back_expiry DATE NOT NULL,
    strike NUMERIC(7,2) NOT NULL,
    option_type VARCHAR(4) NOT NULL,
    quantity INTEGER DEFAULT 1,
    delta_entry NUMERIC(8,6),
    gamma_entry NUMERIC(8,6),
    theta_entry_per_day NUMERIC(8,6),
    vega_entry NUMERIC(8,6),
    current_price NUMERIC(10,2),
    current_pnl NUMERIC(12,2),
    current_pnl_pct NUMERIC(8,4),
    current_delta NUMERIC(8,6),
    current_theta_per_day NUMERIC(8,6),
    exit_timestamp TIMESTAMP,
    exit_snapshot_id INTEGER REFERENCES snapshots_0dte(id),
    exit_price NUMERIC(10,2),
    exit_reason VARCHAR(50),
    delta_exit NUMERIC(8,6),
    gamma_exit NUMERIC(8,6),
    theta_exit_per_day NUMERIC(8,6),
    vega_exit NUMERIC(8,6),
    final_pnl NUMERIC(12,2),
    final_pnl_pct NUMERIC(8,4),
    max_profit_realized NUMERIC(12,2),
    max_loss_realized NUMERIC(12,2),
    hold_duration_days NUMERIC(8,2),
    hold_duration_hours NUMERIC(8,2),
    entry_iv_slope NUMERIC(6,4),
    exit_iv_slope NUMERIC(6,4),
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol_status ON calendar_spread_trades(symbol, status);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON calendar_spread_trades(entry_timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_open ON calendar_spread_trades(status, entry_timestamp DESC);

CREATE TABLE IF NOT EXISTS calendar_spread_performance (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date_traded DATE NOT NULL,
    trades_opened INTEGER DEFAULT 0,
    trades_closed INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    breakeven_trades INTEGER DEFAULT 0,
    total_pnl NUMERIC(12,2),
    avg_pnl_per_trade NUMERIC(10,2),
    median_pnl_per_trade NUMERIC(10,2),
    max_win NUMERIC(12,2),
    max_loss NUMERIC(12,2),
    win_rate NUMERIC(6,4),
    profit_factor NUMERIC(8,4),
    payoff_ratio NUMERIC(8,4),
    sharpe_ratio NUMERIC(8,4),
    max_drawdown NUMERIC(8,4),
    avg_hold_days NUMERIC(8,2),
    avg_theta_collected NUMERIC(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_performance_symbol ON calendar_spread_performance(symbol);
