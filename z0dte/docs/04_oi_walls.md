# Chunk 4: Put/Call OI Walls as Dynamic Support/Resistance (Signal 3)

## Goal

Track the strikes with the **highest open interest concentration** and update them intraday as volume builds. As price approaches a massive call OI wall, dealers who are short those calls hedge by buying stock (creating resistance). The inverse for puts (dealers sell stock near put walls, creating support). Overlay these levels on the 15-min chart as **moving S/R lines**.

---

## What This Signal Tells You

| Condition | Meaning |
|-----------|---------|
| Price approaching large call OI wall from below | Resistance — dealer delta hedging creates selling pressure |
| Price approaching large put OI wall from above | Support — dealer delta hedging creates buying pressure |
| OI wall shifting intraday (new strike accumulating) | Market repositioning — new magnet forming |
| Price breaking through an OI wall | Gamma squeeze potential — dealers forced to chase |
| Both call and put walls tightening around spot | Pin risk — price may get trapped between walls |

### Dealer Hedging Mechanics

```
Scenario: Huge call OI at 5100 strike, spot at 5080

1. Market makers sold those 5100 calls to customers
2. As spot rises toward 5100, those calls gain delta
3. To stay delta-neutral, dealers must BUY stock
4. But at 5100, gamma is at maximum — small price moves = large delta changes
5. Net effect: dealers buying below 5100 slows the advance (resistance)
6. IF price breaks through 5100, dealers must buy MORE aggressively (gamma squeeze)

Inverse for puts: Dealers who sold puts must SELL stock as price falls toward put walls.
```

---

## Data Requirements

### From Each Snapshot

For every 15-min bar, per option contract:
- `strike` — strike price
- `put_call` — CALL or PUT
- `open_interest` — number of open contracts
- `total_volume` — contracts traded (for intraday accumulation tracking)
- `expiration_date` — to focus on near-term expiries
- `gamma` — for weighting wall significance by gamma impact
- `delta` — for dealer hedge direction

### Filtering

```python
OI_WALL_FILTERS = {
    "max_dte": 7,              # Focus on 0DTE through weekly
    "strike_range_pct": 0.05,  # Only strikes within ±5% of spot
    "min_oi_threshold": 500,   # Minimum OI to be considered a "wall"
}
```

---

## Computation Logic

### Step 1: Aggregate OI by Strike

```python
def aggregate_oi_by_strike(
    contracts: list[dict],
    underlying_price: float,
    max_dte: int = 7,
    strike_range_pct: float = 0.05,
) -> list[dict]:
    """
    Aggregate open interest at each strike, split by call/put.

    Only includes strikes within range and near-term expiries.
    """
    strike_min = underlying_price * (1 - strike_range_pct)
    strike_max = underlying_price * (1 + strike_range_pct)

    # Filter relevant contracts
    relevant = [
        c for c in contracts
        if c["dte"] is not None and c["dte"] <= max_dte
        and strike_min <= c["strike"] <= strike_max
        and c["open_interest"] is not None and c["open_interest"] > 0
    ]

    # Group by strike
    by_strike = defaultdict(lambda: {
        "call_oi": 0, "put_oi": 0,
        "call_volume": 0, "put_volume": 0,
        "total_oi": 0,
    })

    for c in relevant:
        s = by_strike[c["strike"]]
        oi = c["open_interest"] or 0
        vol = c["total_volume"] or 0

        if c["put_call"] == "CALL":
            s["call_oi"] += oi
            s["call_volume"] += vol
        else:
            s["put_oi"] += oi
            s["put_volume"] += vol
        s["total_oi"] += oi

    # Convert to list
    results = []
    for strike, data in sorted(by_strike.items()):
        if data["total_oi"] < OI_WALL_FILTERS["min_oi_threshold"]:
            continue
        data["strike"] = strike
        results.append(data)

    return results
```

### Step 2: Classify Wall Type and Strength

```python
def classify_walls(
    strike_data: list[dict],
    underlying_price: float,
) -> list[dict]:
    """
    Classify each strike as a call wall, put wall, or mixed.
    Compute relative strength (0-1 normalized to day's max).
    Determine dealer hedge direction.
    """
    if not strike_data:
        return []

    max_oi = max(d["total_oi"] for d in strike_data)

    for d in strike_data:
        strike = d["strike"]

        # Wall type: dominant side
        if d["call_oi"] > d["put_oi"] * 2:
            d["wall_type"] = "call_wall"
        elif d["put_oi"] > d["call_oi"] * 2:
            d["wall_type"] = "put_wall"
        else:
            d["wall_type"] = "mixed"

        # Strength: normalized to max OI in this snapshot
        d["wall_strength"] = d["total_oi"] / max_oi if max_oi > 0 else 0

        # Distance from spot
        d["distance_from_spot"] = (strike - underlying_price) / underlying_price

        # Dealer hedge direction
        # Call wall above spot: dealers short calls → buy stock as price rises → resistance
        # Put wall below spot: dealers short puts → sell stock as price falls → support
        if d["wall_type"] == "call_wall":
            d["dealer_hedge_direction"] = "buying_stock"   # resistance
        elif d["wall_type"] == "put_wall":
            d["dealer_hedge_direction"] = "selling_stock"  # support
        else:
            # Mixed: net direction depends on which side dominates
            if d["call_oi"] > d["put_oi"]:
                d["dealer_hedge_direction"] = "buying_stock"
            else:
                d["dealer_hedge_direction"] = "selling_stock"

    return strike_data
```

