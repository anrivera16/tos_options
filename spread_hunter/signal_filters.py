"""
Signal Filters -- hard gates that ALL must pass before a trade fires.

Each filter takes the data it needs and returns (passed: bool, reason: str).
If ANY filter returns False, no trade that day.
"""
from __future__ import annotations

import logging
from typing import Any

from spread_hunter.spread_types import Leg, SignalFilter

logger = logging.getLogger(__name__)


def check_delta(leg: Leg, config: SignalFilter) -> tuple[bool, str]:
    """Filter on real delta from Schwab. Short leg must be in range."""
    if leg.delta is None:
        return False, f"delta is None for {leg.strike} {leg.put_call}"
    abs_delta = abs(leg.delta)
    if abs_delta < config.delta_min:
        return False, f"delta {abs_delta:.3f} < min {config.delta_min}"
    if abs_delta > config.delta_max:
        return False, f"delta {abs_delta:.3f} > max {config.delta_max}"
    return True, f"delta {abs_delta:.3f} in range"


def check_volume_oi(leg: Leg, config: SignalFilter) -> tuple[bool, str]:
    """Filter on volume and open interest per leg."""
    oi = leg.open_interest or 0
    vol = leg.volume or 0
    if oi < config.min_oi:
        return False, f"OI {oi} < min {config.min_oi}"
    if vol < config.min_volume:
        return False, f"volume {vol} < min {config.min_volume}"
    return True, f"OI={oi} vol={vol} OK"


def check_iv_rank(
    current_iv: float | None,
    historical_ivs: list[float],
    config: SignalFilter,
) -> tuple[bool, str]:
    """
    Filter on IV percentile rank.

    Args:
        current_iv: Current ATM IV (whole-number %, e.g. 32.0 = 32%)
        historical_ivs: List of historical IV values for percentile calc
        config: Filter config with iv_rank_min, iv_rank_max

    Returns:
        (passed, reason)
    """
    if current_iv is None:
        return False, "IV is None"

    if len(historical_ivs) < 5:
        # Not enough data to compute rank -- pass through with warning
        logger.warning(
            f"Only {len(historical_ivs)} historical IV points, "
            f"IV rank filter skipped (pass-through)"
        )
        return True, f"IV {current_iv:.1f}% (insufficient history, pass-through)"

    percentile = _percentile_rank(current_iv, historical_ivs)

    if percentile < config.iv_rank_min:
        return False, f"IV rank {percentile:.0f}% < min {config.iv_rank_min}%"
    if percentile > config.iv_rank_max:
        return False, f"IV rank {percentile:.0f}% > max {config.iv_rank_max}%"
    return True, f"IV rank {percentile:.0f}% in range ({current_iv:.1f}% IV)"


def check_trend(
    current_price: float,
    price_history: list[float],
    config: SignalFilter,
) -> tuple[bool, str]:
    """
    Filter on trend: price must be above SMA for bull puts.

    Args:
        current_price: Current underlying price
        price_history: Recent closing prices (oldest first)
        config: Filter config

    Returns:
        (passed, reason)
    """
    if not config.trend_require_above_sma:
        return True, "trend filter disabled"

    n = config.trend_sma_periods
    if len(price_history) < n:
        logger.warning(
            f"Only {len(price_history)} price points, need {n} for SMA, "
            f"trend filter skipped (pass-through)"
        )
        return True, f"price {current_price:.2f} (insufficient history, pass-through)"

    sma = sum(price_history[-n:]) / n
    if current_price > sma:
        pct_above = (current_price - sma) / sma * 100
        return True, f"price {current_price:.2f} > SMA({n}) {sma:.2f} (+{pct_above:.1f}%)"
    else:
        pct_below = (sma - current_price) / sma * 100
        return False, f"price {current_price:.2f} < SMA({n}) {sma:.2f} (-{pct_below:.1f}%)"


def check_support(
    short_strike: float,
    put_call: str,
    underlying_price: float,
    strike_oi_map: dict[float, int],
    config: SignalFilter,
) -> tuple[bool, str]:
    """
    Filter on support/resistance from high-OI strikes.

    Finds major support levels (strikes with OI > threshold * average).
    For bull puts: don't sell if short strike is at or below major support.

    Args:
        short_strike: The strike you're selling
        put_call: "PUT" or "CALL"
        underlying_price: Current price
        strike_oi_map: {strike: total_put_oi} for support detection
        config: Filter config
    """
    if not strike_oi_map:
        return True, "no OI data for support check (pass-through)"

    oi_values = [oi for oi in strike_oi_map.values() if oi > 0]
    if not oi_values:
        return True, "all OI is zero (pass-through)"

    avg_oi = sum(oi_values) / len(oi_values)
    threshold = avg_oi * config.support_oi_threshold

    # Find major support strikes (high put OI below current price)
    major_supports = []
    for strike, oi in sorted(strike_oi_map.items()):
        if put_call == "PUT" and strike < underlying_price and oi >= threshold:
            major_supports.append((strike, oi))

    if not major_supports:
        return True, "no major support levels detected"

    # Check if short strike is at or below any major support
    buffer = underlying_price * config.support_buffer_pct / 100.0
    for sup_strike, sup_oi in major_supports:
        if short_strike <= sup_strike + buffer:
            return False, (
                f"short strike {short_strike} at/below major support "
                f"{sup_strike} (OI={sup_oi:,})"
            )

    return True, f"short strike {short_strike} clear of {len(major_supports)} support levels"


def _percentile_rank(value: float, data: list[float]) -> float:
    """Compute percentile rank of value within data (0-100)."""
    if not data:
        return 50.0
    below = sum(1 for d in data if d < value)
    equal = sum(1 for d in data if d == value)
    return (below + equal / 2.0) / len(data) * 100.0


def run_all_filters(
    leg: Leg,
    underlying_price: float,
    config: SignalFilter,
    historical_ivs: list[float] | None = None,
    price_history: list[float] | None = None,
    strike_oi_map: dict[float, int] | None = None,
) -> tuple[bool, list[str]]:
    """
    Run ALL filters against a candidate short leg.
    Returns (all_passed, list_of_reasons).
    """
    reasons: list[str] = []

    # 1. Delta
    passed, reason = check_delta(leg, config)
    reasons.append(f"DELTA: {'PASS' if passed else 'FAIL'} - {reason}")
    if not passed:
        return False, reasons

    # 2. Volume/OI
    passed, reason = check_volume_oi(leg, config)
    reasons.append(f"VOL/OI: {'PASS' if passed else 'FAIL'} - {reason}")
    if not passed:
        return False, reasons

    # 3. IV rank
    if historical_ivs is not None:
        current_iv = leg.iv
        passed, reason = check_iv_rank(current_iv, historical_ivs, config)
        reasons.append(f"IV_RANK: {'PASS' if passed else 'FAIL'} - {reason}")
        if not passed:
            return False, reasons

    # 4. Trend
    if price_history is not None:
        passed, reason = check_trend(underlying_price, price_history, config)
        reasons.append(f"TREND: {'PASS' if passed else 'FAIL'} - {reason}")
        if not passed:
            return False, reasons

    # 5. Support/resistance
    if strike_oi_map is not None:
        passed, reason = check_support(
            leg.strike, leg.put_call, underlying_price, strike_oi_map, config
        )
        reasons.append(f"SUPPORT: {'PASS' if passed else 'FAIL'} - {reason}")
        if not passed:
            return False, reasons

    return True, reasons
