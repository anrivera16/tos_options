# Chunk 2: Net Premium Flow (Signal 1)

## Goal

Track the dollar-weighted difference between call and put premium hitting the ask vs. the bid on each 15-min bar. This reveals **directional conviction** — buyers hitting the ask are aggressively opening positions, sellers hitting the bid are liquidating. The cumulative flow line diverging from price action is a leading indicator.

---

## What This Signal Tells You

| Condition | Meaning |
|-----------|---------|
| Large call premium at ask | Aggressive call buying — bullish conviction |
| Large put premium at ask | Aggressive put buying — bearish conviction (or hedging) |
| Large call premium at bid | Call liquidation — bullish unwind |
| Large put premium at bid | Put liquidation — bearish unwind (or profit-taking) |
| Cumulative flow rising, price flat | Divergence — bullish pressure building |
| Cumulative flow falling, price rising | Divergence — rally losing conviction |

---

## Data Requirements

### From Schwab API / CSV

Each option contract needs:
- `bid`, `ask`, `last` — pricing
- `total_volume` — number of contracts traded
- `mark` — mid-market price (for dollar weighting)
- `put_call` — CALL or PUT

### Bid/Ask Classification Problem

**The challenge:** Schwab's option chain endpoint gives us `total_volume` but does NOT directly split volume into "traded at bid" vs "traded at ask." We need to classify trades.

**Approach — Last Price Proximity Method:**

```python
def classify_trade_side(bid: float, ask: float, last: float) -> str:
    """Classify whether the last trade was closer to bid or ask.

    This is a simplification. In production with streaming data,
    we'd use time-and-sales to classify each individual trade.
    For 15-min snapshots, we use the last trade price as a proxy.
    """
    if bid is None or ask is None or last is None:
        return "unknown"
    mid = (bid + ask) / 2
    if last >= mid:
        return "at_ask"    # buyer-initiated
    else:
        return "at_bid"    # seller-initiated
```

**Better approach for live mode (future enhancement):**
When we have streaming data via Schwab's websocket, classify each individual trade from the time-and-sales feed. The snapshot approach above is a reasonable approximation for 15-min bars.

**For backtest CSVs:**
Same classification — use the last/bid/ask relationship in each row.

---

## Computation Logic

### Per-Bar Calculation

For each 15-min snapshot:

```python
def compute_premium_flow(contracts: list[OptionContractRow],
                          underlying_price: float) -> dict:
    """
    Compute dollar-weighted premium flow for one 15-min bar.

    Dollar premium = volume × mark × 100 (contract multiplier)
    Split into bid/ask side using last price proximity.
    """
    call_at_ask = 0.0
    call_at_bid = 0.0
    put_at_ask = 0.0
    put_at_bid = 0.0

    for c in contracts:
        if c.total_volume is None or c.total_volume == 0:
            continue
        if c.mark is None or c.mark <= 0:
            continue

        dollar_premium = c.total_volume * c.mark * 100
        side = classify_trade_side(c.bid, c.ask, c.last)

        if c.put_call == "CALL":
            if side == "at_ask":
                call_at_ask += dollar_premium
            elif side == "at_bid":
                call_at_bid += dollar_premium
            else:
                # Split 50/50 if unknown
                call_at_ask += dollar_premium * 0.5
                call_at_bid += dollar_premium * 0.5
        else:  # PUT
            if side == "at_ask":
                put_at_ask += dollar_premium
            elif side == "at_bid":
                put_at_bid += dollar_premium
            else:
                put_at_ask += dollar_premium * 0.5
                put_at_bid += dollar_premium * 0.5

    # Net flow: positive = bullish pressure, negative = bearish
    net_flow = (call_at_ask - call_at_bid) - (put_at_ask - put_at_bid)

    return {
        "call_premium_at_ask": call_at_ask,
        "call_premium_at_bid": call_at_bid,
        "put_premium_at_ask": put_at_ask,
        "put_premium_at_bid": put_at_bid,
        "net_premium_flow": net_flow,
    }
```

### Cumulative Flow

