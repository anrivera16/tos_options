# Feature Ideas & Edge Opportunities

> Generated from scraper code review — June 2026
> All items leverage existing Schwab API data or small incremental scrapes. Zero API cost unless noted.

---

## Currently Scraped (baseline)

**From Schwab Option Chains (every 5 min, SPY/QQQ/SPX + dynamic tickers):**
- Core pricing: bid, ask, last, mark
- Greeks: delta, gamma, theta, vega
- Implied volatility, open interest, total volume
- Strike, expiration, DTE, put/call, ITM flag
- Underlying price at snapshot time

**Computed/derived:**
- GEX/DEX/VEX/TEX aggregates by strike and expiry
- Put-call ratios (OI and volume) at expiry level
- IV term structure (matrix across strikes x DTEs)
- IV rank (percentile over historical DTE-14 ATM)
- OI wall detection (support/resistance strikes)
- SMA trend from price history

**From Universe Scanner (quotes, not persisted):**
- Volume, relative volume, price change %, 52w range position
- Movers from $SPX by volume

---

## Available from Schwab API but NOT Stored

These fields exist in the raw API response but are discarded at parse time in `schwab/models.py`:

| Field | API Source | Notes |
|-------|-----------|-------|
| bidSize, askSize, lastSize | Contract object | Liquidity at each strike |
| open, high, low, close | Contract object | Option-level OHLC (intraday premium range) |
| previousClose, change, percentChange | Contract object | Premium momentum, net premium change |
| rho | Contract object | Rate sensitivity (meaningful for 14+ DTE) |
| theoreticalOptionValue | Contract object | Schwab's model fair value |
| theoreticalVolatility | Contract object | Model-implied vol |
| timeValue, intrinsicValue | Contract object | Decomposed premium |
| dollarDelta | Contract object | Dollar move per $1 underlying move |
| tradeTimeInLong, quoteTimeInLong | Contract object | Exact timestamps per contract |
| nonStandard | Contract object | Corporate action adjusted contracts |
| settlementType | Contract object | PM/AM settled |
| exerciseStyle | Contract object | American vs European |
| lastTradingDay | Contract object | Final trade date |
| optionDeliverablesList | Contract object | Deliverable details |
| interestRate | Chain top-level | Risk-free rate used in pricing |
| volatility | Chain top-level | Schwab's computed HV (vs per-contract IV) |
| expirationType | Expiration chain | Regular (R), Quarterly (Q), Weekly (W) |
| settlementType | Expiration chain | PM/AM per expiration |

---

## Feature Ideas

### Tier 1: Quick Wins (1-2 hours, almost no new infrastructure)

#### 1. Liquidity Flow Imbalance
**Data needed:** bidSize, askSize per contract per snapshot (2 new columns in option_contracts)

**What it enables:**
- `bid_ask_size_ratio = bidSize / (bidSize + askSize)` — if 0.8+, heavy buy-side liquidity, sellers dominate. If 0.2-, heavy sell-side.
- Track how this ratio shifts over time per strike. When bid size collapses and ask size builds at a strike, liquidity is vacating — often precedes a move through that level.
- Combine with existing OI walls: a strike with high OI AND deteriorating bid-side liquidity is a weak wall that's more likely to break.

**Implementation:** Add 2 columns to `OptionContractRow` + DB. ~20KB extra per scrape for SPY. Zero API cost.

#### 2. Premium Momentum / Velocity
**Data needed:** option-level percentChange, open, high, low, close (6 new columns)

**What it enables:**
- See which strikes are getting bid up fastest intraday (volume + premium rise = institutional buying)
- Detect when a spread you're watching is deteriorating before stop-loss triggers
- Build "premium velocity" signals: strikes where mark price is moving faster than the underlying

#### 3. IV Skew / Smile Tracking
**Data needed:** Already have volatility + delta per contract — just need aggregation by delta buckets

**What it enables:**
- At each snapshot, compute IV by delta bucket (0.10, 0.15, 0.20, 0.25, 0.30, ATM)
- Track how the 0.10 put IV vs ATM IV ratio changes — when put skew steepens, market is buying downside protection aggressively
- One of the most predictive signals for near-term drawdowns
- New table: `aggregates_by_delta_bucket` (snapshot_id, delta_bucket, put_call, avg_iv, avg_gamma, oi_total, vol_total)

---

### Tier 2: Medium Value (half-day project)

#### 4. Block Trade Detection
**Data needed:** lastSize + totalVolume delta between snapshots

**What it enables:**
- When a single snapshot shows volume jump of 500+ on a normally quiet OTM strike, flag it
- Cross-reference with bidSize/askSize to see if it hit bid (selling) or ask (buying)
- These are "unusual activity" alerts — often hedge fund positioning
- Could feed into Discord alerts alongside existing scanner

#### 5. Put-Call Divergence by DTE Bucket
**Data needed:** Existing data, new aggregation query

**What it enables:**
- PCR for 0-2 DTE vs 3-7 DTE vs 7-14 DTE vs 14+ DTE
- When short-dated PCR is extreme (lots of 0DTE put buying) but longer-dated is neutral = short-term panic, not structural fear
- When longer-dated PCR rises = institutional hedging, more meaningful
- Separates "gamma squeeze" noise from real positioning

