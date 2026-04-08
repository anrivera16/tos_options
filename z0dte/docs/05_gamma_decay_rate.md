# Chunk 5: Gamma Exposure Decay Rate (Signal 4)

## Goal

Track how fast the **GEX reading is changing** per 15-min bar — the **rate of change of gamma**, not just the level. As 0DTE options approach expiration, gamma at ATM strikes explodes. When that acceleration spikes, dealer hedging flows dominate price action. That's when **mean reversion setups around GEX levels have the highest hit rate**.

---

## What This Signal Tells You

| Condition | Meaning |
|-----------|---------|
| GEX acceleration positive (speeding up) | Gamma is expanding — dealers hedging more aggressively each bar |
| GEX acceleration negative (slowing down) | Gamma is contracting — dealer impact fading |
| Acceleration spike | Entering a regime where dealers dominate — price likely to mean-revert to GEX levels |
| Steady low acceleration | Normal market — other flows matter more than dealer hedging |
| GEX level high + acceleration high | Maximum dealer impact zone — strongest mean reversion signal |

### Why Rate of Change Matters More Than Level

The absolute GEX level tells you how much dealer hedging pressure exists *right now*. But the **acceleration** tells you whether you're entering or leaving a dealer-dominated regime.

```
Example:
  Bar 1: GEX = $500M  → delta = 0
  Bar 2: GEX = $600M  → delta = +$100M   → accel = 0
  Bar 3: GEX = $800M  → delta = +$200M   → accel = +$100M  ← steepening!
  Bar 4: GEX = $1.1B  → delta = +$300M   → accel = +$100M  ← sustained
  Bar 5: GEX = $1.3B  → delta = +$200M   → accel = -$100M  ← peaking

At Bar 3-4, acceleration is positive = you're entering dealer dominance.
At Bar 5, acceleration turns negative = dealer impact is peaking/fading.
The actual trade entry is at the spike (Bar 3), not at the peak level (Bar 5).
```

---

## Data Requirements

### From Each Snapshot

This signal computes its inputs from the raw contracts:
- `gamma` — per-contract gamma
- `open_interest` — for weighting
- `underlying_price` — for dollar-normalizing GEX
- `strike` — for ATM identification
- `put_call` — for signed GEX (calls positive, puts negative)
- `dte` — to focus on 0DTE and near-term (where gamma explodes)

### Reuse from `gex/calculations.py`

```python
from gex.calculations import (
    _signed_gamma_exposure,   # signed GEX per contract
    _contract_metrics,        # full metrics including abs_gex
    CONTRACT_MULTIPLIER,      # 100
)
```

---

## Computation Logic

### Step 1: Compute Total GEX for This Bar

```python
def compute_bar_gex(
    contracts: list[dict],
    underlying_price: float,
    max_dte: int = 2,             # Focus on 0DTE and 1DTE
    strike_range_pct: float = 0.05,  # ±5% of spot
) -> dict:
    """
    Compute total GEX for the current 15-min bar.

    Focuses on near-term, near-money contracts where gamma
    is most significant for dealer hedging.
    """
    strike_min = underlying_price * (1 - strike_range_pct)
    strike_max = underlying_price * (1 + strike_range_pct)

    total_gex = 0.0
    atm_gex = 0.0
    atm_strike = None
    min_distance = float("inf")

    for c in contracts:
        # Filter
        if c["dte"] is None or c["dte"] > max_dte:
            continue
        if not (strike_min <= c["strike"] <= strike_max):
            continue
        if c["gamma"] is None or c["open_interest"] is None:
            continue

        # Compute signed GEX
        side = 1.0 if c["put_call"] == "CALL" else -1.0
        gex = side * c["gamma"] * c["open_interest"] * CONTRACT_MULTIPLIER * (underlying_price ** 2)
        total_gex += gex

        # Track ATM GEX (strike closest to spot)
        distance = abs(c["strike"] - underlying_price)
        if distance < min_distance:
            min_distance = distance
            atm_strike = c["strike"]

    # Sum GEX at ATM strike specifically
    if atm_strike is not None:
        atm_gex = sum(
            (1.0 if c["put_call"] == "CALL" else -1.0)
            * c["gamma"] * c["open_interest"] * CONTRACT_MULTIPLIER * (underlying_price ** 2)
            for c in contracts
            if c["strike"] == atm_strike
            and c["gamma"] is not None and c["open_interest"] is not None
            and c["dte"] is not None and c["dte"] <= max_dte
        )

    return {
        "total_gex": total_gex,
        "atm_gex": atm_gex,
    }
```

### Step 2: Compute Rate of Change (1st Derivative)

```python
def compute_gex_delta(
    current_gex: float,
    prior_gex: float | None,
) -> float | None:
    """
    First derivative: change in GEX from prior bar.

    Positive = gamma expanding (dealers hedging more)
    Negative = gamma contracting (dealers hedging less)
    """
    if prior_gex is None:
        return None
    return current_gex - prior_gex
```

### Step 3: Compute Acceleration (2nd Derivative)

