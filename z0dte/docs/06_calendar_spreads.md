# Calendar Spread Signals and Strategy

## Quick Start

### 1. Apply Database Migration
```bash
psql tos_0dte < z0dte/db/migrations/001_add_calendar_spreads.sql
```

This creates:
- `signal_calendar_violations` — detects inverted term structures
- `signal_calendar_opportunities` — scores trade quality
- `calendar_spread_trades` — tracks position P&L
- `calendar_spread_performance` — aggregates daily stats

### 2. Register Signals in Pipeline
Edit `z0dte/ingestion/pipeline.py`:

```python
from z0dte.signals import (
    IVTermStructure,
    CalendarSpreadViolation,
    CalendarSpreadOpportunity,
)

SIGNALS = [
    IVTermStructure(),
    CalendarSpreadViolation(),
    CalendarSpreadOpportunity(),
    # ... other signals
]
```

### 3. Register Strategy
Edit `z0dte/strategies/__init__.py`:

```python
from z0dte.strategies.calendar_spread_strategy import CalendarSpreadStrategy

STRATEGIES = {
    "calendar_spread": CalendarSpreadStrategy(),
    # ... other strategies
}
```

### 4. Add to Backtest
Edit `z0dte/backtest/pm1_backtest.py`:

```python
strategies_to_run = ["calendar_spread", "0dte"]
```

---

## How It Works

### Data Flow

```
Every 15 minutes (live) or every snapshot (backtest):

1. CalendarSpreadViolation.compute()
   → Detects if front_iv > back_iv (inverted term structure)
   → Stores: iv_slope, violation_severity, is_violation
   
2. CalendarSpreadOpportunity.compute()
   → Reads violation from signal_calendar_violations
   → Scores: severity, theta, iv_regime, momentum
   → Stores: opportunity_score, confidence, trade suggestion
   
3. CalendarSpreadStrategy.evaluate()
   → Checks for open positions (any?)
   → If no position: Reads opportunity_score
     → If score > 0.60 AND confidence > 0.55: OPEN
   → If position open: Evaluates exit conditions
     → Profit target (35%)? CLOSE
     → Hold time (7 days)? CLOSE
     → Stop loss (-15%)? CLOSE
     → Thesis broken (slope reversed)? CLOSE
```

### Example: A Complete Trade Cycle

**2026-04-08 10:00 AM**
- SPX = 5432
- Front (30 DTE) IV: 17.3%
- Back (60 DTE) IV: 16.8%
- **IV Slope: +50 bps INVERTED** ✓
- CalendarSpreadViolation stores this

**2026-04-08 10:15 AM**
- CalendarSpreadOpportunity scores:
  - Severity: 0.80 (good inversion)
  - Theta: 0.90 (perfect 30 DTE timing)
  - IV Regime: 0.75 (17% IV is safe)
  - Momentum: 0.85 (getting worse - good!)
  - **Overall Score: 0.81** (high confidence)

**2026-04-08 10:30 AM**
- CalendarSpreadStrategy: **"OPEN"**
- Entry: Sell 30 DTE 5430 Call Spread
- Entry Price: $2.00 debit
- Target Profit: $0.70 (35% of $2.00)
- Hold Until: 7 days or profit target

**2026-04-08 11:00 AM**
- Front IV falls to 17.1% (term structure normalizing)
- Current spread price: $1.80
- **P&L: +$0.20 (10% profit)**
- Status: HOLD

**2026-04-08 14:00 PM**
- Front IV falls to 16.9%
- Back IV stable at 16.8%
- Current spread price: $1.30
- **P&L: +$0.70 (35% profit)** ✓
- CalendarSpreadStrategy: **"CLOSE"** (profit target hit)
- Exit: Sell to close at $1.30
- **Trade Result: +$0.70 profit**

---

## Configuration

### CalendarSpreadViolation Signal
```python
# signals/calendar_spread_violation.py

VIOLATION_THRESHOLD = 0.005      # 50 basis points
SEVERITY_SCALE = 0.015           # 150 basis points max

# A violation occurs when: front_iv - back_iv < -VIOLATION_THRESHOLD
```

### CalendarSpreadOpportunity Signal
```python
# signals/calendar_spread_opportunity.py

# Weighting of component scores:
# severity (35%) + theta (30%) + iv_regime (20%) + momentum (15%) = score
```

### CalendarSpreadStrategy
```python
# strategies/calendar_spread_strategy.py

OPPORTUNITY_THRESHOLD = 0.60      # Min score to enter (0-1)
CONFIDENCE_THRESHOLD = 0.55       # Min confidence
CAPITAL_PER_TRADE = 5000          # USD risk per position
PROFIT_TARGET_PCT = 0.35          # Exit at 35% profit
HOLD_TIME_DAYS = 7                # Target hold
MAX_HOLD_DAYS = 25                # Don't hold > 25 days
STOP_LOSS_PCT = 0.15              # Exit if loss > 15%
```