#### 6. Mispricing Detector
**Data needed:** theoreticalOptionValue vs actual mark (1 new column)

**What it enables:**
- If mark < theoretical by >5%, option is cheap relative to Schwab's model
- If mark > theoretical by >5%, expensive
- Mean-reversion signal — cheap options tend to normalize
- Can score spreads by whether both legs are cheap (good entry) or expensive (avoid)

#### 7. HV vs IV Spread Tracker
**Data needed:** Chain top-level volatility (HV) vs per-contract IV — both available, HV not stored

**What it enables:**
- Track IV/HV ratio over time per ticker
- When IV/HV ratio spikes, options are expensive relative to realized move (sell premium)
- When IV/HV ratio drops, options are cheap (buy premium)
- Simple mean-reversion signal that works well for credit spreads

---

### Tier 3: Higher Effort, Biggest Edge

#### 8. Expiration Chain Tracking
**Data needed:** `get_expirations()` endpoint (currently unused, 1 API call per ticker)

**What it enables:**
- New weekly expirations being listed
- Changes in available DTEs over time
- Gaps in the calendar (holidays, no 0DTE days)
- Track expirationType (Regular R, Quarterly Q, Weekly W) — do certain expiration patterns have different profitability?
- Helps with "week effect" analysis

#### 9. Cross-Ticker Aggregate GEX
**Data needed:** Existing GEX data, cross-ticker aggregation

**What it enables:**
- Track when multiple names show unusual activity simultaneously (sector rotation signal)
- Compute aggregate net GEX across entire universe, not just SPY
- Detect "gamma cliffs" — price levels where net GEX flips from positive to negative across multiple tickers
- Identify dominant gamma regime across the market (bullish vs bearish gamma)

#### 10. Earnings IV Crush Tracker
**Data needed:** IV snapshots around earnings dates, plus earnings calendar

**What it enables:**
- Track IV buildup in 30 days before earnings (IV rank rising)
- Measure actual IV drop post-earnings
- Build "IV crush magnitude" database per company to predict future crushes
- Directly monetizable — sell premium before earnings with known crush patterns
- Algo pipeline already has `earnings_filter.py` but no earnings IV tracking
- Could use Polygon's earnings calendar or manual earnings dates

#### 11. Option Volume Profile / VWAP by Strike
**Data needed:** totalVolume + mark price per snapshot

**What it enables:**
- Compute volume-weighted average price per strike across the day
- See where most volume transacted vs where price ended up
- Identifies "accepted" vs "rejected" prices at each strike
- Similar to stock volume profile but for option premium

#### 12. Gamma Flip Level Tracking
**Data needed:** Existing GEX aggregates

**What it enables:**
- Find the price level where net GEX crosses from positive to negative (gamma flip)
- Above flip = dealer long gamma (mean-reverting, low vol)
- Below flip = dealer short gamma (momentum, high vol)
- Track how this level moves intraday and over days
- Already partially computed in aggregates_by_strike — just need to find the crossover point

---

## Implementation Notes

**DB Schema Changes:**
- All Tier 1 changes are additive columns to `option_contracts` — no migration headaches
- IV Skew (Tier 1) needs new `aggregates_by_delta_bucket` table — follow same pattern as `aggregates_by_strike`
- No existing tables need to be dropped or altered structurally

**Scraper Changes:**
- `schwab/models.py` — add fields to `OptionContractRow` dataclass
- `schwab/models.py` — extract new fields from contract dict in `flatten_option_chain()`
- `gex/storage.py` — add columns to CREATE TABLE and INSERT statements
- No new API calls needed for Tier 1-2 features

**Backward Compatibility:**
- All new columns should be NULL-able initially
- Historical data won't have new fields — queries need to handle NULLs
- IV rank and GEX calculations are unaffected (use existing fields)

**Rate Limit Impact:**
- Tier 1-2: Zero additional API calls (data already in chain response)
- Tier 3 #8 (Expiration Chain): +1 API call per ticker per cycle. With 8 tickers = +8 calls/cycle. Still well within 60/min budget.
- Tier 3 #10 (Earnings): Could use existing price history endpoint or external source

---

## Priority Order (recommended)

1. **bidSize/askSize** → Liquidity Flow Imbalance (5 min to add, high signal value)
2. **IV Skew** → Delta-bucketed IV tracking (aggregation only, no new data)
3. **Premium OHLC** → Option-level open/high/low/close/percentChange
4. **HV vs IV Spread** → Top-level HV tracking (1 field, big insight)
5. **Mispricing Detector** → theoreticalOptionValue vs mark
6. **Put-Call Divergence by DTE Bucket** → New aggregation query
7. **Block Trade Detection** → Volume delta between snapshots
8. **Gamma Flip Level Tracking** → Find crossover in existing GEX data
9. **Expiration Chain Tracking** → +1 API call per ticker
10. **Cross-Ticker Aggregate GEX** → Cross-ticker aggregation
11. **Option Volume Profile** → VWAP by strike
12. **Earnings IV Crush Tracker** → Needs earnings calendar data

