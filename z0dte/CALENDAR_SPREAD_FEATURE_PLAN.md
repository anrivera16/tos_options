# Calendar Spread Feature Integration

## Overview

Add calendar spread detection, tracking, and execution to the existing z0dte system.

**Why it fits:**
- Your IVTermStructure signal already computes front/back vol slopes
- You have multi-expiration options data
- Your strategy framework is abstraction-ready
- Calendar spreads trade on term structure violations (your data is perfect for this)

---

## What We're Adding

### 1. New Signals
- **TermStructureViolation**: Detect when front-month IV > back-month IV (backwards)
- **CalendarSpreadOpportunity**: Identify good entry/exit points
- **TermStructureMomentum**: Track steepening/flattening velocity

### 2. New Strategy
- **CalendarSpreadStrategy**: Trade violations when detected

### 3. New Database Tables
- `signal_calendar_opportunities` — detected spread setups
- `calendar_spread_trades` — opened positions + P&L tracking
- `calendar_spread_executions` — historical trades + performance

### 4. Integration Points
- Consume IVTermStructure signal (reuse!)
- Multi-leg order placement (extend strategy.evaluate)
- Position tracking (Greeks, P&L, hold time)

---

## File Structure

```
z0dte/
  signals/
    calendar_spread_violation.py     # Signal 1: Term structure inversion
    calendar_spread_opportunity.py   # Signal 2: Entry/exit scoring
    calendar_term_momentum.py        # Signal 3: Slope acceleration
  
  strategies/
    calendar_spread_strategy.py      # Calendar spread trading logic
  
  db/
    migrations/
      001_add_calendar_spreads.sql   # Schema additions
  
  docs/
    06_calendar_spreads.md           # Full implementation guide
  
  tests/
    test_calendar_signals.py
    test_calendar_strategy.py
```

---

## Database Schema Additions

```sql
CREATE TABLE signal_calendar_violations (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots_0dte(id),
    symbol VARCHAR(10) NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    
    -- Term structure data
    front_expiry DATE NOT NULL,
    front_atm_iv NUMERIC(6,4),
    back_expiry DATE NOT NULL,
    back_atm_iv NUMERIC(6,4),
    
    -- Violation metrics
    iv_slope NUMERIC(6,4),              -- front_iv - back_iv (NEGATIVE = violation)
    violation_severity NUMERIC(6,4),    -- How inverted (lower = more inverted)
    is_violation BOOLEAN,               -- Crosses threshold
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE signal_calendar_opportunities (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots_0dte(id),
    symbol VARCHAR(10) NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    
    -- Opportunity scoring
    opportunity_score NUMERIC(6,4),     -- 0-1, higher = better entry
    entry_signal VARCHAR(50),           -- "short_call_spread", "short_put_spread", etc.
    confidence NUMERIC(6,4),            -- Based on vol regime, theta, etc.
    
    -- Trade setup suggestion
    suggested_strike_front INTEGER,
    suggested_strike_back INTEGER,
    suggested_size INTEGER,
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE calendar_spread_trades (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    trade_id VARCHAR(32) UNIQUE,        -- UUID for linking executions
    
    -- Entry
    entry_timestamp TIMESTAMP NOT NULL,
    entry_snapshot_id INTEGER REFERENCES snapshots_0dte(id),
    entry_price NUMERIC(8,2),           -- Net debit/credit
    
    -- Setup
    front_expiry DATE NOT NULL,
    back_expiry DATE NOT NULL,
    strike INTEGER NOT NULL,
    option_type VARCHAR(4),             -- CALL, PUT
    quantity INTEGER DEFAULT 1,
    
    -- Greeks at entry
    delta_entry NUMERIC(8,6),
    gamma_entry NUMERIC(8,6),
    theta_entry NUMERIC(8,6),
    vega_entry NUMERIC(8,6),
    
    -- Position tracking
    current_price NUMERIC(8,2),
    current_pnl NUMERIC(10,2),
    current_pnl_pct NUMERIC(8,4),
    
    exit_timestamp TIMESTAMP,           -- NULL if still open
    exit_price NUMERIC(8,2),
    exit_snapshot_id INTEGER REFERENCES snapshots_0dte(id),
    
    exit_reason VARCHAR(50),            -- "profit_target", "stop_loss", "theta_target", "expiration"
    final_pnl NUMERIC(10,2),
    final_pnl_pct NUMERIC(8,4),
    
    hold_duration_minutes INTEGER,      -- (exit_time - entry_time) / 60
    
    status VARCHAR(20),                 -- "open", "closed", "rolled"
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE calendar_spread_performance (
    symbol VARCHAR(10) NOT NULL,
    date_traded DATE NOT NULL,
    
    trades_opened INTEGER DEFAULT 0,
    trades_closed INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    
    total_pnl NUMERIC(12,2),
    avg_pnl_per_trade NUMERIC(10,2),
    win_rate NUMERIC(6,4),              -- winning / total
    profit_factor NUMERIC(8,4),         -- wins / losses
    
    sharpe_ratio NUMERIC(8,4),
    max_drawdown NUMERIC(8,4),
    
    PRIMARY KEY (symbol, date_traded)
);
```

