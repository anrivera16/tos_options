# GEX Calculation Audit Report

## Scope

Full audit of the GEX (Gamma Exposure) computation pipeline in the `tos_options` project:
- `gex/calculations.py` — core formulas
- `gex/storage.py` — DB schema + persistence
- `gex/chart.py` — visualization
- `gex/iv_term.py` — IV term structure queries
- `schwab/models.py` — data ingestion
- `cli.py` — CLI integration
- `tests/test_gex.py` — test coverage

---

## 1. GEX Formula

**Location:** `gex/calculations.py` → `_unsigned_gamma_exposure()` + `_signed_gamma_exposure()`

```
Unsigned GEX = gamma × open_interest × 100 × (underlying_price)²
Signed GEX   = sign × Unsigned GEX
  where sign = +1 for CALLS, -1 for PUTS
```

**Verdict: CORRECT.** This is the standard dealer GEX formula. The `S²` term (spot price squared) accounts for the fact that gamma exposure is dollar-denominated — a 1% move on a $500 stock moves more dollars than a 1% move on a $100 stock. The sign convention (+1 calls / -1 puts) assumes dealers are typically long calls and short puts (the standard market-maker hedging assumption).

**Manual verification against test fixture:**
- 6 contracts (3 calls, 3 puts) at spot=500
- Computed total_gex = 8,500,000 ✓ (matches test)
- Computed total_dex = 1,050,000 ✓
- Computed total_vex = 4,540 ✓
- Computed total_tex = -6,630 ✓

---

## 2. DEX (Delta Exposure)

**Formula:**
```
DEX = delta × open_interest × 100 × underlying_price
```

**Verdict: CORRECT.** Delta already carries its own sign (negative for puts, positive for calls), so no additional sign multiplier is needed. The code correctly does NOT apply `_signed_side()` to DEX — it uses the raw delta value which is already signed.

---

## 3. VEX (Vega Exposure)

**Formula:**
```
VEX = vega × open_interest × 100
```

**Verdict: CORRECT.** Vega is always positive for both calls and puts (long options have positive vega). No spot price multiplier needed — vega exposure is already in dollar terms per 1% IV change. The code does NOT apply `_signed_side()` to VEX.

---

## 4. TEX (Theta Exposure)

**Formula:**
```
TEX = theta × open_interest × 100
```

**Verdict: CORRECT.** Theta is naturally negative for long options. No sign flip needed. The code does NOT apply `_signed_side()` to TEX.

---

## 5. Aggregation Logic

**Location:** `gex/calculations.py` → `_aggregate_contracts()`

Aggregates by:
- **Strike** → `by_strike` (primary GEX profile)
- **Expiration** → `by_expiration` (term structure)
- **DTE bucket** → 0DTE, 1-3DTE, 4-7DTE, 8-30DTE, 31-90DTE, 90+DTE
- **Moneyness** → ATM (within 2%), ITM, OTM
- **Distance from spot** → percentage bands

**Key aggregation behavior:**
- `call_gex` = sum of GEX for CALL contracts only (positive by definition)
- `put_gex` = sum of GEX for PUT contracts only (negative by definition)
- `net_gex` = call_gex + put_gex (total signed exposure)
- `call_oi` / `put_oi` tracked separately
- `pcr_oi` = put_oi / call_oi (put/call ratio)

**Verdict: CORRECT.** Clean additive aggregation. Test confirms `sum(by_strike) == total` and `sum(by_expiration) == total` — all rollups reconcile.

---

## 6. Gamma Flip Estimation

**Location:** `gex/calculations.py` → `estimate_gamma_flip()`

Linear interpolation between strikes where net_gex crosses zero:

```
weight = |prev_gex| / (|prev_gex| + |curr_gex|)
flip   = prev_strike + (curr_strike - prev_strike) × weight
```

**Verdict: CORRECT.** Standard linear interpolation. Test confirms flip at 497.5 for the fixture data. The chart module (`chart.py`) duplicates this logic independently but with the same formula — functional but slightly redundant.

---

## 7. Dealer Regime Classification

