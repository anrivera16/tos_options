# Calendar Spread Implementation Checklist

## Overview
Everything you need to integrate calendar spreads into z0dte is in `/Users/arivera/projects/tos_options/`.

**Total Lines of Code Created:** ~1,000 lines (signals + strategy)
**Total Documentation:** ~45 KB (guides + examples)
**Estimated Integration Time:** 30 minutes

---

## Files You Have

### Documentation (Read First)
- [ ] **CALENDAR_SPREAD_INTEGRATION_SUMMARY.md** ← START HERE
  - 5-minute quick start
  - Configuration reference
  - Troubleshooting guide
  
- [ ] CALENDAR_SPREAD_FEATURE_PLAN.md
  - Full architecture and design
  - Database schema walkthrough
  - Phase-by-phase implementation

### Code (Ready to Integrate)
- [ ] `z0dte/signals/calendar_spread_violation.py` (280 lines)
  - Detects term structure inversions
  - Fully documented with docstrings

- [ ] `z0dte/signals/calendar_spread_opportunity.py` (392 lines)
  - Scores opportunities (0-1 scale)
  - Component-based weighting

- [ ] `z0dte/strategies/calendar_spread_strategy.py` (366 lines)
  - Entry/hold/exit logic
  - Position tracking

### Database
- [ ] `z0dte/db/migrations/001_add_calendar_spreads.sql` (160 lines)
  - 4 new tables
  - Indexes for fast queries

### Documentation (Implementation)
- [ ] `z0dte/docs/06_calendar_spreads.md`
  - Data flow explanation
  - SQL queries for monitoring
  - Next steps

---

## Integration Steps (In Order)

### Step 1: Database Setup (5 minutes)
- [ ] Run: `psql tos_0dte < z0dte/db/migrations/001_add_calendar_spreads.sql`
- [ ] Verify: `psql tos_0dte -c "SELECT COUNT(*) FROM signal_calendar_violations;"`
  - Should return: `count: 0` (empty, which is correct)

### Step 2: Register Signals in Pipeline (10 minutes)
- [ ] Open: `z0dte/ingestion/pipeline.py`
- [ ] Add imports:
  ```python
  from z0dte.signals.calendar_spread_violation import CalendarSpreadViolation
  from z0dte.signals.calendar_spread_opportunity import CalendarSpreadOpportunity
  ```
- [ ] Add to SIGNALS list:
  ```python
  CalendarSpreadViolation(),
  CalendarSpreadOpportunity(),
  ```
- [ ] Save file

### Step 3: Register Strategy (5 minutes)
- [ ] Open: `z0dte/strategies/__init__.py`
- [ ] Add import:
  ```python
  from z0dte.strategies.calendar_spread_strategy import CalendarSpreadStrategy
  ```
- [ ] Add to STRATEGIES dict:
  ```python
  "calendar_spread": CalendarSpreadStrategy(),
  ```
- [ ] Save file

### Step 4: Add to Backtest Config (5 minutes)
- [ ] Open: `z0dte/backtest/pm1_backtest.py`
- [ ] Find line: `strategies_to_run = ["0dte"]`
- [ ] Change to: `strategies_to_run = ["calendar_spread"]`
- [ ] Or to run both: `strategies_to_run = ["0dte", "calendar_spread"]`
- [ ] Save file

### Step 5: Test Integration (5 minutes)
- [ ] Run: `python z0dte/backtest/pm1_backtest.py --help`
- [ ] Should see strategy options (including calendar_spread if registered)
- [ ] If errors, check Step 2-4 above

---

## First Backtest (10 minutes)

### Option A: Quick Test (1 day of data)
```bash
# If you have a sample CSV:
python z0dte/backtest/pm1_backtest.py \
  --symbol SPX \
  --data data/2026-04-08.csv \
  --strategy calendar_spread
```

### Option B: Full Month Test
```bash
python z0dte/backtest/pm1_backtest.py \
  --symbol SPX \
  --data data/2026-04.csv \
  --strategy calendar_spread
```

### Option C: Both Strategies
```bash
python z0dte/backtest/pm1_backtest.py \
  --symbol SPX \
  --data data/2026-04.csv
```

### Check Results
```bash
# Query trades in database
psql tos_0dte -c "
  SELECT COUNT(*) as total_trades,
         COUNT(CASE WHEN status='closed' THEN 1 END) as closed,
         ROUND(AVG(CASE WHEN final_pnl > 0 THEN 1 ELSE 0 END)::numeric * 100, 1) as win_rate_pct
  FROM calendar_spread_trades;
"
```

---

## Customization (Optional)

### Adjust Entry Threshold
**File:** `z0dte/strategies/calendar_spread_strategy.py`
**Line:** ~40
```python
OPPORTUNITY_THRESHOLD = 0.60  # Change this value
# Lower = more trades, fewer filters
# Higher = fewer trades, only best setups
```

### Adjust Exit Conditions
**File:** `z0dte/strategies/calendar_spread_strategy.py`
**Lines:** ~40-50
```python
PROFIT_TARGET_PCT = 0.35      # Exit at 35% profit
HOLD_TIME_DAYS = 7            # Exit after 7 days
STOP_LOSS_PCT = 0.15          # Exit if loss > 15%
MAX_HOLD_DAYS = 25            # Never hold > 25 days
```

### Adjust Scoring Weights
**File:** `z0dte/signals/calendar_spread_opportunity.py`
**Lines:** ~190-195
```python
opportunity_score = (
    0.35 * severity_score +    # Change weights here
    0.30 * theta_score +
    0.20 * iv_regime_score +
    0.15 * momentum_score
)
```