---

## Signal 1: Term Structure Violation Detector

```python
# z0dte/signals/calendar_spread_violation.py

class CalendarSpreadViolation(Signal):
    """
    Detect when front-month IV > back-month IV (inverted term structure).
    
    Calendar spreads profit when this normalizes:
    - You SHORT the expensive front month
    - You LONG the cheaper back month
    - As time passes and the vol structure normalizes, you profit
    """
    
    name = "calendar_spread_violation"
    table = "signal_calendar_violations"
    
    # A term structure violation is when near-term vol is >50 bps 
    # higher than back-term vol
    VIOLATION_THRESHOLD = 0.005  # 50 bps
    
    def compute(self, snapshot_id: int, db_conn: Any) -> None:
        """
        For each snapshot, check if term structure is inverted.
        Store the degree of inversion.
        """
        contracts = self._load_contracts(snapshot_id, db_conn)
        snapshot = self._load_snapshot(snapshot_id, db_conn)
        
        # Use existing IV term structure computation
        expiry_pair = self._get_expiry_pair(contracts)
        if not expiry_pair:
            return
        
        front_exp, back_exp = expiry_pair
        atm_strike = self._find_atm_strike(contracts, snapshot["underlying_price"])
        
        front_iv = self._extract_atm_iv(contracts, front_exp, atm_strike)
        back_iv = self._extract_atm_iv(contracts, back_exp, atm_strike)
        
        if not front_iv or not back_iv:
            return
        
        # Compute violation severity
        iv_slope = front_iv - back_iv  # Negative = violation
        is_violation = iv_slope < -self.VIOLATION_THRESHOLD
        violation_severity = abs(iv_slope) if is_violation else 0.0
        
        # Store in database
        db_conn.execute(
            """
            INSERT INTO signal_calendar_violations
                (snapshot_id, symbol, captured_at,
                 front_expiry, front_atm_iv,
                 back_expiry, back_atm_iv,
                 iv_slope, violation_severity, is_violation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                snapshot_id, snapshot["symbol"], snapshot["captured_at"],
                front_exp, front_iv,
                back_exp, back_iv,
                iv_slope, violation_severity, is_violation
            ]
        )
        db_conn.commit()
```

---

## Signal 2: Calendar Spread Opportunity Scorer