**Location:** `tests/test_gex.py` references `classify_regime()` and `build_options_analysis()`

Four regimes:
- **balanced** — high positive GEX, mean-reverting
- **pinned** — concentrated GEX at specific strikes
- **transition** — near-zero total GEX, flip zone nearby
- **expansion** — negative GEX, momentum/trending

Features hysteresis via `apply_regime_hysteresis()` to prevent regime-flapping between snapshots.

**Verdict: REASONABLE.** The hysteresis mechanism is good engineering. The regime scoring appears to use a multi-factor approach with configurable margin thresholds. Tests cover regime transitions and edge cases.

---

## 8. Data Source: Schwab API

**Location:** `schwab/models.py` → `flatten_option_chain()`

- Parses Schwab's nested `callExpDateMap` / `putExpDateMap` JSON structure
- Extracts: gamma, delta, theta, vega, IV, OI, volume, bid/ask, mark, DTE, strike
- Falls back gracefully for missing fields (`_safe_float`, `_safe_int`)
- `underlying_price` resolved with priority chain: contract level → quote level → chain level

**Verdict: CORRECT.** Robust parsing with null safety. The gamma and OI values used in GEX calc come directly from Schwab's option chain — these are real dealer-quality greeks, not BSM estimates.

---

## 9. DB Schema

**Location:** `gex/storage.py`

Three aggregate tables:
- `aggregates_by_strike` — PK (snapshot_id, strike)
- `aggregates_by_expiry` — PK (snapshot_id, expiration_date)
- `aggregates_by_bucket` — PK (snapshot_id, bucket_type, bucket_label)

Plus raw data:
- `snapshots` — metadata + underlying price
- `option_contracts` — full per-contract data (all greeks, OI, volume)

**Verdict: CORRECT.** Schema is clean, ON CONFLICT upsert logic handles re-runs. Foreign keys with CASCADE delete. Both SQLite and Postgres supported.

---

## 10. Test Coverage

**Location:** `tests/test_gex.py` (18 tests)

Coverage summary:
- ✅ Headline totals match manual calculation
- ✅ Rollup reconciliation (strike/expiry/bucket all sum to total)
- ✅ OI reconciliation (call_oi + put_oi == total_oi)
- ✅ Gamma flip interpolation
- ✅ Top wall identification (largest call/put/net)
- ✅ Regime classification with hysteresis
- ✅ Regime-specific trade suggestions
- ✅ Degraded data handling (missing IV, missing walls)
- ✅ POP estimate bounding (0.35-0.75)
- ✅ Implausible gamma flip filtering (>30% from spot)

**Verdict: GOOD.** Tests are thorough and verify the math against known fixtures.

---

## Summary of Findings

### ✅ What's Correct
1. GEX formula is the standard dealer formula: `gamma × OI × 100 × S²` with +1/-1 sign
2. DEX, VEX, TEX formulas are all correct
3. Aggregation is clean — all rollups reconcile
4. Gamma flip interpolation is standard
5. Data source (Schwab) provides real greeks, not estimates
6. DB schema is well-designed for time-series GEX analysis
7. Test coverage is comprehensive

### ⚠️ Minor Notes (not bugs)
1. **No volume-weighted GEX option.** Currently OI-only. Some practitioners like to also compute a volume-weighted GEX as a short-term signal. Could be added as an alternative view.
2. **Chart module duplicates `estimate_gamma_flip`.** Both `calculations.py` and `chart.py` have independent flip-finding logic. Minor code duplication.
3. **`put_gex` in by_strike is signed negative.** When querying, users need to understand that `put_gex` values are already negative (unlike some platforms that report absolute put GEX). The skill documentation handles this by using `ABS(put_gex)`.
4. **SPX multiplier is 100, same as SPY.** Per Cboe SPX product specs, standard SPX options use a $100 per-index-point multiplier — the same as SPY and XSP. The code's `CONTRACT_MULTIPLIER = 100` is correct for all of SPY, SPX, and XSP.

### ❌ Bugs Found
**None.** The math is solid, the tests pass, and the data pipeline is clean.