```python
def compute_gex_acceleration(
    current_delta: float | None,
    prior_delta: float | None,
) -> float | None:
    """
    Second derivative: change in the rate of change of GEX.

    This is the key signal:
    - Positive acceleration = entering dealer-dominated regime
    - Negative acceleration = leaving dealer-dominated regime
    """
    if current_delta is None or prior_delta is None:
        return None
    return current_delta - prior_delta
```

### Step 4: Classify Acceleration Regime

```python
def classify_acceleration_regime(
    acceleration: float | None,
    total_gex: float,
    thresholds: dict | None = None,
) -> tuple[str, bool]:
    """
    Classify the current gamma acceleration state.

    Returns (regime_label, is_spike).

    Regime labels:
    - "accelerating": GEX rate of change is increasing
    - "decelerating": GEX rate of change is decreasing
    - "stable": minimal acceleration

    Spike detection:
    - True if acceleration exceeds a multiple of typical bar-to-bar change
    """
    t = thresholds or {
        "accel_threshold_pct": 0.10,  # 10% of current GEX level = significant
        "spike_multiplier": 2.0,      # 2x the threshold = spike
    }

    if acceleration is None:
        return ("stable", False)

    # Dynamic threshold based on GEX level
    # Larger GEX means larger absolute changes are normal
    threshold = abs(total_gex) * t["accel_threshold_pct"] if total_gex != 0 else 0
    spike_threshold = threshold * t["spike_multiplier"]

    is_spike = abs(acceleration) > spike_threshold

    if acceleration > threshold:
        return ("accelerating", is_spike)
    elif acceleration < -threshold:
        return ("decelerating", is_spike)
    else:
        return ("stable", is_spike)
```

---

## Time-of-Day Effects

Gamma decay is not linear throughout the day. It accelerates dramatically in the final hours:

```
0DTE Gamma Profile (approximate):
  09:30 - 12:00: Gamma grows slowly as time passes
  12:00 - 14:00: Gamma growth accelerates
  14:00 - 15:00: Gamma explodes at ATM strikes
  15:00 - 16:00: Maximum gamma — tiny moves cause massive delta shifts
```

This means:
1. **Early-day spikes are more significant** — they represent genuine positioning changes
2. **Late-day acceleration is partially structural** — gamma always grows as expiry nears
3. We should **normalize for time-of-day** to distinguish signal from structural noise

```python
def time_of_day_gamma_weight(captured_at: datetime) -> float:
    """
    Weight factor that normalizes for expected intraday gamma growth.

    Early-day acceleration is weighted higher (more surprising).
    Late-day acceleration is weighted lower (more expected).
    """
    et = captured_at.astimezone(ZoneInfo("US/Eastern"))
    hour = et.hour + et.minute / 60

    if hour < 11:     # morning
        return 1.5    # acceleration here is notable
    elif hour < 13:   # midday
        return 1.0    # baseline
    elif hour < 14.5: # afternoon
        return 0.8    # some expected growth
    else:             # final 90 min
        return 0.5    # lots of structural gamma growth, discount it
```

---

## Signal Interface

```python
# 0dte/signals/gamma_decay_rate.py

class GammaDecayRate(Signal):
    """Signal 4: Rate of change of GEX per 15-min bar."""

    name = "gamma_decay_rate"
    table = "signal_gamma_decay"

    def compute(self, snapshot_id: int, db_conn):
        """
        1. Load contracts for this snapshot
        2. Compute total GEX and ATM GEX
        3. Look up prior bar's GEX and delta
        4. Compute delta (1st derivative) and acceleration (2nd derivative)
        5. Classify regime and detect spikes
        6. Write to signal_gamma_decay table
        """
        contracts = self._load_contracts(snapshot_id, db_conn)
        snapshot = self._load_snapshot(snapshot_id, db_conn)

        gex_data = compute_bar_gex(contracts, snapshot["underlying_price"])

        # Get prior bars for derivatives
        prior_bars = self._get_prior_bars(snapshot, db_conn, limit=2)

        # 1st derivative
        prior_gex = prior_bars[0]["total_gex"] if prior_bars else None
        gex_delta = compute_gex_delta(gex_data["total_gex"], prior_gex)

        # 2nd derivative
        prior_delta = prior_bars[0]["gex_delta"] if prior_bars and prior_bars[0]["gex_delta"] is not None else None
        gex_acceleration = compute_gex_acceleration(gex_delta, prior_delta)

        # Classify
        regime, is_spike = classify_acceleration_regime(
            gex_acceleration, gex_data["total_gex"]
        )

        db_conn.execute("""
            INSERT INTO signal_gamma_decay
                (snapshot_id, symbol, captured_at,
                 total_gex, atm_gex,
                 gex_delta, gex_acceleration,
                 acceleration_regime, is_spike)
            VALUES (%(sid)s, %(sym)s, %(time)s,
                    %(gex)s, %(atm)s,
                    %(delta)s, %(accel)s,
                    %(regime)s, %(spike)s)
        """, {
            "sid": snapshot_id,
            "sym": snapshot["symbol"],
            "time": snapshot["captured_at"],
            "gex": gex_data["total_gex"],
            "atm": gex_data["atm_gex"],
            "delta": gex_delta,
            "accel": gex_acceleration,
            "regime": regime,
            "spike": is_spike,
        })
        db_conn.commit()

    def _get_prior_bars(self, snapshot: dict, db_conn, limit: int = 2) -> list[dict]:
        """Get the N most recent prior bars for this trading day."""
        results = db_conn.execute("""
            SELECT sgd.total_gex, sgd.gex_delta, sgd.gex_acceleration
            FROM signal_gamma_decay sgd
            JOIN snapshots_0dte s ON s.id = sgd.snapshot_id
            WHERE s.symbol = %(symbol)s
              AND s.captured_at < %(current_time)s
              AND DATE(s.captured_at AT TIME ZONE 'US/Eastern') =
                  DATE(%(current_time)s AT TIME ZONE 'US/Eastern')
            ORDER BY s.captured_at DESC
            LIMIT %(limit)s
        """, {
            "symbol": snapshot["symbol"],
            "current_time": snapshot["captured_at"],
            "limit": limit,
        }).fetchall()
        return results
```