```python
# z0dte/signals/calendar_spread_opportunity.py

class CalendarSpreadOpportunity(Signal):
    """
    Score the quality of a calendar spread entry.
    
    Factors:
    1. Degree of term structure violation (higher = better)
    2. Theta availability (how much time decay you'll collect)
    3. Implied vol regime (low vol = safer short)
    4. Days to expiration (30-60 DTE optimal)
    5. Momentum (is inversion getting worse or improving?)
    """
    
    name = "calendar_spread_opportunity"
    table = "signal_calendar_opportunities"
    
    def compute(self, snapshot_id: int, db_conn: Any) -> None:
        """
        Compute opportunity score (0-1 scale).
        Higher score = better entry point.
        """
        contracts = self._load_contracts(snapshot_id, db_conn)
        snapshot = self._load_snapshot(snapshot_id, db_conn)
        
        # Get prior violation data
        prior_violation = self._get_prior_violation(snapshot, db_conn)
        current_violation = self._get_current_violation(snapshot, db_conn)
        
        if not current_violation:
            return
        
        # Component 1: Violation severity (0-1)
        # Max profitable violation is ~150 bps
        severity_score = min(current_violation["violation_severity"] / 0.015, 1.0)
        
        # Component 2: Theta accumulation potential
        # Compute expected theta based on time to expiry
        theta_score = self._compute_theta_score(
            contracts,
            current_violation["front_expiry"],
            current_violation["back_expiry"]
        )
        
        # Component 3: IV regime (lower vol = safer)
        iv_regime_score = self._compute_iv_regime_score(
            current_violation["front_atm_iv"],
            current_violation["back_atm_iv"]
        )
        
        # Component 4: Inversion momentum
        momentum_score = self._compute_momentum_score(
            current_violation["iv_slope"],
            prior_violation["iv_slope"] if prior_violation else None
        )
        
        # Weighted combination
        opportunity_score = (
            0.35 * severity_score +
            0.30 * theta_score +
            0.20 * iv_regime_score +
            0.15 * momentum_score
        )
        
        # Determine confidence
        confidence = self._compute_confidence(
            opportunity_score,
            current_violation,
            prior_violation
        )
        
        # Suggest entry strike (ATM is safest)
        entry_strike = self._find_atm_strike(contracts, snapshot["underlying_price"])
        
        # Store opportunity
        db_conn.execute(
            """
            INSERT INTO signal_calendar_opportunities
                (snapshot_id, symbol, captured_at,
                 opportunity_score, entry_signal, confidence,
                 suggested_strike_front, suggested_strike_back, suggested_size)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                snapshot_id, snapshot["symbol"], snapshot["captured_at"],
                opportunity_score, "short_call_spread", confidence,
                entry_strike, entry_strike, 1
            ]
        )
        db_conn.commit()
```

---

## Strategy: Calendar Spread Trader

