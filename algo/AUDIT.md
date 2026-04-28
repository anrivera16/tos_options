# `/algo` Audit — Findings & Fixes

Audit date: 2026-04-27
Scope: every module under `algo/` (`__init__`, `config`, `display`, `earnings_filter`, `generators`, `iv_rank_filter`, `pipeline`, `risk_manager`, `scoring`, `stop_loss`, `trend_filter`, `types`, `wall_detector`, `wall_proximity`).

Severity legend:
- **CRITICAL** — silently breaks correctness of backtest results.
- **HIGH** — wrong numbers in metrics or unexpected pipeline behavior.
- **MEDIUM** — brittle / latent bug, degraded over time.
- **LOW** — cosmetic / dead code / minor smell.

---

## CRITICAL

### C1. Filters drop rejected candidates instead of returning them

**Files:** `algo/trend_filter.py:97-116`, `algo/earnings_filter.py:97-110`, `algo/wall_proximity.py:41-72`, `algo/iv_rank_filter.py:74-84`.

All four filters mark candidates with `c.reject(module, reason)` *and* exclude them from the returned list. The pipeline then computes:

```python
# pipeline.py:118-120
passed = [c for c in candidates if c.passed]
rejected = [c for c in candidates if not c.passed]
result.rejected = rejected
```

But by that point, `candidates` only contains what the **last** filter (proximity) returned — which is just the kept set. Rejected candidates from every prior stage have been thrown away. Consequences:

- `result.rejected` is almost always empty.
- `BacktestResult.rejections_by_module` is always empty.
- `display.py` "REJECTIONS" section never prints.
- Pipeline diagnostics that "X dropped at trend" are wrong.

**Fix:** filters should return *all* candidates with `passed`/`rejection_reasons` set, and the pipeline should split on `c.passed` only at scoring time. Concretely:

```python
# trend_filter.py — replace `kept` list with returning all candidates
def apply_trend_filter(...):
    if not config.enabled:
        for c in candidates:
            c.tag("trend:disabled")
        return candidates
    trend = determine_trend(...)
    for c in candidates:
        c.trend_direction = trend.value
        if trend == TrendDirection.BULLISH:
            if c.spread_type == "bull_put_credit":
                c.tag("trend:bullish_match")
            else:
                c.reject("trend", "bear call rejected in bullish trend")
        elif trend == TrendDirection.BEARISH:
            ...
        elif config.neutral_action == "keep_none":
            c.reject("trend", "neutral trend, no trades taken")
    return candidates  # always return everything
```

Apply the same pattern to `apply_earnings_filter`, `apply_proximity_filter`, `apply_iv_rank_filter`.

In the pipeline, the `result.post_*` counters can keep using `len([c for c in candidates if c.passed])`, which is already what they do.

---

### C2. `apply_iv_rank_filter` returns `[]` when out of range

**File:** `algo/iv_rank_filter.py:78, 84`.

When `rank < min` or `rank > max` the function rejects each candidate then `return []`. This drops every candidate (including their rejection records) from the pipeline.

**Fix:** mark rejections and return `candidates` as-is. After C1's fix this is a one-line change (just `return candidates` instead of `return []`).

---

### C3. Backtest never closes positions — `trade_result` always `None`

**Files:** `algo/pipeline.py:131-133`, `algo/risk_manager.py:110-137`.

`BacktestPipeline.run_on_snapshot` calls `risk_mgr.open_position(...)` but there is no corresponding `close_position` anywhere in the pipeline. Because of this:

- `CandidateSpread.trade_result` stays `None` for every trade.
- `BacktestResult.compute_summary()` filters to `[t for t in self.trades if t.trade_result is not None]` — always empty.
- `total_trades`, `wins`, `losses`, `win_rate`, `total_pnl`, `max_drawdown`, `profit_factor` all stay at zero.

The `RiskManager.daily_pnl` / `weekly_pnl` counters never advance, so the daily/weekly circuit breakers are dead code in backtest mode.

**Fix:** add an exit step. Two reasonable options:

1. **End-of-window resolution** — at expiry (or `dte == 0` snapshot), call `risk_mgr.close_position(pos, current_spread_cost, exit_date)` for every still-open position. Use `algo.stop_loss.check_exit` against intermediate snapshots to trigger early exits.
2. **Per-snapshot exit pass** — at the top of `run_on_snapshot`, walk `self.risk_mgr.state.open_positions`, look up current short/long marks for that position from `rows`, call `check_exit`, close on signal. This is the more honest backtest.