---

## Combining With Other Signals

The gamma decay rate signal is most powerful when combined:

### With OI Walls (Signal 3)
```
IF acceleration_regime = "accelerating" AND is_spike = true
AND price is within 0.5% of a major OI wall (from Signal 3)
THEN: high probability of mean reversion off that wall
```

### With Net Premium Flow (Signal 1)
```
IF acceleration is spiking (dealers dominating)
AND premium flow diverges from price
THEN: premium flow divergence is likely to resolve in the
      direction of the flow (dealers will force it)
```

### With IV Term Structure (Signal 2)
```
IF gamma acceleration is spiking
AND IV slope is steepening
THEN: the market is pricing in the dealer-driven move;
      momentum trades aligned with the slope have tailwinds
```

---

## Querying for Strategy Consumption

```sql
-- Find all spike bars today
SELECT s.captured_at, sgd.total_gex, sgd.gex_delta,
       sgd.gex_acceleration, sgd.acceleration_regime
FROM signal_gamma_decay sgd
JOIN snapshots_0dte s ON s.id = sgd.snapshot_id
WHERE s.symbol = '$SPX'
  AND DATE(s.captured_at AT TIME ZONE 'US/Eastern') = CURRENT_DATE
  AND sgd.is_spike = TRUE
ORDER BY s.captured_at;

-- Compare GEX acceleration to OI wall proximity for mean reversion setups
SELECT sgd.captured_at, sgd.gex_acceleration, sgd.is_spike,
       w.strike, w.wall_type, w.distance_from_spot
FROM signal_gamma_decay sgd
JOIN snapshots_0dte s ON s.id = sgd.snapshot_id
JOIN signal_oi_walls w ON w.snapshot_id = sgd.snapshot_id
WHERE sgd.is_spike = TRUE
  AND ABS(w.distance_from_spot) < 0.005  -- within 0.5% of spot
ORDER BY sgd.captured_at;
```

---

## Testing

### Unit Tests
- `compute_bar_gex()` with known gamma/OI values
- `compute_gex_delta()` first derivative math
- `compute_gex_acceleration()` second derivative math
- Regime classification for accelerating/decelerating/stable
- Spike detection at various thresholds
- Time-of-day weighting factors

### Integration Tests
- Full day backtest → verify acceleration spikes correspond to known volatile periods
- Chain: 3+ bars → verify delta and acceleration chain correctly

### Specific Scenarios to Test
```python
# Scenario: Gamma explosion in final hour
bars = [
    {"time": "14:00", "gex": 500_000_000},
    {"time": "14:15", "gex": 600_000_000},   # delta = +100M
    {"time": "14:30", "gex": 800_000_000},   # delta = +200M, accel = +100M
    {"time": "14:45", "gex": 1_200_000_000}, # delta = +400M, accel = +200M ← SPIKE
    {"time": "15:00", "gex": 1_500_000_000}, # delta = +300M, accel = -100M (peaking)
]
# Expected: spike at 14:45, regime = "accelerating"
# 15:00 regime = "decelerating" (still high GEX, but acceleration fading)
```

### Fixtures
- `tests/fixtures/gamma_spike_day.json` — Day with known 0DTE gamma explosion
- `tests/fixtures/gamma_stable_day.json` — Calm day with no spikes

---

## Milestone Checklist

- [ ] `compute_bar_gex()` correctly sums signed GEX for near-term contracts
- [ ] ATM GEX isolated at the nearest strike
- [ ] `compute_gex_delta()` tracks bar-over-bar change
- [ ] `compute_gex_acceleration()` produces correct 2nd derivative
- [ ] `classify_acceleration_regime()` labels all 3 regimes correctly
- [ ] Spike detection fires on acceleration exceeding 2x threshold
- [ ] `GammaDecayRate.compute()` writes to `signal_gamma_decay` table
- [ ] Prior bar lookups chain correctly (3+ bars needed for acceleration)
- [ ] Time-of-day weighting discounts structural late-day gamma growth
- [ ] Backtest produces acceleration time series for a full day
- [ ] Combined query with OI walls identifies mean reversion setups