### Step 3: Identify Top Walls

```python
def identify_top_walls(
    classified_strikes: list[dict],
    top_n: int = 5,
) -> dict:
    """
    Pick the most significant walls for overlay on the chart.

    Returns:
    - top_call_walls: strongest call OI concentrations (resistance)
    - top_put_walls: strongest put OI concentrations (support)
    - pin_range: if both call and put walls are nearby, the pin zone
    """
    call_walls = sorted(
        [s for s in classified_strikes if s["wall_type"] == "call_wall"],
        key=lambda s: s["call_oi"],
        reverse=True,
    )[:top_n]

    put_walls = sorted(
        [s for s in classified_strikes if s["wall_type"] == "put_wall"],
        key=lambda s: s["put_oi"],
        reverse=True,
    )[:top_n]

    # Pin range detection: nearest call wall above + nearest put wall below
    call_above = [s for s in call_walls if s["distance_from_spot"] > 0]
    put_below = [s for s in put_walls if s["distance_from_spot"] < 0]

    pin_range = None
    if call_above and put_below:
        nearest_call = min(call_above, key=lambda s: s["distance_from_spot"])
        nearest_put = max(put_below, key=lambda s: s["distance_from_spot"])
        pin_width = nearest_call["strike"] - nearest_put["strike"]

        pin_range = {
            "upper_bound": nearest_call["strike"],
            "lower_bound": nearest_put["strike"],
            "width": pin_width,
            "width_pct": pin_width / ((nearest_call["strike"] + nearest_put["strike"]) / 2),
        }

    return {
        "top_call_walls": call_walls,
        "top_put_walls": put_walls,
        "pin_range": pin_range,
    }
```

---

## Intraday Wall Drift Tracking

OI is technically end-of-day data — it doesn't update intraday. But **volume** does. High volume at a strike during the day suggests OI is building there. We track this to detect walls forming in real time:

```python
def compute_intraday_oi_estimate(
    current_oi: int,
    bar_volume: int,
    prior_bar_volume: int | None,
) -> int:
    """
    Estimate intraday OI by adding net new volume.

    Simplification: assume 60% of volume is opening (adds to OI)
    and 40% is closing (subtracts). This is a rough heuristic.
    More sophisticated: use Schwab's transaction-level data if available.
    """
    if prior_bar_volume is None:
        volume_delta = bar_volume
    else:
        volume_delta = max(0, bar_volume - prior_bar_volume)

    estimated_new_oi = int(volume_delta * 0.6)  # 60% opening assumption
    return current_oi + estimated_new_oi
```

### Wall Movement Detection

```python
def detect_wall_movement(
    current_walls: dict,
    prior_walls: dict | None,
) -> list[dict]:
    """
    Compare current top walls to prior bar's walls.
    Flag strikes that are newly appearing or growing significantly.
    """
    if prior_walls is None:
        return []

    events = []
    prior_strikes = {w["strike"]: w for w in prior_walls.get("top_call_walls", [])}
    prior_strikes.update({w["strike"]: w for w in prior_walls.get("top_put_walls", [])})

    for wall in current_walls.get("top_call_walls", []) + current_walls.get("top_put_walls", []):
        strike = wall["strike"]
        if strike not in prior_strikes:
            events.append({
                "type": "new_wall",
                "strike": strike,
                "wall_type": wall["wall_type"],
                "oi": wall["total_oi"],
            })
        else:
            prior = prior_strikes[strike]
            oi_change = wall["total_oi"] - prior["total_oi"]
            if abs(oi_change) > prior["total_oi"] * 0.1:  # 10% change
                events.append({
                    "type": "wall_growing" if oi_change > 0 else "wall_shrinking",
                    "strike": strike,
                    "wall_type": wall["wall_type"],
                    "oi_change": oi_change,
                })

    return events
```

---

## Integration with Existing GEX

The existing `gex/calculations.py` already computes:
- `_signed_gamma_exposure()` per contract
- `compute_gex_levels()` → top N strikes by abs GEX
- `summarize_top_walls()` → largest call/put walls

