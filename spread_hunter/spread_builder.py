"""
Spread Builder — constructs spread candidates from option chain data in the DB.

Reads the latest snapshot per ticker, groups contracts, then pairs legs into:
  - Bull Put Credit spreads
  - Bear Call Credit spreads
  - Iron Condors
  - Iron Flys
  - Calendar spreads
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from spread_hunter.signal_filters import run_all_filters
from spread_hunter.spread_types import (
    AnySpread,
    CalendarSpread,
    IronCondor,
    IronFly,
    Leg,
    SignalFilter,
    VerticalSpread,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class SpreadHunterConfig:
    """Tunable knobs for the spread hunter."""

    # Liquidity filters (per leg)
    min_oi: int = 50
    min_volume: int = 10
    max_bid_ask_spread_pct: float = 25.0

    # DTE range
    min_dte: int = 1
    max_dte: int = 45

    # Strike width (auto if None — uses ~0.7% of underlying)
    min_strike_width: float | None = None
    max_strike_width: float | None = None

    # Min ROI to include
    min_roi_pct: float = 10.0

    # Max results per spread type per ticker
    max_per_type: int = 20

    # Iron condor: require roughly symmetric wings (within this factor)
    ic_symmetry_factor: float = 2.0

    # Calendar: max DTE gap between near and far leg
    calendar_max_dte_gap: int = 30

    # Iron fly: how far from ATM is acceptable for center strike (as %)
    iron_fly_atm_tolerance_pct: float = 1.0


def auto_width(underlying_price: float) -> tuple[float, float]:
    """Return (min_width, max_width) based on underlying price."""
    # ~0.7% of price as target width
    base = round(underlying_price * 0.007, 1)
    base = max(base, 1.0)
    # Snap to common widths
    for w in [0.5, 1, 2.5, 5, 10, 15, 25, 50]:
        if w >= base:
            base = w
            break
    min_w = base
    max_w = base * 3
    return min_w, max_w


# ---------------------------------------------------------------------------
# DB query
# ---------------------------------------------------------------------------

def _snapshot_subquery(is_pg: bool) -> str:
    """SQL subquery to get latest snapshot IDs per ticker.
    
    Uses the most recent snapshot for each symbol regardless of age,
    so spread hunting works even after market hours or during gaps.
    """
    if is_pg:
        return """
            SELECT id FROM snapshots s1
            WHERE captured_at = (
                SELECT MAX(s2.captured_at)
                FROM snapshots s2
                WHERE s2.symbol = s1.symbol
            )
        """
    return """
        SELECT id FROM snapshots s1
        WHERE captured_at = (
            SELECT MAX(s2.captured_at)
            FROM snapshots s2
            WHERE s2.symbol = s1.symbol
        )
    """


def fetch_contracts(
    conn: Any,
    tickers: list[str] | None = None,
    is_pg: bool = False,
) -> list[dict[str, Any]]:
    """Fetch option contracts from latest snapshot per ticker."""
    ph = "%s" if is_pg else "?"
    subq = _snapshot_subquery(is_pg)

    ticker_clause = ""
    params: list = []
    if tickers:
        placeholders = ", ".join(ph for _ in tickers)
        ticker_clause = f"AND oc.underlying_symbol IN ({placeholders})"
        params = list(tickers)

    query = f"""
        SELECT
            oc.underlying_symbol,
            s.underlying_price,
            oc.strike,
            oc.put_call,
            oc.expiration_date,
            oc.dte,
            oc.bid,
            oc.ask,
            oc.mark,
            oc.delta,
            oc.gamma,
            oc.theta,
            oc.vega,
            oc.volatility,
            oc.total_volume,
            oc.open_interest
        FROM option_contracts oc
        JOIN snapshots s ON oc.snapshot_id = s.id
        WHERE s.id IN ({subq})
        AND oc.delta IS NOT NULL
        AND oc.volatility IS NOT NULL
        {ticker_clause}
        ORDER BY oc.underlying_symbol, oc.dte, oc.strike, oc.put_call
    """

    cur = conn.cursor()
    cur.execute(query, params)
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    return rows


# ---------------------------------------------------------------------------
# Historical data queries (for signal filters)
# ---------------------------------------------------------------------------

def fetch_price_history(
    conn: Any,
    ticker: str,
    lookback_days: int = 30,
    is_pg: bool = False,
) -> list[float]:
    """Fetch recent underlying prices from snapshots for SMA calc.
    Returns one price per day (latest snapshot of each day), oldest first.
    """
    ph = "%s" if is_pg else "?"
    if is_pg:
        query = f"""
            SELECT DISTINCT ON (captured_at::date)
                underlying_price, captured_at::date as day
            FROM snapshots
            WHERE symbol = {ph}
            AND captured_at >= NOW() - INTERVAL '1 day' * {ph}
            AND underlying_price IS NOT NULL
            ORDER BY captured_at::date, captured_at DESC
        """
    else:
        query = f"""
            SELECT underlying_price, DATE(captured_at) as day
            FROM (
                SELECT underlying_price, DATE(captured_at) as day,
                       ROW_NUMBER() OVER(PARTITION BY DATE(captured_at) ORDER BY captured_at DESC) as rn
                FROM snapshots
                WHERE symbol = {ph}
                AND captured_at >= datetime('now', '-' || {ph} || ' days')
                AND underlying_price IS NOT NULL
            )
            WHERE rn = 1
            ORDER BY day
        """
    cur = conn.cursor()
    cur.execute(query, [ticker, lookback_days])
    return [float(row[0]) for row in cur.fetchall() if row[0]]


def fetch_atm_iv_history(
    conn: Any,
    ticker: str,
    lookback_days: int = 30,
    is_pg: bool = False,
) -> list[float]:
    """
    Fetch historical ATM IV values for IV rank calculation.
    Gets the IV of the nearest-to-ATM put for each snapshot.
    """
    ph = "%s" if is_pg else "?"
    if is_pg:
        query = f"""
            SELECT oc.volatility
            FROM (
                SELECT oc.volatility,
                       ABS(oc.strike - s.underlying_price) as dist,
                       s.captured_at,
                       ROW_NUMBER() OVER(
                           PARTITION BY s.id
                           ORDER BY ABS(oc.strike - s.underlying_price)
                       ) as rn
                FROM option_contracts oc
                JOIN snapshots s ON oc.snapshot_id = s.id
                WHERE s.symbol = {ph}
                AND oc.put_call = 'PUT'
                AND oc.volatility IS NOT NULL
                AND s.underlying_price IS NOT NULL
                AND s.captured_at >= NOW() - INTERVAL '1 day' * {ph}
            ) oc
            WHERE rn = 1
            ORDER BY captured_at
        """
    else:
        query = f"""
            SELECT oc.volatility
            FROM (
                SELECT oc.volatility,
                       ABS(oc.strike - s.underlying_price) as dist,
                       s.captured_at,
                       ROW_NUMBER() OVER(
                           PARTITION BY s.id
                           ORDER BY ABS(oc.strike - s.underlying_price)
                       ) as rn
                FROM option_contracts oc
                JOIN snapshots s ON oc.snapshot_id = s.id
                WHERE s.symbol = {ph}
                AND oc.put_call = 'PUT'
                AND oc.volatility IS NOT NULL
                AND s.underlying_price IS NOT NULL
                AND s.captured_at >= datetime('now', '-' || {ph} || ' days')
            ) oc
            WHERE rn = 1
            ORDER BY captured_at
        """
    cur = conn.cursor()
    cur.execute(query, [ticker, lookback_days])
    return [float(row[0]) for row in cur.fetchall() if row[0]]


def fetch_strike_oi(
    conn: Any,
    ticker: str,
    put_call: str = "PUT",
    is_pg: bool = False,
) -> dict[float, int]:
    """
    Fetch total OI by strike for support/resistance detection.
    Uses the latest snapshot.
    """
    ph = "%s" if is_pg else "?"
    subq = _snapshot_subquery(is_pg)
    query = f"""
        SELECT oc.strike, SUM(oc.open_interest) as total_oi
        FROM option_contracts oc
        JOIN snapshots s ON oc.snapshot_id = s.id
        WHERE s.id IN ({subq})
        AND oc.underlying_symbol = {ph}
        AND oc.put_call = {ph}
        AND oc.open_interest IS NOT NULL
        GROUP BY oc.strike
        ORDER BY oc.strike
    """
    cur = conn.cursor()
    cur.execute(query, [ticker, put_call])
    return {float(row[0]): int(row[1]) for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_leg(row: dict[str, Any]) -> Leg:
    """Convert a DB row dict to a Leg."""
    return Leg(
        symbol=row["underlying_symbol"],
        strike=float(row["strike"] or 0),
        put_call=row["put_call"],
        expiration_date=row["expiration_date"],
        dte=int(row["dte"] or 0),
        bid=_f(row.get("bid")),
        ask=_f(row.get("ask")),
        mark=_f(row.get("mark")),
        delta=_f(row.get("delta")),
        gamma=_f(row.get("gamma")),
        theta=_f(row.get("theta")),
        vega=_f(row.get("vega")),
        iv=_f(row.get("volatility")),
        volume=_i(row.get("total_volume")),
        open_interest=_i(row.get("open_interest")),
    )


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _mark(leg: Leg) -> float:
    """Get mark price, fallback to mid of bid/ask, then to bid."""
    if leg.mark and leg.mark > 0:
        return leg.mark
    bid = leg.bid or 0
    ask = leg.ask or 0
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    return bid or 0


def _passes_liquidity(leg: Leg, config: SpreadHunterConfig) -> bool:
    """Check if a leg meets minimum liquidity thresholds."""
    oi = leg.open_interest or 0
    vol = leg.volume or 0
    if oi < config.min_oi:
        return False
    if vol < config.min_volume:
        return False
    if leg.bid_ask_spread_pct() > config.max_bid_ask_spread_pct:
        return False
    return True


# ---------------------------------------------------------------------------
# Contract grouping
# ---------------------------------------------------------------------------

def group_contracts(
    contracts: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, list[Leg]]]]:
    """
    Group legs by underlying -> expiration -> put_call.

    Returns: {underlying: {expiration: {"CALL": [Leg, ...], "PUT": [Leg, ...]}}}
    """
    groups: dict[str, dict[str, dict[str, list[Leg]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for row in contracts:
        leg = _row_to_leg(row)
        groups[leg.symbol][leg.expiration_date][leg.put_call].append(leg)
    return groups


# ---------------------------------------------------------------------------
# Vertical spreads (bull put credit, bear call credit)
# ---------------------------------------------------------------------------

def _build_bull_put_credits(
    puts: list[Leg],
    underlying_price: float,
    config: SpreadHunterConfig,
    signal_filter: "SignalFilter | None" = None,
) -> list[VerticalSpread]:
    """
    Bull put credit: SELL higher-strike put, BUY lower-strike put.
    Both OTM (strike < underlying_price).
    """
    if underlying_price <= 0:
        return []

    min_w, max_w = config.min_strike_width or 0, config.max_strike_width or 9999
    if config.min_strike_width is None:
        min_w, max_w = auto_width(underlying_price)

    # Filter to OTM puts only, sorted by strike descending
    otm_puts = sorted(
        [p for p in puts if p.strike < underlying_price],
        key=lambda p: p.strike,
        reverse=True,
    )

    # Delta bounds for the SHORT leg (tight range from signal filter)
    d_lo = signal_filter.delta_min if signal_filter else 0.10
    d_hi = signal_filter.delta_max if signal_filter else 0.25

    results: list[VerticalSpread] = []
    for i, short_put in enumerate(otm_puts):
        # Tight delta filter on the SHORT leg
        if not (d_lo <= abs(short_put.delta or 0) <= d_hi):
            continue
        if not _passes_liquidity(short_put, config):
            continue
        for long_put in otm_puts[i + 1:]:
            width = short_put.strike - long_put.strike
            if width < min_w:
                continue
            if width > max_w:
                break  # further legs are even wider
            if not _passes_liquidity(long_put, config):
                continue

            short_mark = _mark(short_put)
            long_mark = _mark(long_put)
            if short_mark <= 0 or long_mark <= 0:
                continue

            credit = short_mark - long_mark
            if credit <= 0:
                continue

            max_loss = width - credit
            if max_loss <= 0:
                continue

            roi = (credit / max_loss) * 100.0
            if roi < config.min_roi_pct:
                continue

            breakeven = short_put.strike - credit

            net_delta = _safe_add(short_put.delta, long_put.delta)
            net_theta = _safe_add(short_put.theta, long_put.theta)
            net_vega = _safe_add(short_put.vega, long_put.vega)

            results.append(VerticalSpread(
                spread_type="bull_put_credit",
                underlying=short_put.symbol,
                underlying_price=underlying_price,
                short_leg=short_put,
                long_leg=long_put,
                strike_width=width,
                expiration_date=short_put.expiration_date,
                dte=short_put.dte,
                net_premium=credit,
                max_profit=credit,
                max_loss=max_loss,
                breakeven=breakeven,
                roi_pct=round(roi, 1),
                net_delta=net_delta,
                net_theta=net_theta,
                net_vega=net_vega,
                min_oi=min(short_put.open_interest or 0, long_put.open_interest or 0),
                min_volume=min(short_put.volume or 0, long_put.volume or 0),
                max_spread_pct=max(
                    short_put.bid_ask_spread_pct(),
                    long_put.bid_ask_spread_pct(),
                ),
            ))

    return results


def _build_bear_call_credits(
    calls: list[Leg],
    underlying_price: float,
    config: SpreadHunterConfig,
    signal_filter: "SignalFilter | None" = None,
) -> list[VerticalSpread]:
    """
    Bear call credit: SELL lower-strike call, BUY higher-strike call.
    Both OTM (strike > underlying_price).
    """
    if underlying_price <= 0:
        return []

    min_w, max_w = config.min_strike_width or 0, config.max_strike_width or 9999
    if config.min_strike_width is None:
        min_w, max_w = auto_width(underlying_price)

    # Filter to OTM calls only, sorted by strike ascending
    otm_calls = sorted(
        [c for c in calls if c.strike > underlying_price],
        key=lambda c: c.strike,
    )

    # Delta bounds for the SHORT leg (tight range from signal filter)
    d_lo = signal_filter.delta_min if signal_filter else 0.10
    d_hi = signal_filter.delta_max if signal_filter else 0.25

    results: list[VerticalSpread] = []
    for i, short_call in enumerate(otm_calls):
        # Tight delta filter on the SHORT leg
        if not (d_lo <= abs(short_call.delta or 0) <= d_hi):
            continue
        if not _passes_liquidity(short_call, config):
            continue
        for long_call in otm_calls[i + 1:]:
            width = long_call.strike - short_call.strike
            if width < min_w:
                continue
            if width > max_w:
                break
            if not _passes_liquidity(long_call, config):
                continue

            short_mark = _mark(short_call)
            long_mark = _mark(long_call)
            if short_mark <= 0 or long_mark <= 0:
                continue

            credit = short_mark - long_mark
            if credit <= 0:
                continue

            max_loss = width - credit
            if max_loss <= 0:
                continue

            roi = (credit / max_loss) * 100.0
            if roi < config.min_roi_pct:
                continue

            breakeven = short_call.strike + credit

            net_delta = _safe_add(short_call.delta, long_call.delta)
            net_theta = _safe_add(short_call.theta, long_call.theta)
            net_vega = _safe_add(short_call.vega, long_call.vega)

            results.append(VerticalSpread(
                spread_type="bear_call_credit",
                underlying=short_call.symbol,
                underlying_price=underlying_price,
                short_leg=short_call,
                long_leg=long_call,
                strike_width=width,
                expiration_date=short_call.expiration_date,
                dte=short_call.dte,
                net_premium=credit,
                max_profit=credit,
                max_loss=max_loss,
                breakeven=breakeven,
                roi_pct=round(roi, 1),
                net_delta=net_delta,
                net_theta=net_theta,
                net_vega=net_vega,
                min_oi=min(short_call.open_interest or 0, long_call.open_interest or 0),
                min_volume=min(short_call.volume or 0, long_call.volume or 0),
                max_spread_pct=max(
                    short_call.bid_ask_spread_pct(),
                    long_call.bid_ask_spread_pct(),
                ),
            ))

    return results


# ---------------------------------------------------------------------------
# Iron Condor
# ---------------------------------------------------------------------------

def _build_iron_condors(
    bull_puts: list[VerticalSpread],
    bear_calls: list[VerticalSpread],
    underlying_price: float,
    config: SpreadHunterConfig,
) -> list[IronCondor]:
    """
    Combine bull put credit + bear call credit into iron condors.
    Same expiration, roughly symmetric wings.
    """
    results: list[IronCondor] = []

    # Index by expiration for fast lookup
    puts_by_exp: dict[str, list[VerticalSpread]] = defaultdict(list)
    for bp in bull_puts:
        puts_by_exp[bp.expiration_date].append(bp)

    for bc in bear_calls:
        matching_puts = puts_by_exp.get(bc.expiration_date, [])
        for bp in matching_puts:
            # Check symmetry: wing widths within factor
            if bp.strike_width == 0 or bc.strike_width == 0:
                continue
            ratio = max(bp.strike_width, bc.strike_width) / min(bp.strike_width, bc.strike_width)
            if ratio > config.ic_symmetry_factor:
                continue

            total_credit = bp.net_premium + bc.net_premium
            max_wing = max(bp.strike_width, bc.strike_width)
            max_loss = max_wing - total_credit
            if max_loss <= 0:
                continue

            roi = (total_credit / max_loss) * 100.0
            if roi < config.min_roi_pct:
                continue

            be_low = bp.short_leg.strike - total_credit
            be_high = bc.short_leg.strike + total_credit

            net_delta = _safe_add(
                _safe_add(bp.net_delta, bc.net_delta, sign=1),
                None,
            )
            net_theta = _safe_add(
                _safe_add(bp.net_theta, bc.net_theta, sign=1),
                None,
            )
            net_vega = _safe_add(
                _safe_add(bp.net_vega, bc.net_vega, sign=1),
                None,
            )

            all_oi = [
                bp.short_leg.open_interest or 0,
                bp.long_leg.open_interest or 0,
                bc.short_leg.open_interest or 0,
                bc.long_leg.open_interest or 0,
            ]
            all_vol = [
                bp.short_leg.volume or 0,
                bp.long_leg.volume or 0,
                bc.short_leg.volume or 0,
                bc.long_leg.volume or 0,
            ]

            results.append(IronCondor(
                underlying=bp.underlying,
                underlying_price=underlying_price,
                put_short=bp.short_leg,
                put_long=bp.long_leg,
                call_short=bc.short_leg,
                call_long=bc.long_leg,
                expiration_date=bp.expiration_date,
                dte=bp.dte,
                put_width=bp.strike_width,
                call_width=bc.strike_width,
                put_credit=bp.net_premium,
                call_credit=bc.net_premium,
                total_credit=round(total_credit, 3),
                max_loss=round(max_loss, 3),
                breakeven_low=round(be_low, 2),
                breakeven_high=round(be_high, 2),
                roi_pct=round(roi, 1),
                net_delta=bp.net_delta and bc.net_delta and round(bp.net_delta + bc.net_delta, 4),
                net_theta=bp.net_theta and bc.net_theta and round(bp.net_theta + bc.net_theta, 4),
                net_vega=bp.net_vega and bc.net_vega and round(bp.net_vega + bc.net_vega, 4),
                min_oi=min(all_oi),
                min_volume=min(all_vol),
            ))

    return results


# ---------------------------------------------------------------------------
# Iron Fly
# ---------------------------------------------------------------------------

def _build_iron_flys(
    puts: list[Leg],
    calls: list[Leg],
    underlying_price: float,
    config: SpreadHunterConfig,
) -> list[IronFly]:
    """
    Iron fly: SELL ATM straddle (put + call at same strike),
    BUY OTM put and OTM call as wings.
    """
    if underlying_price <= 0:
        return []

    min_w, max_w = config.min_strike_width or 0, config.max_strike_width or 9999
    if config.min_strike_width is None:
        min_w, max_w = auto_width(underlying_price)

    # Find ATM-adjacent strikes (within tolerance)
    tolerance = underlying_price * (config.iron_fly_atm_tolerance_pct / 100.0)
    atm_puts = sorted(
        [p for p in puts if abs(p.strike - underlying_price) <= tolerance],
        key=lambda p: abs(p.strike - underlying_price),
    )
    atm_calls = sorted(
        [c for c in calls if abs(c.strike - underlying_price) <= tolerance],
        key=lambda c: abs(c.strike - underlying_price),
    )

    otm_puts = sorted(
        [p for p in puts if p.strike < underlying_price],
        key=lambda p: p.strike,
        reverse=True,
    )
    otm_calls = sorted(
        [c for c in calls if c.strike > underlying_price],
        key=lambda c: c.strike,
    )

    results: list[IronFly] = []

    for atm_put in atm_puts[:1]:  # closest ATM put
        if not _passes_liquidity(atm_put, config):
            continue
        for atm_call in atm_calls[:1]:  # closest ATM call
            if not _passes_liquidity(atm_call, config):
                continue
            if atm_put.expiration_date != atm_call.expiration_date:
                continue

            center = (atm_put.strike + atm_call.strike) / 2.0
            dte = atm_put.dte

            # Find wing puts (below center strike)
            for wing_put in otm_puts:
                if wing_put.expiration_date != atm_put.expiration_date:
                    continue
                put_width = center - wing_put.strike
                if put_width < min_w:
                    continue
                if put_width > max_w:
                    break
                if not _passes_liquidity(wing_put, config):
                    continue

                # Find wing calls (above center strike)
                for wing_call in otm_calls:
                    if wing_call.expiration_date != atm_call.expiration_date:
                        continue
                    call_width = wing_call.strike - center
                    if call_width < min_w:
                        continue
                    if call_width > max_w:
                        break
                    if not _passes_liquidity(wing_call, config):
                        continue

                    # Check symmetry
                    if put_width == 0 or call_width == 0:
                        continue
                    ratio = max(put_width, call_width) / min(put_width, call_width)
                    if ratio > config.ic_symmetry_factor:
                        continue

                    # Pricing
                    atm_put_mark = _mark(atm_put)
                    atm_call_mark = _mark(atm_call)
                    wing_put_mark = _mark(wing_put)
                    wing_call_mark = _mark(wing_call)

                    total_credit = (atm_put_mark + atm_call_mark) - (wing_put_mark + wing_call_mark)
                    if total_credit <= 0:
                        continue

                    max_wing = max(put_width, call_width)
                    max_loss = max_wing - total_credit
                    if max_loss <= 0:
                        continue

                    roi = (total_credit / max_loss) * 100.0
                    if roi < config.min_roi_pct:
                        continue

                    be_low = center - total_credit
                    be_high = center + total_credit

                    all_oi = [
                        atm_put.open_interest or 0,
                        atm_call.open_interest or 0,
                        wing_put.open_interest or 0,
                        wing_call.open_interest or 0,
                    ]
                    all_vol = [
                        atm_put.volume or 0,
                        atm_call.volume or 0,
                        wing_put.volume or 0,
                        wing_call.volume or 0,
                    ]

                    # Net greeks: sell atm straddle + buy wings
                    nd = _safe_add_4(
                        atm_put.delta, atm_call.delta,
                        wing_put.delta, wing_call.delta,
                    )
                    nt = _safe_add_4(
                        atm_put.theta, atm_call.theta,
                        wing_put.theta, wing_call.theta,
                    )
                    nv = _safe_add_4(
                        atm_put.vega, atm_call.vega,
                        wing_put.vega, wing_call.vega,
                    )

                    results.append(IronFly(
                        underlying=atm_put.symbol,
                        underlying_price=underlying_price,
                        put_short=atm_put,
                        call_short=atm_call,
                        put_long=wing_put,
                        call_long=wing_call,
                        center_strike=center,
                        put_width=put_width,
                        call_width=call_width,
                        expiration_date=atm_put.expiration_date,
                        dte=dte,
                        total_credit=round(total_credit, 3),
                        max_loss=round(max_loss, 3),
                        breakeven_low=round(be_low, 2),
                        breakeven_high=round(be_high, 2),
                        roi_pct=round(roi, 1),
                        net_delta=nd,
                        net_theta=nt,
                        net_vega=nv,
                        min_oi=min(all_oi),
                        min_volume=min(all_vol),
                    ))

                    if len(results) >= config.max_per_type:
                        return results

    return results


# ---------------------------------------------------------------------------
# Calendar spread
# ---------------------------------------------------------------------------

def _build_calendars(
    all_legs: list[Leg],
    underlying_price: float,
    config: SpreadHunterConfig,
) -> list[CalendarSpread]:
    """
    Calendar spread: same strike, sell near-term / buy far-term.
    Works best when near IV > far IV (contango).
    """
    if underlying_price <= 0:
        return []

    min_w, max_w = config.min_strike_width or 0, config.max_strike_width or 9999
    if config.min_strike_width is None:
        # For calendars, width doesn't apply the same way — just filter by DTE
        pass

    # Group by (strike, put_call)
    by_strike: dict[tuple[float, str], list[Leg]] = defaultdict(list)
    for leg in all_legs:
        if not _passes_liquidity(leg, config):
            continue
        by_strike[(leg.strike, leg.put_call)].append(leg)

    results: list[CalendarSpread] = []

    for (strike, pc), legs in by_strike.items():
        # Sort by DTE ascending
        legs.sort(key=lambda l: l.dte)

        for i, near in enumerate(legs):
            if near.dte < config.min_dte or near.dte > config.max_dte:
                continue

            for far in legs[i + 1:]:
                dte_gap = far.dte - near.dte
                if dte_gap <= 0:
                    continue
                if dte_gap > config.calendar_max_dte_gap:
                    break

                # Pricing: sell near, buy far
                near_mark = _mark(near)
                far_mark = _mark(far)
                if near_mark <= 0 or far_mark <= 0:
                    continue

                debit = far_mark - near_mark
                if debit <= 0:
                    continue  # no cost = no risk, but also unrealistic

                # Max loss = debit paid (if near expires worthless and far drops to 0)
                # Max profit estimate: near extrinsic value (rough)
                max_profit_est = near_mark * 1.5  # conservative estimate

                near_iv = near.iv
                far_iv = far.iv
                iv_diff = None
                if near_iv is not None and far_iv is not None:
                    iv_diff = near_iv - far_iv  # positive = contango

                nd = _safe_add(near.delta, far.delta, sign=-1)  # sell near, buy far
                nt = _safe_add(near.theta, far.theta, sign=-1)
                nv = _safe_add(near.vega, far.vega, sign=-1)

                tags: list[str] = []
                if iv_diff is not None and iv_diff > 0:
                    tags.append("iv_contango")
                if nt is not None and nt > 0:
                    tags.append("positive_theta")
                if nv is not None and nv > 0:
                    tags.append("long_vega")

                results.append(CalendarSpread(
                    underlying=near.symbol,
                    underlying_price=underlying_price,
                    near_leg=near,
                    far_leg=far,
                    strike=strike,
                    near_dte=near.dte,
                    far_dte=far.dte,
                    debit=round(debit, 3),
                    max_loss=round(debit, 3),
                    max_profit_est=round(max_profit_est, 3),
                    net_delta=nd,
                    net_theta=nt,
                    net_vega=nv,
                    near_iv=near_iv,
                    far_iv=far_iv,
                    iv_diff=iv_diff,
                    min_oi=min(near.open_interest or 0, far.open_interest or 0),
                    min_volume=min(near.volume or 0, far.volume or 0),
                    tags=tags,
                ))

                if len(results) >= config.max_per_type:
                    return results

    return results


# ---------------------------------------------------------------------------
# Greek helpers
# ---------------------------------------------------------------------------

def _safe_add(a: float | None, b: float | None, sign: int = 1) -> float | None:
    """Add two optional floats. sign=1 for same direction, -1 for opposite."""
    if a is None or b is None:
        return None
    return round(a + (sign * b), 4)


def _safe_add_4(
    a: float | None, b: float | None,
    c: float | None, d: float | None,
) -> float | None:
    """Add four optional floats (for iron fly net greeks)."""
    vals = [v for v in [a, b, c, d] if v is not None]
    if len(vals) < 4:
        return None
    return round(sum(vals), 4)


def _filter_legs(
    legs: list[Leg],
    underlying_price: float,
    signal_filter: SignalFilter,
    iv_history: list[float] | None = None,
    price_history: list[float] | None = None,
    strike_oi_map: dict[float, int] | None = None,
) -> list[Leg]:
    """Run signal filters on each leg, return only those that pass ALL gates."""
    if signal_filter is None:
        return legs
    passed: list[Leg] = []
    for leg in legs:
        ok, reasons = run_all_filters(
            leg, underlying_price, signal_filter,
            historical_ivs=iv_history,
            price_history=price_history,
            strike_oi_map=strike_oi_map,
        )
        if ok:
            passed.append(leg)
        else:
            # Log the first failure reason only (don't spam)
            fail = [r for r in reasons if r.startswith("FAIL")]
            if fail:
                logger.debug(f"Filtered {leg.strike} {leg.put_call}: {fail[0]}")
    return passed


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def build_all_spreads(
    conn: Any,
    config: SpreadHunterConfig,
    tickers: list[str] | None = None,
    is_pg: bool = False,
) -> dict[str, list[AnySpread]]:
    """
    Build all spread types from latest DB data.

    Returns dict keyed by spread type name.
    """
    logger.info("Fetching contracts from DB...")
    contracts = fetch_contracts(conn, tickers=tickers, is_pg=is_pg)
    if not contracts:
        logger.warning("No contracts found in DB")
        return {}

    logger.info(f"Got {len(contracts)} contracts")

    # Track underlyings and their prices
    underlying_prices: dict[str, float] = {}
    for row in contracts:
        sym = row["underlying_symbol"]
        price = _f(row.get("underlying_price"))
        if price and price > 0:
            underlying_prices[sym] = price

    groups = group_contracts(contracts)
    logger.info(f"Grouped into {sum(len(exps) for exps in groups.values())} underlying/expiry combos across {len(groups)} underlyings")

    results: dict[str, list[AnySpread]] = {
        "bull_put_credit": [],
        "bear_call_credit": [],
        "iron_condor": [],
        "iron_fly": [],
        "calendar": [],
    }

    for sym, expirations in groups.items():
        price = underlying_prices.get(sym, 0)
        if price <= 0:
            continue

        if config.min_strike_width is None:
            config.min_strike_width, config.max_strike_width = auto_width(price)

        all_legs_for_sym: list[Leg] = []

        for exp, pc_map in expirations.items():
            puts = pc_map.get("PUT", [])
            calls = pc_map.get("CALL", [])

            # Filter by DTE
            puts = [p for p in puts if config.min_dte <= p.dte <= config.max_dte]
            calls = [c for c in calls if config.min_dte <= c.dte <= config.max_dte]

            # Build verticals
            bull_puts = _build_bull_put_credits(puts, price, config)
            bear_calls = _build_bear_call_credits(calls, price, config)

            results["bull_put_credit"].extend(bull_puts)
            results["bear_call_credit"].extend(bear_calls)

            # Iron condors from same expiration
            ics = _build_iron_condors(bull_puts, bear_calls, price, config)
            results["iron_condor"].extend(ics)

            # Iron flys
            flys = _build_iron_flys(puts, calls, price, config)
            results["iron_fly"].extend(flys)

            all_legs_for_sym.extend(puts + calls)

        # Calendars span expirations
        cals = _build_calendars(all_legs_for_sym, price, config)
        results["calendar"].extend(cals)

    # Reset auto-width for next ticker
    config.min_strike_width = None
    config.max_strike_width = None

    # Trim to max_per_type
    for stype in results:
        results[stype] = results[stype][:config.max_per_type * len(underlying_prices)]

    total = sum(len(v) for v in results.values())
    logger.info(f"Built {total} total spread candidates")
    for stype, items in results.items():
        logger.info(f"  {stype}: {len(items)}")

    return results


def build_filtered_spreads(
    conn: Any,
    tickers: list[str] | None = None,
    config: SpreadHunterConfig | None = None,
    signal_filter: SignalFilter | None = None,
    is_pg: bool = False,
) -> dict[str, list[AnySpread]]:
    """
    Build spreads with signal filters applied.
    Only constructs spreads from legs that pass ALL filter gates.
    This is the main entry point for the scanner.
    """
    if config is None:
        config = SpreadHunterConfig()
    if signal_filter is None:
        signal_filter = SignalFilter()

    # Override config DTE range from signal filter
    config.min_dte = signal_filter.min_dte
    config.max_dte = signal_filter.max_dte

    # Fetch current contracts
    logger.info("Fetching contracts from DB...")
    contracts = fetch_contracts(conn, tickers=tickers, is_pg=is_pg)
    if not contracts:
        logger.warning("No contracts found in DB")
        return {}

    logger.info(f"Got {len(contracts)} contracts")

    # Track underlyings and their prices
    underlying_prices: dict[str, float] = {}
    for row in contracts:
        sym = row["underlying_symbol"]
        price = _f(row.get("underlying_price"))
        if price and price > 0:
            underlying_prices[sym] = price

    groups = group_contracts(contracts)

    # Override spread width from signal filter
    config.min_strike_width = signal_filter.min_strike_width
    config.max_strike_width = signal_filter.max_strike_width

    results: dict[str, list[AnySpread]] = {
        "bull_put_credit": [],
        "bear_call_credit": [],
        "iron_condor": [],
        "iron_fly": [],
        "calendar": [],
    }

    for sym, expirations in groups.items():
        price = underlying_prices.get(sym, 0)
        if price <= 0:
            continue

        # Fetch historical context for filters (once per ticker)
        iv_history = fetch_atm_iv_history(
            conn, sym, signal_filter.iv_lookback_days, is_pg
        )
        price_history = fetch_price_history(
            conn, sym, signal_filter.iv_lookback_days, is_pg
        )
        put_oi_map = fetch_strike_oi(conn, sym, "PUT", is_pg)
        call_oi_map = fetch_strike_oi(conn, sym, "CALL", is_pg)

        logger.info(
            f"[{sym}] Filter context: {len(iv_history)} IV points, "
            f"{len(price_history)} price points, "
            f"{len(put_oi_map)} put strikes w/ OI"
        )

        all_legs_for_sym: list[Leg] = []

        for exp, pc_map in expirations.items():
            puts = pc_map.get("PUT", [])
            calls = pc_map.get("CALL", [])

            # Filter by DTE from signal_filter
            puts = [p for p in puts if signal_filter.min_dte <= p.dte <= signal_filter.max_dte]
            calls = [c for c in calls if signal_filter.min_dte <= c.dte <= signal_filter.max_dte]

            # === SIGNAL FILTER GATE ===
            # Pre-filter legs with a wide delta band so both short and long legs
            # of a spread survive.  The tight delta range (0.10-0.25) is applied
            # later to the SHORT leg only when building each spread type.
            wide_filter = signal_filter.with_wide_delta()
            puts = _filter_legs(
                puts, price, wide_filter,
                iv_history=iv_history,
                price_history=price_history,
                strike_oi_map=put_oi_map,
            )
            calls = _filter_legs(
                calls, price, wide_filter,
                iv_history=iv_history,
                price_history=price_history,
                strike_oi_map=call_oi_map,
            )

            if not puts and not calls:
                logger.debug(f"[{sym}][{exp}] No legs passed signal filters")
                continue

            # Build spreads only from filtered legs (tight delta applied to short leg)
            bull_puts = _build_bull_put_credits(puts, price, config, signal_filter)
            bear_calls = _build_bear_call_credits(calls, price, config, signal_filter)

            results["bull_put_credit"].extend(bull_puts)
            results["bear_call_credit"].extend(bear_calls)

            # Iron condors from same expiration
            ics = _build_iron_condors(bull_puts, bear_calls, price, config)
            results["iron_condor"].extend(ics)

            # Iron flys
            flys = _build_iron_flys(puts, calls, price, config)
            results["iron_fly"].extend(flys)

            all_legs_for_sym.extend(puts + calls)

        # Calendars span expirations
        cals = _build_calendars(all_legs_for_sym, price, config)
        results["calendar"].extend(cals)

    # Reset auto-width
    config.min_strike_width = None
    config.max_strike_width = None

    total = sum(len(v) for v in results.values())
    logger.info(f"Built {total} spread candidates after signal filtering")
    for stype, items in results.items():
        if items:
            logger.info(f"  {stype}: {len(items)}")

    return results