The `max_hold_days` / `min_hold_days` plumbing in `stop_loss.py` is built for option 2 — wire it up.

---

### C4. `trade_result` mislabels small losses as "partial_win"

**File:** `algo/risk_manager.py:132-137`.

```python
if candidate.pnl and candidate.pnl > 0:
    candidate.trade_result = "win"
elif candidate.pnl and candidate.pnl < -candidate.max_loss * 0.5:
    candidate.trade_result = "loss"
else:
    candidate.trade_result = "partial_win"   # ← any pnl in [-max_loss*0.5, 0] lands here
```

A trade closed at a small loss (e.g. `pnl = -0.10`) is labeled `partial_win`. `BacktestResult.compute_summary` then counts it toward win rate:

```python
# types.py:201
self.win_rate = (self.wins + self.partial_wins) / self.total_trades * 100.0
```

This inflates win rate. Every backtest comparison number is wrong by this amount.

**Fix:** use sign of `pnl` for win/loss split, and reserve `partial_win` for *positive but below profit target* outcomes (or remove the bucket entirely):

```python
if pnl > 0:
    candidate.trade_result = "win" if pnl >= candidate.credit * profit_target_pct/100 else "partial_win"
elif pnl < 0:
    candidate.trade_result = "loss"
else:
    candidate.trade_result = "scratch"
```

Or simpler — drop `partial_win` from the win rate aggregation in `compute_summary`.

---

## HIGH

### H1. `RiskManager` never resets daily/weekly P&L between sessions

**File:** `algo/risk_manager.py:139-145`, `algo/pipeline.py:48-140`.

`reset_daily()` and `reset_weekly()` exist but the pipeline never calls them. In a multi-day backtest the daily counter accumulates indefinitely and the daily-loss circuit breaker either never trips or trips permanently after one bad day.

**Fix:** in `run_on_snapshot`, compare `snapshot_timestamp[:10]` against `state.current_date`. On a new date, call `reset_daily()` and update `state.current_date`. Same for week boundaries (compare ISO week number) → `reset_weekly()`.

---

### H2. `PortfolioState.available_capital` ignores contract count

**File:** `algo/risk_manager.py:39-42`.

```python
committed = sum(p.max_loss * 100 for p in self.open_positions)
```

This counts each open position as 1 contract. If `position_size()` returns >1 (the typical case at $50k bankroll, 3% risk, $5 spread), capital usage is undercounted by the contract multiplier. Currently harmless because `max_positions = 1` and `available_capital` isn't read anywhere, but the first time someone increases `max_positions`, position sizing across positions becomes wrong.

**Fix:** persist contract count on the position when it's opened:

```python
# risk_manager.py — open_position
contracts = self.position_size(candidate)
candidate.tags.append(f"risk:contracts={contracts}")
candidate.contracts = contracts   # add field on CandidateSpread
```

Then `available_capital` becomes `sum(p.max_loss * 100 * p.contracts ...)`. The `close_position` P&L calc (`pnl_val = candidate.pnl * 100 * self.position_size(candidate)`) should also use the stored value, not recompute — recomputing means a bankroll change between open and close silently changes historical P&L.

---

### H3. Duplicate `StopLossConfig` definition

**Files:** `algo/config.py:99-105`, `algo/stop_loss.py:21-29`.

Both files define their own `StopLossConfig` dataclass with the same field names. The pipeline imports `StopLossConfig` from `config.py` but `stop_loss.check_exit` is typed against the one in `stop_loss.py`. Today this works only because of structural compatibility (duck typing); the moment one drifts (e.g. someone adds a field in one place), behavior diverges silently.

**Fix:** delete the dataclass in `stop_loss.py:21-29` and import it from `config`:

```python
# stop_loss.py
from algo.config import StopLossConfig
```

---

### H4. `_find_nearest_strike` doesn't constrain to the correct side of `short_strike`

**File:** `algo/generators.py:296-306, 122-131, 230-238`.

For a bull put credit, `target_long_strike = short_strike - width` and the long leg must be **below** the short. `_find_nearest_strike` searches the whole OTM list and returns the geometrically nearest strike — which can be *above* the short (e.g. when only $578 and $583 are listed and target is $575, it picks $578). The downstream guard `abs(actual_width - width) > 1.0` saves correctness in most cases but:

- If $578 is selected against short $580 (target $575): `actual_width = 580 - 578 = 2`, `abs(2 - 5) = 3 > 1.0` → rejected. OK.
- But if strike grid is denser (e.g. half-dollar strikes near the money on SPY), edge cases may slip through and produce a degenerate spread.

**Fix:** filter the search domain by side first:

```python
# bull put: long must be strictly below short
long_candidates = [p for p in otm if _to_float(p.get("strike"), 0) < short_strike]
long_row = _find_nearest_strike(long_candidates, target_long_strike)

# bear call: long must be strictly above short
long_candidates = [c for c in otm if _to_float(c.get("strike"), 0) > short_strike]
```

---

### H5. `result.post_walls` declared but never set

**File:** `algo/types.py:158`, `algo/pipeline.py:86-115`.

`PipelineResult.post_walls` is in the dataclass but the pipeline never assigns it (walls are detected but not used as a candidate filter on their own — proximity is the gate). Reading `result.post_walls` always shows 0.

**Fix:** delete the field, or set it to `len(walls)` if the intent is "how many walls were detected this snapshot." Update `display.py:85-91` accordingly.

---

## MEDIUM

### M1. Wall-proximity "same_side_only" misses walls between price and short strike

**File:** `algo/wall_proximity.py:90-104`.

For a bull put with short at $585 and underlying at $600, only walls at strike `< 585` are considered (`w.strike < candidate.short_strike`). A heavy support wall at $590 — i.e. the *first* support level on the way down — is ignored, even though if it breaks, the next stop is the short.

The docstring says "support wall just below your short put strike" — that's a strategy choice, but most credit-spread literature treats walls *between* current price and short strike as the more dangerous case (because their failure points price toward the short).

**Fix (recommended):** consider walls within a strike-distance band of `short_strike`, regardless of side, when `same_side_only` is set:

```python
if candidate.spread_type == "bull_put_credit" and w.wall_type == "support":
    # any support wall within the proximity band of the short strike
    relevant.append(w)
```

Then let `proximity_pct` do the actual filtering. This is a behavior change — flag for the user before applying.

---

### M2. Earnings calendar is hardcoded and runs out April 2026

**File:** `algo/earnings_filter.py:23-33`.

`DEFAULT_EARNINGS_DATES` only covers Jan–Apr 2026. Today is 2026-04-27 — a backtest extending into May or later silently has zero earnings filtering. There's no warning when the calendar is exhausted.

**Fix:** at minimum, log a warning when the latest date in the calendar is within the trade window. Long-term, fetch from a service (e.g. Finnhub, Polygon) and cache.

---

### M3. `current_iv = 0.0` treated as valid, returns rank 0%

**File:** `algo/iv_rank_filter.py:56-67`.

```python
if current_iv is None:
    for c in candidates: c.reject(...)
```

A `current_iv` of `0.0` (DB NULL coerced to zero, or a stale snapshot) is treated as a valid reading and yields a rank of 0% → all candidates get rejected as "below min." A genuine 0% IV is impossible.

**Fix:** treat `current_iv <= 0` the same as `None`.

---

### M4. `wall_detector.fetch_strike_data_from_rows` and `detect_walls` don't reject `None` strikes

**Files:** `algo/wall_detector.py:41, 121`.

```python
strike = float(row.get("strike", 0))
```

`row.get("strike", 0)` returns `0` only if the key is missing. If the key is present and explicitly `None`, this raises `TypeError`. The same defensive `_to_float` helper exists in `generators.py` — use it here too.

---

### M5. RiskManager P&L assumes `exit_price` is "spread cost to close" — not documented

**File:** `algo/risk_manager.py:118-129`.

`candidate.pnl = candidate.credit - exit_price` makes sense only if `exit_price` is the cost to buy back the spread (mid of `short - long`). Nothing in the call signature or docstring states this. The duplicated code paths for `bull_put_credit` and `bear_call_credit` (both branches do the same thing) suggest the author considered they might differ — they don't, because credit and cost-to-close are signed the same way for both.

**Fix:** rename parameter to `exit_spread_cost`, drop the dead `if/else`:

```python
def close_position(self, candidate, exit_spread_cost: float, exit_date: str):
    candidate.pnl = candidate.credit - exit_spread_cost
```

---

### M6. `wall_detector` classifies `strike == underlying_price` as resistance (puts) / support (calls)

**File:** `algo/wall_detector.py:85-90`.

```python
if stats["put_oi"] > stats["call_oi"]:
    wall_type = "support" if strike < underlying_price else "resistance"
```