---

## Verification Checkpoints

### After Step 1 (Database)
```bash
psql tos_0dte -c "
  SELECT table_name FROM information_schema.tables 
  WHERE table_name LIKE 'signal_calendar%' OR table_name LIKE 'calendar_spread%';
"
```
Should list 4 new tables.

### After Step 2-4 (Code Integration)
```bash
python -c "
  from z0dte.signals.calendar_spread_violation import CalendarSpreadViolation
  from z0dte.signals.calendar_spread_opportunity import CalendarSpreadOpportunity
  from z0dte.strategies.calendar_spread_strategy import CalendarSpreadStrategy
  print('✓ All imports successful')
"
```

### After Step 5 (Backtest)
```bash
psql tos_0dte -c "
  SELECT COUNT(*) as trades_detected 
  FROM calendar_spread_trades 
  WHERE status = 'open' OR status = 'closed';
"
```
Should show > 0 if backtest ran successfully.

---

## Monitoring Queries

### See All Open Positions
```sql
SELECT trade_id, entry_timestamp, entry_price, current_pnl, current_pnl_pct
FROM calendar_spread_trades
WHERE status = 'open'
ORDER BY entry_timestamp DESC;
```

### See Closed Trades with P&L
```sql
SELECT trade_id, entry_timestamp, exit_timestamp, 
       entry_price, exit_price, final_pnl, final_pnl_pct, exit_reason
FROM calendar_spread_trades
WHERE status = 'closed'
ORDER BY entry_timestamp DESC;
```

### See Daily Performance
```sql
SELECT date_traded, trades_opened, trades_closed, winning_trades,
       total_pnl, win_rate, profit_factor
FROM calendar_spread_performance
WHERE symbol = 'SPX'
ORDER BY date_traded DESC;
```

### See Opportunities Being Detected
```sql
SELECT captured_at, opportunity_score, confidence, suggested_strike,
       estimated_entry_cost, estimated_max_profit
FROM signal_calendar_opportunities
WHERE symbol = 'SPX'
ORDER BY captured_at DESC
LIMIT 10;
```

### See Violations in Real-Time
```sql
SELECT captured_at, front_expiry, front_atm_iv, back_expiry, back_atm_iv,
       iv_slope, violation_severity, is_violation
FROM signal_calendar_violations
WHERE symbol = 'SPX'
ORDER BY captured_at DESC
LIMIT 10;
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'z0dte.signals.calendar_spread_violation'"
**Fix:** Ensure Step 2 (register signals in pipeline.py) is complete.

### "No violations detected / No opportunities being traded"
**Check:**
1. Is your CSV data valid? (Has expiration_date, strike, volatility columns)
2. Are there 2+ expirations in the data?
3. Is there actual term structure inversion? (front_iv > back_iv)
4. Lower OPPORTUNITY_THRESHOLD to 0.50 to see more trades

### "Trades open but not closing"
**Check:**
1. Run the SQL query above to see open trades
2. Check current P&L: is it >35%? (profit target condition)
3. Check hold duration: >7 days? (hold time condition)
4. Check if violation reversed: is iv_slope now positive?

### "Database error: relation does not exist"
**Fix:** Re-run Step 1: `psql tos_0dte < z0dte/db/migrations/001_add_calendar_spreads.sql`

---

## What's Next (After Integration)

### Week 2: Backtest & Optimize
- [ ] Run backtest on 1 month of data
- [ ] Review CALENDAR_SPREAD_INTEGRATION_SUMMARY.md for expected performance
- [ ] Adjust thresholds if needed (OPPORTUNITY_THRESHOLD, PROFIT_TARGET_PCT, etc.)
- [ ] Check win rate and profit factor in calendar_spread_performance

### Week 3: Live Paper Trading (Optional)
- [ ] Modify pipeline.py to use LiveDataSource instead of CSVDataSource
- [ ] Run in paper trading mode (no real capital)
- [ ] Monitor fills and execution quality
- [ ] Record notes on what works and what doesn't

### Week 4: Phase 2 (Optional Enhancements)
- [ ] Multi-leg order execution (integrate with Schwab API)
- [ ] Automatic rolling logic (4 days before front expiry)
- [ ] Greeks tracking and rebalancing
- [ ] Multiple spread types (put spreads, long calendars, etc.)

---

## Key Files to Understand

**For quick answers:**
- CALENDAR_SPREAD_INTEGRATION_SUMMARY.md (config, examples, FAQ)
- z0dte/docs/06_calendar_spreads.md (implementation details)

**For code deep-dives:**
- z0dte/signals/calendar_spread_violation.py (start here — simpler)
- z0dte/signals/calendar_spread_opportunity.py (scoring logic)
- z0dte/strategies/calendar_spread_strategy.py (entry/exit logic)

**For database:**
- z0dte/db/migrations/001_add_calendar_spreads.sql (schema)
- SQL queries above (monitoring)

---

## Support

**Questions about:**
- Integration steps → CALENDAR_SPREAD_INTEGRATION_SUMMARY.md (Quick Start section)
- How it works → z0dte/docs/06_calendar_spreads.md (Data Flow section)
- Configuration → Look for the config section at top of each file (OPPORTUNITY_THRESHOLD, etc.)
- Troubleshooting → CALENDAR_SPREAD_INTEGRATION_SUMMARY.md (Troubleshooting section)

---

**You're ready to integrate. Start with Step 1 above!** 🚀