```python
# z0dte/strategies/calendar_spread_strategy.py

from z0dte.strategies.base import Strategy

class CalendarSpreadStrategy(Strategy):
    """
    Trade calendar spreads based on term structure violations.
    
    Entry Rules:
    1. Is there a term structure violation? (front IV > back IV + threshold)
    2. Is the opportunity score high enough? (> 0.6)
    3. Do we have capital available?
    
    Exit Rules:
    1. Profit target: 20-50% of max profit
    2. Time decay: Hold for 5-10 days if profitable
    3. Stop loss: If inversion reverses + spreads widen
    4. Maximum hold: 30 days before roll
    
    Position Management:
    - Track Greeks (especially theta and vega)
    - Monitor P&L daily
    - Roll forward if needed
    """
    
    name = "calendar_spread_strategy"
    
    # Configuration
    OPPORTUNITY_THRESHOLD = 0.60
    CAPITAL_PER_TRADE = 5000  # Risk $5K per position
    PROFIT_TARGET_PCT = 0.25  # 25% of entry cost
    HOLD_TIME_DAYS = 7
    MAX_HOLD_DAYS = 30
    
    def evaluate(self, snapshot_id: int, db_conn: Any) -> dict:
        """
        Evaluate if we should open a calendar spread trade.
        
        Returns:
            {
                "action": "OPEN" | "HOLD" | "CLOSE" | "NONE",
                "signal_score": float,
                "position_id": str (if OPEN),
                "reason": str
            }
        """
        snapshot = self._load_snapshot(snapshot_id, db_conn)
        
        # Check for open positions (are we already positioned?)
        open_positions = self._get_open_positions(snapshot["symbol"], db_conn)
        if open_positions:
            # Evaluate exit for existing positions
            return self._evaluate_exits(open_positions, snapshot, db_conn)
        
        # Check for new entry opportunities
        opportunity = self._get_latest_opportunity(snapshot["symbol"], snapshot["captured_at"], db_conn)
        
        if not opportunity:
            return {"action": "NONE", "reason": "No opportunity signal"}
        
        if opportunity["opportunity_score"] < self.OPPORTUNITY_THRESHOLD:
            return {
                "action": "NONE",
                "reason": f"Score too low: {opportunity['opportunity_score']:.2f} < {self.OPPORTUNITY_THRESHOLD}"
            }
        
        # All conditions met for entry
        return {
            "action": "OPEN",
            "signal_score": opportunity["opportunity_score"],
            "reason": "Term structure violation + high opportunity",
            "trade_params": {
                "strike": opportunity["suggested_strike_front"],
                "front_expiry": opportunity["front_expiry"],
                "back_expiry": opportunity["back_expiry"],
                "quantity": opportunity["suggested_size"],
                "price": self._estimate_entry_price(opportunity, snapshot)
            }
        }
    
    def _evaluate_exits(self, open_positions: list[dict], snapshot: dict, db_conn: Any) -> dict:
        """
        Decide whether to close existing positions.
        """
        for position in open_positions:
            # Calculate current P&L
            current_pnl = self._estimate_current_pnl(position, snapshot, db_conn)
            hold_time = (snapshot["captured_at"] - position["entry_timestamp"]).days
            
            # Exit condition 1: Profit target hit
            if current_pnl > position["entry_price"] * self.PROFIT_TARGET_PCT:
                return {
                    "action": "CLOSE",
                    "position_id": position["id"],
                    "reason": f"Profit target hit: {current_pnl:.0f}",
                    "exit_price": self._estimate_exit_price(position, snapshot, db_conn)
                }
            
            # Exit condition 2: Hold time reached
            if hold_time >= self.HOLD_TIME_DAYS:
                return {
                    "action": "CLOSE",
                    "position_id": position["id"],
                    "reason": f"Hold time reached: {hold_time} days",
                    "exit_price": self._estimate_exit_price(position, snapshot, db_conn)
                }
            
            # Exit condition 3: Stop loss (violation reverses)
            violation = self._get_latest_violation(
                snapshot["symbol"],
                snapshot["captured_at"],
                db_conn
            )
            if violation["iv_slope"] > 0:  # Inversion reversed
                return {
                    "action": "CLOSE",
                    "position_id": position["id"],
                    "reason": "Term structure reversed (stop loss)",
                    "exit_price": self._estimate_exit_price(position, snapshot, db_conn)
                }
        
        return {"action": "HOLD", "reason": "Position monitoring"}
```

---

## Implementation Steps

### Phase 1: Database + Signals (Week 1)
- [ ] Create migration file: `001_add_calendar_spreads.sql`
- [ ] Implement `CalendarSpreadViolation` signal
- [ ] Implement `CalendarSpreadOpportunity` signal
- [ ] Test on 1 week of historical data
- [ ] Verify PostgreSQL writes and queries

### Phase 2: Strategy (Week 2)
- [ ] Implement `CalendarSpreadStrategy`
- [ ] Add multi-leg order placement to strategy.evaluate()
- [ ] Implement position tracking (P&L, Greeks, hold time)
- [ ] Test exit logic on historical data

### Phase 3: Integration (Week 3)
- [ ] Add calendar spreads to `pipeline.py` (compute signals)
- [ ] Add calendar spread strategy to live runner
- [ ] Add calendar spread dashboard metrics
- [ ] Backtest: full month of data