When `strike == underlying_price` exactly, falls into the `else` branch. ATM walls are arguably neither support nor resistance — they're pin candidates. Edge case that won't bite on SPY (rarely ATM exactly), worth a `wall_type = "atm"` value or comment.

---

### M7. `BacktestPipeline.run_on_snapshots` doesn't `reset()` between runs

**File:** `algo/pipeline.py:142-202`.

If a caller does:

```python
pipeline.run_on_snapshots(snaps_q1)
pipeline.run_on_snapshots(snaps_q2)
```

…the risk manager carries over open positions from Q1 into Q2, P&L accumulates, etc. Either auto-reset at the top of `run_on_snapshots` or document that the caller must call `pipeline.reset()`.

---

## LOW

### L1. `PortfolioState.bankroll` default in dataclass is dead

**File:** `algo/risk_manager.py:24`.

`bankroll: float = 50000.0` in `PortfolioState` is always overridden by `RiskManager.__init__` passing `config.bankroll`. Either drop the default or accept that it's an example.

### L2. `apply_risk_filter` short-circuit ordering reads strangely

**File:** `algo/risk_manager.py:166-177`.

```python
for c in candidates:
    allowed, reason = ...
    if allowed:
        approved.append(c)
    else:
        c.reject(...)
    if approved:
        break
```

The `if approved: break` outside the `if allowed` branch implies the loop might keep iterating even after a successful approval. It doesn't (because `approved` only becomes truthy in the `allowed` branch), but the structure suggests a bug. Move the break inside `if allowed:`.

### L3. `generators.py` enumerates `for i, short_row in enumerate(otm)` but never uses `i`

**File:** `algo/generators.py:102, 213`.

`enumerate` here is purely cosmetic — replace with `for short_row in otm:`.

### L4. `display.format_pipeline_report` hardcodes IV gate thresholds

**File:** `algo/display.py:64`.

```python
gate = "OPEN" if rank is not None and 30 <= rank <= 95 else "CLOSED"
```

Numbers are duplicated from `IVRankConfig.iv_rank_min/max`. Pass the config (or the values) through `iv_info` instead of hardcoding.

### L5. Inconsistent terminology: `pnl` is per-share, `pnl_val` is per-position dollars

**File:** `algo/risk_manager.py:122-129`.

Two different fields with the same conceptual name (one stored on the candidate, one local). Confusing. Use `candidate.pnl_per_share` and `candidate.pnl_dollars` (or compute one from the other on demand).

### L6. `BacktestResult.compute_summary` skips empty case silently

**File:** `algo/types.py:191-222`.

When there are no resolved trades, `compute_summary` returns immediately with all stats at default. Combined with C3 (`trade_result` always None), the user gets a "successful" backtest with all-zero output and no warning. At minimum, log a warning when `len(resolved) == 0` but `len(self.trades) > 0`.

### L7. `pipeline.py` imports `Any` from `typing` but isn't using it where typed dicts would help

Lots of `dict[str, Any]` in module signatures. Consider a `Snapshot` TypedDict for the per-snapshot dict consumed by `run_on_snapshots` — it's currently constructed by callers with no type guidance.

---

## Suggested fix order

If applying these incrementally, do them in this order — each one unblocks the next:

1. **C1 + C2** (filter rejection-propagation) — restores observability into what each filter is doing.
2. **C3** (close positions in backtest) — without it, you have no metrics at all.
3. **C4** (trade_result classification) — fixes the win-rate inflation.
4. **H1** (reset daily/weekly P&L) — daily/weekly limits start working.
5. **H3** (dedupe `StopLossConfig`) — needed before C3's stop-loss wiring touches both files.
6. **H2 + H5** — quick housekeeping that prevents future bugs.
7. **H4** — defense-in-depth on the generator.
8. **M-series** — pick by what the next backtest pass actually exercises.
9. **L-series** — sweep when convenient.

---

## Items NOT requiring change

- `compute_iv_rank` empty-list fallback (`return 50.0` at line 33) — unreachable because `apply_iv_rank_filter` checks `len < 5` first. Defensive code, leave as is.
- `BacktestResult.profit_factor = float("inf")` when no losses — `display.py:200` handles inf via the `< 100` check.
- The `_to_float` / `_to_int` helpers in `generators.py` are correct as defensive shims around messy DB rows.
- Generator's enumeration of all qualifying shorts (not just the highest-delta one) is by design — let scoring pick.
