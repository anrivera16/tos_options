# Chunk 3: IV Term Structure Slope (Signal 2)

## Goal

Compare the implied volatility of the **nearest expiry ATM options** to the **next expiry out** on each 15-min bar. When the front expiry IV spikes relative to the back month, the market is pricing in an imminent move. When front IV collapses relative to back, the market expects nothing. This is a **timing signal** for entries.

---

## What This Signal Tells You

| Condition | Meaning | Trade Implication |
|-----------|---------|-------------------|
| Slope steepening (front IV rising vs back) | Market expects near-term move | Enter momentum / breakout trades |
| Slope flattening (front IV converging to back) | Near-term calm expected | Enter mean reversion / selling trades |
| Slope inverted (front IV < back IV) | Unusual — near-term complacency or post-event | Potential for surprise move; caution |
| Rapid slope change (velocity spike) | Sentiment shift happening now | Pay attention — something changed |

---

## Data Requirements

### From Each Snapshot

For every 15-min bar, we need:
- The **two nearest expiration dates** (e.g., 0DTE and 1DTE, or 0DTE and 2DTE)
- For each expiry: the **ATM options** (calls and puts at the strike nearest to spot)
- The **implied volatility** of those ATM options

### ATM Definition

```python
def find_atm_strike(contracts: list[dict], underlying_price: float) -> float:
    """Find the strike closest to the current underlying price."""
    strikes = sorted(set(c["strike"] for c in contracts))
    return min(strikes, key=lambda s: abs(s - underlying_price))
```

### ATM IV Extraction

```python
def extract_atm_iv(
    contracts: list[dict],
    expiration_date: str,
    atm_strike: float,
) -> float | None:
    """
    Get ATM implied volatility for a specific expiration.

    Average the call and put IV at the ATM strike for that expiry.
    If only one side is available, use that.
    """
    atm_contracts = [
        c for c in contracts
        if c["expiration_date"] == expiration_date
        and c["strike"] == atm_strike
        and c["volatility"] is not None
        and c["volatility"] > 0
    ]

    if not atm_contracts:
        return None

    ivs = [c["volatility"] for c in atm_contracts]
    return sum(ivs) / len(ivs)
```

---

## Computation Logic

### Identify Front and Back Expiries

```python
def identify_expiry_pair(contracts: list[dict]) -> tuple[str, str] | None:
    """
    Find the two nearest expiration dates in the snapshot.

    Returns (front_expiry, back_expiry) or None if < 2 expiries available.
    """
    expiries = sorted(set(c["expiration_date"] for c in contracts))

    # Filter to expiries that actually have ATM contracts with IV data
    valid_expiries = [
        e for e in expiries
        if any(c["expiration_date"] == e and c["volatility"] for c in contracts)
    ]

    if len(valid_expiries) < 2:
        return None

    return (valid_expiries[0], valid_expiries[1])
```

### Compute IV Slope

```python
def compute_iv_slope(
    contracts: list[dict],
    underlying_price: float,
) -> dict | None:
    """
    Compute the IV term structure slope between front and back expiry.

    Returns dict with slope metrics or None if insufficient data.
    """
    pair = identify_expiry_pair(contracts)
    if pair is None:
        return None

    front_expiry, back_expiry = pair
    atm_strike = find_atm_strike(contracts, underlying_price)

    # For each expiry, find the ATM strike closest to that expiry's forward
    # (may differ slightly from overall ATM due to dividend/rate effects)
    front_contracts = [c for c in contracts if c["expiration_date"] == front_expiry]
    back_contracts = [c for c in contracts if c["expiration_date"] == back_expiry]

    front_atm = find_atm_strike(front_contracts, underlying_price)
    back_atm = find_atm_strike(back_contracts, underlying_price)

    front_iv = extract_atm_iv(contracts, front_expiry, front_atm)
    back_iv = extract_atm_iv(contracts, back_expiry, back_atm)

    if front_iv is None or back_iv is None:
        return None

    # Absolute slope: front - back
    iv_slope = front_iv - back_iv

    # Ratio: front / back (useful for normalization)
    iv_slope_ratio = front_iv / back_iv if back_iv > 0 else None

    return {
        "front_expiry": front_expiry,
        "front_atm_iv": front_iv,
        "back_expiry": back_expiry,
        "back_atm_iv": back_iv,
        "iv_slope": iv_slope,
        "iv_slope_ratio": iv_slope_ratio,
    }
```