Running sum from market open (09:30) to current bar:

```python
def compute_cumulative_flow(snapshot_id: int, db_conn) -> float:
    """Sum all net_premium_flow values for this trading day up to this bar."""
    result = db_conn.execute("""
        SELECT COALESCE(SUM(spf.net_premium_flow), 0) as cumulative
        FROM signal_premium_flow spf
        JOIN snapshots_0dte s ON s.id = spf.snapshot_id
        WHERE s.symbol = %(symbol)s
          AND DATE(s.captured_at AT TIME ZONE 'US/Eastern') = %(trade_date)s
          AND s.captured_at <= %(current_time)s
    """, params).fetchone()
    return result["cumulative"]
```

### Flow Velocity (Rate of Change)

```python
def compute_flow_velocity(current_flow: float, prior_flow: float | None) -> float | None:
    """Change in net flow from prior bar."""
    if prior_flow is None:
        return None
    return current_flow - prior_flow
```

---

## Divergence Detection

The most actionable signal from premium flow is **divergence** between the cumulative flow line and price:

```python
def detect_divergence(
    flow_series: list[dict],   # last N bars of {cumulative_flow, price}
    lookback: int = 4,         # number of bars to check (1 hour at 15-min)
) -> dict:
    """
    Detect divergence between cumulative premium flow and price.

    Bullish divergence: price flat/down, flow rising
    Bearish divergence: price flat/up, flow falling
    """
    if len(flow_series) < lookback:
        return {"divergence": "insufficient_data"}

    recent = flow_series[-lookback:]
    first, last = recent[0], recent[-1]

    price_change_pct = (last["price"] - first["price"]) / first["price"]
    flow_change = last["cumulative_flow"] - first["cumulative_flow"]

    # Thresholds (tunable)
    price_flat_threshold = 0.001  # 0.1% = essentially flat
    flow_significant = abs(first.get("cumulative_flow", 1)) * 0.1  # 10% change

    if abs(price_change_pct) < price_flat_threshold and flow_change > flow_significant:
        return {"divergence": "bullish", "flow_delta": flow_change, "price_delta_pct": price_change_pct}
    elif abs(price_change_pct) < price_flat_threshold and flow_change < -flow_significant:
        return {"divergence": "bearish", "flow_delta": flow_change, "price_delta_pct": price_change_pct}
    elif price_change_pct > price_flat_threshold and flow_change < -flow_significant:
        return {"divergence": "bearish", "flow_delta": flow_change, "price_delta_pct": price_change_pct}
    elif price_change_pct < -price_flat_threshold and flow_change > flow_significant:
        return {"divergence": "bullish", "flow_delta": flow_change, "price_delta_pct": price_change_pct}
    else:
        return {"divergence": "none", "flow_delta": flow_change, "price_delta_pct": price_change_pct}
```

---

## Signal Interface

```python
# 0dte/signals/net_premium_flow.py

from 0dte.signals.base import Signal

class NetPremiumFlow(Signal):
    """Signal 1: Dollar-weighted bid/ask premium flow."""

    name = "net_premium_flow"
    table = "signal_premium_flow"

    def compute(self, snapshot_id: int, db_conn):
        """
        1. Load contracts for this snapshot
        2. Compute per-bar premium flow
        3. Compute cumulative flow for the day
        4. Compute velocity vs prior bar
        5. Write to signal_premium_flow table
        """
        contracts = self._load_contracts(snapshot_id, db_conn)
        snapshot = self._load_snapshot(snapshot_id, db_conn)

        flow = compute_premium_flow(contracts, snapshot["underlying_price"])
        cumulative = compute_cumulative_flow(snapshot_id, db_conn)
        prior = self._get_prior_bar_flow(snapshot, db_conn)
        velocity = compute_flow_velocity(flow["net_premium_flow"], prior)

        db_conn.execute("""
            INSERT INTO signal_premium_flow
                (snapshot_id, symbol, captured_at,
                 call_premium_at_ask, call_premium_at_bid,
                 put_premium_at_ask, put_premium_at_bid,
                 net_premium_flow, cumulative_flow,
                 flow_velocity, price_at_bar)
            VALUES (%(snapshot_id)s, %(symbol)s, %(captured_at)s,
                    %(call_at_ask)s, %(call_at_bid)s,
                    %(put_at_ask)s, %(put_at_bid)s,
                    %(net_flow)s, %(cumulative)s,
                    %(velocity)s, %(price)s)
        """, {
            "snapshot_id": snapshot_id,
            "symbol": snapshot["symbol"],
            "captured_at": snapshot["captured_at"],
            "call_at_ask": flow["call_premium_at_ask"],
            "call_at_bid": flow["call_premium_at_bid"],
            "put_at_ask": flow["put_premium_at_ask"],
            "put_at_bid": flow["put_premium_at_bid"],
            "net_flow": flow["net_premium_flow"],
            "cumulative": cumulative + flow["net_premium_flow"],
            "velocity": velocity,
            "price": snapshot["underlying_price"],
        })
        db_conn.commit()
```