**Key difference in this signal:**
- Existing GEX code works on a single snapshot for a report
- This signal tracks **wall evolution over time** (15-min series)
- This signal adds **dealer hedge direction** and **pin range detection**
- This signal includes **intraday volume accumulation** as a proxy for OI changes

**Reuse opportunity:** We can call `_signed_gamma_exposure()` and `_contract_metrics()` from `gex/calculations.py` to gamma-weight the OI walls, making them more accurate than pure OI count.

---

## Signal Interface

```python
# 0dte/signals/oi_walls.py

class OIWalls(Signal):
    """Signal 3: Dynamic OI-based support/resistance levels."""

    name = "oi_walls"
    table = "signal_oi_walls"

    def compute(self, snapshot_id: int, db_conn):
        """
        1. Load contracts for this snapshot
        2. Aggregate OI by strike
        3. Classify walls and compute strength
        4. Write all significant strikes to signal_oi_walls table
        """
        contracts = self._load_contracts(snapshot_id, db_conn)
        snapshot = self._load_snapshot(snapshot_id, db_conn)
        underlying_price = snapshot["underlying_price"]

        # Aggregate and classify
        strike_data = aggregate_oi_by_strike(contracts, underlying_price)
        classified = classify_walls(strike_data, underlying_price)

        # Batch insert all wall strikes
        for wall in classified:
            db_conn.execute("""
                INSERT INTO signal_oi_walls
                    (snapshot_id, symbol, captured_at, strike,
                     call_oi, put_oi, total_oi,
                     call_volume, put_volume,
                     wall_type, wall_strength,
                     dealer_hedge_direction, distance_from_spot)
                VALUES (%(sid)s, %(sym)s, %(time)s, %(strike)s,
                        %(coi)s, %(poi)s, %(toi)s,
                        %(cvol)s, %(pvol)s,
                        %(wtype)s, %(wstr)s,
                        %(hedge)s, %(dist)s)
            """, {
                "sid": snapshot_id,
                "sym": snapshot["symbol"],
                "time": snapshot["captured_at"],
                "strike": wall["strike"],
                "coi": wall["call_oi"],
                "poi": wall["put_oi"],
                "toi": wall["total_oi"],
                "cvol": wall.get("call_volume", 0),
                "pvol": wall.get("put_volume", 0),
                "wtype": wall["wall_type"],
                "wstr": wall["wall_strength"],
                "hedge": wall["dealer_hedge_direction"],
                "dist": wall["distance_from_spot"],
            })

        db_conn.commit()
```

---

## Querying Walls for Chart Overlay

```sql
-- Get top walls for the most recent snapshot
SELECT strike, wall_type, wall_strength, dealer_hedge_direction, total_oi
FROM signal_oi_walls
WHERE snapshot_id = (
    SELECT id FROM snapshots_0dte
    WHERE symbol = '$SPX'
    ORDER BY captured_at DESC LIMIT 1
)
ORDER BY wall_strength DESC
LIMIT 10;

-- Track how a specific wall evolved throughout the day
SELECT s.captured_at, w.total_oi, w.wall_strength, w.call_volume + w.put_volume as total_vol
FROM signal_oi_walls w
JOIN snapshots_0dte s ON s.id = w.snapshot_id
WHERE w.strike = 5100
  AND DATE(s.captured_at AT TIME ZONE 'US/Eastern') = '2024-03-15'
ORDER BY s.captured_at;
```

---

## Testing

### Unit Tests
- OI aggregation with known contract sets
- Wall classification (call-dominant, put-dominant, mixed)
- Strength normalization (max = 1.0)
- Dealer hedge direction logic
- Pin range detection (both sides present, one side only)
- Wall movement detection (new, growing, shrinking)

### Integration Tests
- Full day backtest → verify wall levels match expected S/R zones
- Pin range narrows → price stays pinned (correlation check on historical data)

### Fixtures
- `tests/fixtures/oi_walls_pinned.json` — Snapshot with tight call/put walls around spot
- `tests/fixtures/oi_walls_breakout.json` — Snapshot with walls far from spot

---

## Milestone Checklist

- [ ] `aggregate_oi_by_strike()` correctly sums OI across expiries
- [ ] `classify_walls()` labels call/put/mixed correctly
- [ ] `wall_strength` normalized to 0-1 range
- [ ] `dealer_hedge_direction` correct for call walls (buying) and put walls (selling)
- [ ] `identify_top_walls()` picks meaningful levels
- [ ] Pin range detection works when walls bracket spot
- [ ] `OIWalls.compute()` writes to `signal_oi_walls` table
- [ ] Wall evolution query shows OI changes across bars
- [ ] Backtest produces wall time series for a full day