### Slope Change (Velocity)

```python
def compute_slope_change(current_slope: float, prior_slope: float | None) -> float | None:
    """Change in IV slope from prior bar."""
    if prior_slope is None:
        return None
    return current_slope - prior_slope
```

### Slope Regime Classification

```python
def classify_slope_regime(
    iv_slope: float,
    slope_change: float | None,
    thresholds: dict | None = None,
) -> str:
    """
    Classify the current IV term structure regime.

    Regimes:
    - "steepening": front IV increasing faster than back (expect move)
    - "flattening": front IV converging to back (expect calm)
    - "flat": minimal slope, stable
    - "inverted": front IV below back IV (unusual)
    """
    t = thresholds or {
        "steep_threshold": 0.02,    # 2 IV points = steepening
        "flat_threshold": 0.005,    # < 0.5 IV points = flat
        "change_threshold": 0.005,  # velocity threshold
    }

    # Inverted: front IV significantly below back
    if iv_slope < -t["steep_threshold"]:
        return "inverted"

    # Steepening: front IV much higher AND/OR slope accelerating
    if iv_slope > t["steep_threshold"]:
        if slope_change is not None and slope_change > t["change_threshold"]:
            return "steepening"
        return "steepening"

    # Flattening: slope was steep, now converging
    if slope_change is not None and slope_change < -t["change_threshold"]:
        return "flattening"

    return "flat"
```

---

## Edge Cases

### 0DTE After 3:00 PM
As 0DTE options approach expiry in the final hour, their IV becomes erratic (very high gamma, wide spreads). Handling:

```python
def should_use_0dte_as_front(front_expiry: str, current_time: datetime) -> bool:
    """
    After 3:00 PM ET, 0DTE IV may be unreliable.
    Consider using 1DTE as front if 0DTE is expiring today and it's late.
    """
    market_close = current_time.replace(hour=16, minute=0)
    time_to_close = (market_close - current_time).total_seconds() / 60

    today = current_time.date().isoformat()
    if front_expiry == today and time_to_close < 60:
        return False  # Skip 0DTE, use next expiry as front
    return True
```

### Single Expiry Available
If only one expiry has data (e.g., only 0DTE on a Friday afternoon), the signal returns `None` — we can't compute a slope without two points.

### SPX vs SPY Expiry Differences
- SPX: has Mon/Wed/Fri 0DTE expirations
- SPY: has daily expirations (Mon-Fri)
- The signal works the same — just pick the two nearest available expiries

---

## Signal Interface