---

## Signal Base Class

```python
# 0dte/signals/base.py

from abc import ABC, abstractmethod

class Signal(ABC):
    """Base class for all 0DTE signals."""

    name: str
    table: str

    @abstractmethod
    def compute(self, snapshot_id: int, db_conn):
        """Compute signal for a given snapshot and write results to DB."""
        ...

    def _load_contracts(self, snapshot_id: int, db_conn) -> list[dict]:
        """Load all contracts for a snapshot from the DB."""
        return db_conn.execute(
            "SELECT * FROM contracts_0dte WHERE snapshot_id = %s",
            [snapshot_id]
        ).fetchall()

    def _load_snapshot(self, snapshot_id: int, db_conn) -> dict:
        """Load snapshot metadata."""
        return db_conn.execute(
            "SELECT * FROM snapshots_0dte WHERE id = %s",
            [snapshot_id]
        ).fetchone()
```

---

## Volume Considerations

### Volume Delta Problem

When using 15-min snapshots (not streaming), `total_volume` is cumulative for the day. To get per-bar volume:

```python
def compute_bar_volume(current_volume: int, prior_volume: int | None) -> int:
    """Get volume for just this 15-min bar by differencing cumulative volume."""
    if prior_volume is None:
        return current_volume  # first bar of day
    return max(0, current_volume - prior_volume)
```

This is critical — without differencing, we'd overcount premium as the day progresses.

**Implementation:** When computing premium flow, look up the prior snapshot's contracts for the same option symbol and difference the volumes before dollar-weighting.

---

## Filtering

Focus the premium flow signal on **liquid, relevant contracts**:

```python
PREMIUM_FLOW_FILTERS = {
    "max_dte": 7,          # Only 0DTE through weekly expiry
    "min_volume": 10,       # Skip illiquid contracts
    "min_open_interest": 100,  # Skip newly listed strikes
    "strike_range_pct": 0.10,  # Only strikes within ±10% of spot
}
```

---

## Testing

### Unit Tests
- Classification of bid/ask side with known bid/ask/last combos
- Premium flow computation with mock contracts
- Volume differencing logic
- Divergence detection with synthetic time series

### Integration Tests
- Load fixture CSV → run pipeline with NetPremiumFlow signal → query results
- Verify cumulative flow sums correctly across bars
- Verify velocity tracks bar-over-bar changes

### Fixture
- `tests/fixtures/premium_flow_day.csv` — Full day of SPX contracts with known volume patterns

---

## Milestone Checklist

- [ ] `classify_trade_side()` correctly splits volume
- [ ] `compute_premium_flow()` produces dollar-weighted flow per bar
- [ ] Volume differencing handles first bar + subsequent bars
- [ ] Cumulative flow sums correctly across a full day
- [ ] Velocity tracks bar-over-bar changes
- [ ] Divergence detection flags bullish/bearish conditions
- [ ] `NetPremiumFlow.compute()` writes to `signal_premium_flow` table
- [ ] Backtest produces flow time series for a full CSV day
