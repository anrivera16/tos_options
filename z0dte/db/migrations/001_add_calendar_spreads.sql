-- Migration: Add Calendar Spread Signals and Trades Tracking
-- Date: 2026-04-08
-- Purpose: Schema extensions for calendar spread detection and position tracking

-- Signal 1: Term Structure Violations
CREATE TABLE IF NOT EXISTS signal_calendar_violations (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    
    -- Term structure pair
    front_expiry DATE NOT NULL,
    front_atm_strike NUMERIC(7,2),
    front_atm_iv NUMERIC(6,4),
    
    back_expiry DATE NOT NULL,
    back_atm_strike NUMERIC(7,2),
    back_atm_iv NUMERIC(6,4),
    
    -- Violation metrics
    iv_slope NUMERIC(6,4),                  -- front_iv - back_iv (NEGATIVE = violation)
    violation_severity NUMERIC(6,4),        -- abs(iv_slope) if violation
    is_violation BOOLEAN DEFAULT FALSE,     -- Crosses threshold
    violation_basis_points INTEGER,         -- iv_slope in basis points
    
    -- Additional context
    front_dte INTEGER,                      -- Days to expiration (front)
    back_dte INTEGER,                       -- Days to expiration (back)
    underlying_price NUMERIC(8,2),
    
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_symbol_time (symbol, captured_at),
    INDEX idx_violation (is_violation, captured_at)
);

-- Signal 2: Calendar Spread Opportunities
CREATE TABLE IF NOT EXISTS signal_calendar_opportunities (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots_0dte(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    
    -- Violation reference
    violation_id INTEGER REFERENCES signal_calendar_violations(id) ON DELETE SET NULL,
    
    -- Opportunity scoring (0.0 - 1.0)
    opportunity_score NUMERIC(6,4) NOT NULL,
    severity_score NUMERIC(6,4),            -- 0-1 based on violation severity
    theta_score NUMERIC(6,4),               -- 0-1 based on time to expiration
    iv_regime_score NUMERIC(6,4),           -- 0-1 based on absolute IV level
    momentum_score NUMERIC(6,4),            -- 0-1 based on trend
    confidence NUMERIC(6,4),                -- Overall confidence level
    
    -- Trade setup
    entry_signal VARCHAR(50),               -- "short_call_spread", "short_put_spread", "long_calendar"
    suggested_strike NUMERIC(7,2),          -- Recommended strike (ATM)
    suggested_quantity INTEGER DEFAULT 1,
    estimated_entry_cost NUMERIC(10,2),    -- Net debit or credit
    estimated_max_profit NUMERIC(10,2),    -- If term structure normalizes
    
    -- Trade timing
    optimal_hold_days INTEGER,              -- Days to maturity of front month
    days_to_roll INTEGER,                   -- Days until roll needed
    
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_symbol_score (symbol, opportunity_score DESC),
    INDEX idx_confidence (confidence DESC, captured_at)
);

-- Track open and closed calendar spread trades
CREATE TABLE IF NOT EXISTS calendar_spread_trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(36) UNIQUE NOT NULL,  -- UUID for linking all executions
    symbol VARCHAR(10) NOT NULL,
    
    -- Entry details
    entry_timestamp TIMESTAMP NOT NULL,
    entry_snapshot_id INTEGER REFERENCES snapshots_0dte(id),
    entry_opportunity_id INTEGER REFERENCES signal_calendar_opportunities(id),
    entry_price NUMERIC(10,2) NOT NULL,    -- Net debit (positive) or credit (negative)
    entry_reason VARCHAR(255),              -- Why we entered
    
    -- Position setup
    front_expiry DATE NOT NULL,
    back_expiry DATE NOT NULL,
    strike NUMERIC(7,2) NOT NULL,
    option_type VARCHAR(4) NOT NULL,       -- CALL or PUT
    quantity INTEGER DEFAULT 1,
    
    -- Entry Greeks (at entry time)
    delta_entry NUMERIC(8,6),
    gamma_entry NUMERIC(8,6),
    theta_entry_per_day NUMERIC(8,6),     -- Theta per day
    vega_entry NUMERIC(8,6),
    
    -- Position tracking (updated daily)
    current_price NUMERIC(10,2),
    current_pnl NUMERIC(12,2),
    current_pnl_pct NUMERIC(8,4),
    current_delta NUMERIC(8,6),
    current_theta_per_day NUMERIC(8,6),
    
    -- Exit details
    exit_timestamp TIMESTAMP,
    exit_snapshot_id INTEGER REFERENCES snapshots_0dte(id),
    exit_price NUMERIC(10,2),
    exit_reason VARCHAR(50),                -- "profit_target" | "stop_loss" | "time_decay" | "thesis_broken" | "max_hold"
    
    -- Exit Greeks (at exit time)
    delta_exit NUMERIC(8,6),
    gamma_exit NUMERIC(8,6),
    theta_exit_per_day NUMERIC(8,6),
    vega_exit NUMERIC(8,6),
    
    -- P&L metrics
    final_pnl NUMERIC(12,2),
    final_pnl_pct NUMERIC(8,4),
    max_profit_realized NUMERIC(12,2),    -- High water mark
    max_loss_realized NUMERIC(12,2),      -- Low water mark
    
    -- Duration metrics
    hold_duration_days NUMERIC(8,2),
    hold_duration_hours NUMERIC(8,2),
    
    -- Term structure context
    entry_iv_slope NUMERIC(6,4),            -- IV slope at entry
    exit_iv_slope NUMERIC(6,4),             -- IV slope at exit
    
    status VARCHAR(20) NOT NULL,            -- "open" | "closed" | "rolled"
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_symbol_status (symbol, status),
    INDEX idx_timestamp (entry_timestamp),
    INDEX idx_open (status, entry_timestamp)
);

-- Daily performance aggregation
CREATE TABLE IF NOT EXISTS calendar_spread_performance (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date_traded DATE NOT NULL,
    
    -- Trade counts
    trades_opened INTEGER DEFAULT 0,
    trades_closed INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    breakeven_trades INTEGER DEFAULT 0,
    
    -- P&L metrics
    total_pnl NUMERIC(12,2),
    avg_pnl_per_trade NUMERIC(10,2),
    median_pnl_per_trade NUMERIC(10,2),
    
    max_win NUMERIC(12,2),
    max_loss NUMERIC(12,2),
    
    -- Performance ratios
    win_rate NUMERIC(6,4),                  -- winning / total
    profit_factor NUMERIC(8,4),             -- sum(wins) / sum(losses)
    payoff_ratio NUMERIC(8,4),              -- avg_win / avg_loss
    
    -- Risk metrics
    sharpe_ratio NUMERIC(8,4),
    max_drawdown NUMERIC(8,4),
    
    -- Strategy metrics
    avg_hold_days NUMERIC(8,2),
    avg_theta_collected NUMERIC(10,2),
    
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (symbol, date_traded),
    INDEX idx_symbol (symbol)
);

-- Create composite index for common queries
CREATE INDEX IF NOT EXISTS idx_signals_by_symbol_time 
    ON signal_calendar_violations(symbol, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_opportunities_by_score
    ON signal_calendar_opportunities(symbol, opportunity_score DESC, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_trades_open_by_symbol
    ON calendar_spread_trades(symbol, status, entry_timestamp DESC);