```python
# 0dte/signals/iv_term_structure.py

class IVTermStructure(Signal):
    """Signal 2: IV term structure slope between front and back expiry."""

    name = "iv_term_structure"
    table = "signal_iv_slope"

    def compute(self, snapshot_id: int, db_conn):
        """
        1. Load contracts for this snapshot
        2. Identify front/back expiry pair
        3. Extract ATM IV for each
        4. Compute slope, ratio, change, and regime
        5. Write to signal_iv_slope table
        """
        contracts = self._load_contracts(snapshot_id, db_conn)
        snapshot = self._load_snapshot(snapshot_id, db_conn)

        slope_data = compute_iv_slope(contracts, snapshot["underlying_price"])
        if slope_data is None:
            return  # insufficient data, skip this bar

        # Get prior bar's slope for velocity
        prior = self._get_prior_slope(snapshot, db_conn)
        slope_change = compute_slope_change(
            slope_data["iv_slope"],
            prior["iv_slope"] if prior else None,
        )

        regime = classify_slope_regime(
            slope_data["iv_slope"],
            slope_change,
        )

        db_conn.execute("""
            INSERT INTO signal_iv_slope
                (snapshot_id, symbol, captured_at,
                 front_expiry, front_atm_iv,
                 back_expiry, back_atm_iv,
                 iv_slope, iv_slope_ratio, slope_change,
                 slope_regime)
            VALUES (%(snapshot_id)s, %(symbol)s, %(captured_at)s,
                    %(front)s, %(front_iv)s,
                    %(back)s, %(back_iv)s,
                    %(slope)s, %(ratio)s, %(change)s,
                    %(regime)s)
        """, {
            "snapshot_id": snapshot_id,
            "symbol": snapshot["symbol"],
            "captured_at": snapshot["captured_at"],
            "front": slope_data["front_expiry"],
            "front_iv": slope_data["front_atm_iv"],
            "back": slope_data["back_expiry"],
            "back_iv": slope_data["back_atm_iv"],
            "slope": slope_data["iv_slope"],
            "ratio": slope_data["iv_slope_ratio"],
            "change": slope_change,
            "regime": regime,
        })
        db_conn.commit()

    def _get_prior_slope(self, snapshot: dict, db_conn) -> dict | None:
        """Get the most recent prior bar's slope data for this trading day."""
        result = db_conn.execute("""
            SELECT iv_slope FROM signal_iv_slope sis
            JOIN snapshots_0dte s ON s.id = sis.snapshot_id
            WHERE s.symbol = %(symbol)s
              AND s.captured_at < %(current_time)s
              AND DATE(s.captured_at AT TIME ZONE 'US/Eastern') =
                  DATE(%(current_time)s AT TIME ZONE 'US/Eastern')
            ORDER BY s.captured_at DESC
            LIMIT 1
        """, {
            "symbol": snapshot["symbol"],
            "current_time": snapshot["captured_at"],
        }).fetchone()
        return result
```

---

## Relationship to Existing Code

The existing `options_analysis/engine.py` already computes a vol environment with term structure in `_compute_vol_environment()`. However, that function:
- Works on a single snapshot (not time series)
- Computes a broader term structure across all expiries
- Returns relative-value tags (`vol_sale`, `vol_buy`)

Our signal differs:
- **Time series focused** — tracks slope changes across 15-min bars
- **Two-expiry focus** — only front vs next-out for maximum sensitivity
- **Intraday regime** — classifies steepening/flattening in real time

We can reuse the ATM IV identification logic pattern from `_compute_vol_environment()` but the core computation is new.

---

## Testing

### Unit Tests
- ATM strike finding with various strike ladders
- ATM IV extraction with mixed call/put IVs
- Slope computation with known IV values
- Regime classification for each regime type
- Edge case: late-day 0DTE exclusion
- Edge case: single expiry available

### Integration Tests
- Load multi-expiry fixture → compute slope time series
- Verify regime transitions as IVs change across bars

### Fixtures
- `tests/fixtures/iv_slope_steepening.json` — Bars where front IV rises sharply
- `tests/fixtures/iv_slope_flattening.json` — Bars where front/back converge

---

## Milestone Checklist

- [ ] `find_atm_strike()` correctly identifies nearest strike
- [ ] `extract_atm_iv()` averages call/put IV at ATM
- [ ] `identify_expiry_pair()` picks correct front/back expiries
- [ ] `compute_iv_slope()` produces slope and ratio
- [ ] Late-day 0DTE exclusion works (falls back to 1DTE as front)
- [ ] `classify_slope_regime()` correctly labels all 4 regimes
- [ ] `IVTermStructure.compute()` writes to `signal_iv_slope` table
- [ ] Slope change (velocity) tracks correctly across bars
- [ ] Backtest produces slope time series for a full day