---

## DB Clean Up

### What's Solid (don't touch)

- **Aggregate table pattern** — `aggregates_by_strike`, `aggregates_by_expiry`, `aggregates_by_bucket` pre-compute heavy GEX math at write time. Keep this pattern for IV skew (`aggregates_by_delta_bucket`).
- **FK relationships** — `option_contracts` -> `snapshots` with `ON DELETE CASCADE`. Correct.
- **BIGSERIAL IDs** — Will exceed 2.1B rows on `option_contracts` within a year at current scrape rates.

### Problems (fix before Tier 1 features)

#### 1. `captured_at` is TEXT, not TIMESTAMPTZ (HIGH PRIORITY)

Every time-range query does `WHERE captured_at::timestamp >= NOW() - INTERVAL '20 minutes'`. The `::timestamp` cast prevents index range scans — Postgres must cast every row before comparing. On 50M+ rows this is a sequential scan disguised as an index scan.

**Fix:**
```sql
ALTER TABLE snapshots ALTER COLUMN captured_at TYPE TIMESTAMPTZ
  USING captured_at::TIMESTAMPTZ;
```
All `::timestamp` casts in queries go away. One-time table rewrite, ~30-60 seconds on current data.

#### 2. Missing Indexes

Existing 6 indexes cover GEX lookups but miss critical query patterns:

| Missing Index | Why Needed | Queries It Helps |
|---|---|---|
| `idx_oc_snapshot_id` ON `option_contracts(snapshot_id)` | FK lookups for snapshot replay/backtests | `WHERE snapshot_id = ?` |
| `idx_oc_symbol_snapshot` ON `option_contracts(symbol, snapshot_id)` | Spread hunter / scanner joins by symbol + latest snapshot | `JOIN snapshots ON symbol + ORDER BY captured_at DESC` |
| `idx_oc_expiry_dte` ON `option_contracts(expiration_date, dte)` | IV rank query, expiry aggregations | `GROUP BY expiration_date, dte` |
| `idx_oc_greeks_present` ON `option_contracts(snapshot_id, put_call, delta)` WHERE `delta IS NOT NULL` | 90% of queries filter contracts with Greeks. Partial index is 10x smaller and faster | `WHERE delta IS NOT NULL AND snapshot_id = ?` |

#### 3. Denormalized Columns in `option_contracts`

`underlying_symbol`, `underlying_price`, `snapshot_captured_at` stored on every contract row. Already exist in `snapshots`. ~40 bytes wasted per row = ~4 GB/year redundant. Also creates two sources of truth for `underlying_price`.

**Fix:** Don't normalize now (expensive migration). Add a retention policy / archival migration later and clean up at that time. For now it's a storage tax, not a correctness problem.

#### 4. `raw_json` Column Bloat

When `--raw-json` is enabled, stores full contract dict (~1-2KB per row). Adds 2-4 GB/month. With `skip_raw_json=True` (default) the column is mostly NULL (1 byte per row in Postgres — no issue).

**Action:** If you ever enable `--raw-json`, ensure backup/replication strategy accounts for the 10-20x storage increase.

#### 5. No Retention Mechanism

Storage projections: 40-80 GB/year. 2.27TB desktop disk handles 2-3 years, but queries slow as table grows without partitioning.

**Fix (deferred until ~50M rows, ~6 months):** Add monthly declarative partitioning on `option_contracts`. New data goes to current month's partition. Old partitions can be detached and archived without affecting active queries.

### Migration Script (COMPLETED June 2026)

```sql
-- DONE: captured_at type fixed (text → timestamptz)
-- DONE: 4 new indexes added
-- DONE: all ::timestamp casts removed from Python code
-- DB size: 1673 MB → 2077 MB (+404 MB from indexes)
-- All 10,282 snapshots + 4M contracts preserved
```

Verified:
- `captured_at` is now `timestamp with time zone`
- Time-range queries use Bitmap Index Scan (0.175ms vs sequential scan)
- All 9 indexes present on option_contracts + snapshots
- 35 `::timestamp` casts removed from 9 Python files

### Deferred (not urgent)

| Issue | Why Defer | When to Fix |
|---|---|---|
| Denormalized columns in option_contracts | Storage tax only, no correctness impact | Retention/archival migration |
| REAL vs DECIMAL for prices | Precision loss negligible at current decimals | Never, unless rounding bugs appear |
| Table partitioning | Not needed until 50M+ rows (~6 months) | Q3 2026 |
| Compression / TOAST tuning | Postgres handles automatically | When disk usage concerns arise |

### Why Run Migration Before Tier 1

- `captured_at` TIMESTAMPTZ makes liquidity flow time-series queries 10-100x faster
- Partial index on `delta IS NOT NULL` speeds up IV skew bucket aggregation
- `(snapshot_id)` index makes backtesting against historical snapshots efficient
- All Tier 1 features are additive only — new columns + new aggregate table. No schema refactoring blocks them, but this migration makes the new features run fast from day one.