### Phase 4: Live Deployment (Week 4)
- [ ] Paper trading with Schwab API
- [ ] Monitor for 2 weeks
- [ ] Deploy to production with safeguards

---

## Key Advantages Over 0DTE

| Aspect | 0DTE | Calendar Spread |
|--------|------|-----------------|
| **Gamma Risk** | Extreme (high leverage) | Low (defined-risk spreads) |
| **Theta Decay** | Intraday (fast profit) | Daily (steady profit) |
| **Holding Time** | Minutes to 2h | Days to weeks |
| **Capital Efficiency** | High (100% returns possible) | Medium (15-50% returns) |
| **Frequency** | 15-20 trades/day | 3-10 trades/week |
| **Risk/Reward** | Very High / Very High | Medium / Medium |
| **Best Conditions** | Calm markets, range-bound | Stable vol regimes |

---

## Testing the Integration

```python
# tests/test_calendar_spread_strategy.py

def test_violation_detector_on_sample_csv():
    """Load sample CSV with known inversion, verify detection."""
    
    # Load CSV with front_iv=17.3%, back_iv=16.8% (50 bps inversion)
    contracts = load_sample_csv("test_calendar_inversion.csv")
    
    # Compute signal
    violation = CalendarSpreadViolation.compute(contracts)
    
    assert violation["is_violation"] == True
    assert violation["violation_severity"] > 0.004
    assert violation["iv_slope"] < -0.005

def test_opportunity_scorer():
    """Test opportunity score calculation."""
    
    opportunity = CalendarSpreadOpportunity.compute(
        violation_severity=0.010,
        theta_days=7,
        iv_level=0.15,
        momentum="negative"  # Getting worse
    )
    
    # Should score well
    assert opportunity["opportunity_score"] > 0.65
    
def test_strategy_entry_exit_cycle():
    """Backtest a full entry-to-exit cycle."""
    
    # Entry: Sell 30 DTE call spread (term structure violation)
    entry = strategy.evaluate(entry_snapshot)
    assert entry["action"] == "OPEN"
    
    # Hold for 5 days
    hold_positions = [entry for _ in range(5)]
    
    # Exit: Profit target hit
    exit = strategy.evaluate(exit_snapshot_after_5_days)
    assert exit["action"] == "CLOSE"
    assert exit["reason"] == "Profit target hit"
```

---

## Success Metrics

After 1 month of paper trading:

| Metric | Target |
|--------|--------|
| **Win Rate** | >60% |
| **Profit Factor** | >2.0 |
| **Avg Return / Trade** | 15-30% |
| **Max Drawdown** | <15% |
| **Sharpe Ratio** | >1.0 |
| **Trades / Week** | 3-10 |

---

## Files to Create/Modify

### New Files
```
z0dte/signals/calendar_spread_violation.py
z0dte/signals/calendar_spread_opportunity.py
z0dte/signals/calendar_term_momentum.py       (optional)
z0dte/strategies/calendar_spread_strategy.py
z0dte/db/migrations/001_add_calendar_spreads.sql
z0dte/docs/06_calendar_spreads.md
z0dte/tests/test_calendar_signals.py
z0dte/tests/test_calendar_strategy.py
```

### Files to Modify
```
z0dte/ingestion/pipeline.py                   (add signal registration)
z0dte/backtest/pm1_backtest.py                (add strategy)
z0dte/signals/__init__.py                     (register signals)
z0dte/strategies/__init__.py                  (register strategy)
```

---

## Next Steps

1. **Review this plan** — Does it fit your architecture?
2. **Start with Phase 1** — Get the database + signals working first
3. **Test on historical data** — See if the violations were real
4. **Implement Phase 2** — Add the strategy
5. **Backtest full month** — Measure performance

Ready to build? I can write the actual code for Phase 1 if you want.