---

## Testing

### Unit Tests
```bash
pytest z0dte/tests/test_calendar_signals.py
pytest z0dte/tests/test_calendar_strategy.py
```

### Backtest on CSV Data
```python
from z0dte.sources.csv_loader import CSVDataSource
from z0dte.ingestion.pipeline import Pipeline

# Load CSV with options data
source = CSVDataSource("data/2026-04-08_spx.csv")
pipeline = Pipeline(source=source)

# Run signals and strategy
pipeline.process_full_day()

# Query results
db_conn.execute("SELECT * FROM calendar_spread_trades WHERE status = 'closed'")
```

### Check Performance
```sql
-- Daily stats
SELECT * FROM calendar_spread_performance 
WHERE symbol = 'SPX' 
ORDER BY date_traded DESC;

-- Trade details
SELECT trade_id, entry_timestamp, exit_timestamp, 
       entry_price, exit_price, final_pnl, final_pnl_pct
FROM calendar_spread_trades
WHERE symbol = 'SPX'
ORDER BY entry_timestamp DESC;

-- Current open positions
SELECT * FROM calendar_spread_trades
WHERE symbol = 'SPX' AND status = 'open';
```

---

## Expected Results

After running on 1 month of historical data:

| Metric | Target |
|--------|--------|
| Win Rate | >60% |
| Profit Factor | >2.0 |
| Avg Trade | 15-30% |
| Max Drawdown | <15% |
| Sharpe Ratio | >1.0 |

---

## Troubleshooting

### No Violations Detected
- Check that your options data has multiple expirations
- Verify IV data is present (volatility field populated)
- Check that term structure inversion threshold matches your market

### Low Opportunity Scores
- Check IV regime score (is IV too high >35%?)
- Check theta score (is front month too short <10 DTE or >70 DTE?)
- Review violation severity (is inversion small <20 bps?)

### Positions Not Closing
- Check database connection (are updates committing?)
- Verify exit conditions in `_evaluate_exit()`
- Check that current prices are being estimated correctly

---

## Next Steps

### Phase 2: Multi-Leg Execution
- Integrate with Schwab API
- Send multi-leg orders: (short 30 DTE call) + (long 60 DTE call)
- Track fills and partial executions

### Phase 3: Greeks Management
- Compute current position Greeks
- Track delta/gamma/theta over position lifecycle
- Add rebalancing logic if position drifts

### Phase 4: Advanced Features
- Automatic roll logic (4 days before front expiry)
- Spread-specific IV forecasting
- Correlation with broader strategies

---

## Architecture Notes

### Why This Design Works with Your Existing System

1. **Signal Independence** — CalendarSpreadViolation and CalendarSpreadOpportunity are self-contained. They don't depend on 0DTE logic.

2. **Reuses IVTermStructure** — Your existing signal computes front/back IV pairs. Calendar spreads leverage this.

3. **Same DataSource Abstraction** — Works identically with live Schwab API or backtestCSVs.

4. **Strategy Pattern** — CalendarSpreadStrategy follows your existing Strategy ABC interface.

5. **PostgreSQL Single Source of Truth** — All signals and trades persist in your DB. Live and backtest use the same schema.

---

## Files Changed/Added

### New Files
```
z0dte/signals/calendar_spread_violation.py       (400 lines)
z0dte/signals/calendar_spread_opportunity.py     (470 lines)
z0dte/strategies/calendar_spread_strategy.py     (400 lines)
z0dte/db/migrations/001_add_calendar_spreads.sql (160 lines)
z0dte/docs/06_calendar_spreads.md               (this file)
z0dte/tests/test_calendar_signals.py             (TBD)
z0dte/tests/test_calendar_strategy.py            (TBD)
```

### Modified Files
```
z0dte/ingestion/pipeline.py          (+2 lines: register signals)
z0dte/strategies/__init__.py          (+2 lines: register strategy)
z0dte/backtest/pm1_backtest.py        (+1 line: add strategy to run)
```

---

## Questions?

1. **How do I adjust the entry threshold?**
   → Change `OPPORTUNITY_THRESHOLD` in `calendar_spread_strategy.py`

2. **How do I trade different calendar spread types?**
   → Modify `entry_signal` selection in `_evaluate_entry()`
   → Create separate signals for different spread types

3. **Can I use this with live Schwab data?**
   → Yes! The signals work with any DataSource. Just use `LiveDataSource` instead of `CSVDataSource` in your pipeline.

4. **How do I backtest with my own CSV data?**
   → Ensure CSV has columns: `expiration_date`, `strike`, `volatility`, etc.
   → Feed to `CSVDataSource` and let the pipeline handle the rest.
