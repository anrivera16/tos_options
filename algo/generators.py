"""
Module 1: Signal Generator

Builds raw candidate bull put credit and bear call credit spreads
from option chain data. This is the entry point of the pipeline —
no filtering happens here, just spread construction.
"""
from __future__ import annotations

import logging
from typing import Any

from algo.types import CandidateSpread
from algo.config import GeneratorConfig

logger = logging.getLogger(__name__)


def generate_from_rows(
    rows: list[dict[str, Any]],
    underlying_price: float,
    config: GeneratorConfig,
    snapshot_timestamp: str = "",
) -> list[CandidateSpread]:
    """
    Build candidate spreads from raw DB rows.

    Each row should have: strike, put_call, expiration_date, dte,
    bid, ask, mark, delta, gamma, theta, vega, volatility,
    open_interest, total_volume

    Returns both bull_put_credit and bear_call_credit candidates
    based on config.spread_types.
    """
    candidates: list[CandidateSpread] = []

    # Group legs by (expiration, put_call)
    legs_by_expiry_side: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        expiry = row.get("expiration_date", "")
        pc = row.get("put_call", "")
        key = (expiry, pc)
        legs_by_expiry_side.setdefault(key, []).append(row)

    for (expiry, pc), legs in legs_by_expiry_side.items():
        # Filter to DTE range
        dte = legs[0].get("dte", 0)
        if dte is None or not (config.dte_min <= int(dte) <= config.dte_max):
            continue

        if pc == "PUT" and "bull_put_credit" in config.spread_types:
            candidates.extend(
                _build_put_credit_spreads(legs, underlying_price, config, expiry, int(dte), snapshot_timestamp)
            )

        if pc == "CALL" and "bear_call_credit" in config.spread_types:
            candidates.extend(
                _build_call_credit_spreads(legs, underlying_price, config, expiry, int(dte), snapshot_timestamp)
            )

    logger.info(f"Generated {len(candidates)} raw candidates")
    return candidates


def _get_mark(row: dict[str, Any]) -> float:
    """Get mark price from row, fallback to mid of bid/ask."""
    mark = _to_float(row.get("mark"))
    if mark and mark > 0:
        return mark
    bid = _to_float(row.get("bid")) or 0
    ask = _to_float(row.get("ask")) or 0
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    return bid or 0


def _build_put_credit_spreads(
    puts: list[dict],
    underlying_price: float,
    config: GeneratorConfig,
    expiry: str,
    dte: int,
    timestamp: str,
) -> list[CandidateSpread]:
    """
    Bull put credit: SELL higher-strike put, BUY lower-strike put.
    Both OTM (strike < underlying_price).
    """
    if underlying_price <= 0:
        return []

    # Filter to OTM puts, sorted by strike descending (highest first)
    otm = sorted(
        [p for p in puts if _to_float(p.get("strike"), 0) < underlying_price],
        key=lambda p: _to_float(p.get("strike"), 0),
        reverse=True,
    )

    results: list[CandidateSpread] = []
    width = config.strike_width

    for short_row in otm:
        short_strike = _to_float(short_row.get("strike"), 0)
        short_delta = abs(_to_float(short_row.get("delta")) or 0)

        # Delta filter on short leg
        if not (config.delta_min <= short_delta <= config.delta_max):
            continue

        # Liquidity check on short leg
        short_oi = _to_int(short_row.get("open_interest"))
        short_vol = _to_int(short_row.get("total_volume"))
        if short_oi < config.min_oi or short_vol < config.min_volume:
            continue

        short_mark = _get_mark(short_row)
        if short_mark <= 0:
            continue

        # Find long leg: exactly $width below, must be strictly below short
        target_long_strike = short_strike - width
        long_candidates = [p for p in otm if _to_float(p.get("strike"), 0) < short_strike]
        long_row = _find_nearest_strike(long_candidates, target_long_strike)
        if long_row is None:
            continue

        long_strike = _to_float(long_row.get("strike"), 0)
        actual_width = short_strike - long_strike

        # Accept if within 1 point of target width
        if abs(actual_width - width) > 1.0:
            continue

        long_oi = _to_int(long_row.get("open_interest"))
        long_vol = _to_int(long_row.get("total_volume"))
        if long_oi < config.min_oi or long_vol < config.min_volume:
            continue

        long_mark = _get_mark(long_row)
        if long_mark <= 0:
            continue

        credit = short_mark - long_mark
        if credit <= 0:
            continue

        max_loss = actual_width - credit
        if max_loss <= 0:
            continue

        roc = (credit / max_loss) * 100.0
        if roc < config.min_roc_pct:
            continue

        results.append(CandidateSpread(
            spread_type="bull_put_credit",
            underlying=config.underlying,
            underlying_price=underlying_price,
            short_strike=short_strike,
            long_strike=long_strike,
            strike_width=actual_width,
            expiration_date=expiry,
            dte=dte,
            short_premium=short_mark,
            long_premium=long_mark,
            credit=credit,
            max_loss=max_loss,
            roc_pct=round(roc, 1),
            short_delta=_to_float(short_row.get("delta")),
            short_theta=_to_float(short_row.get("theta")),
            short_vega=_to_float(short_row.get("vega")),
            short_iv=_to_float(short_row.get("volatility")),
            net_delta=_safe_add(short_row.get("delta"), long_row.get("delta")),
            net_theta=_safe_add(short_row.get("theta"), long_row.get("theta")),
            net_vega=_safe_add(short_row.get("vega"), long_row.get("vega")),
            short_oi=short_oi,
            short_volume=short_vol,
            long_oi=long_oi,
            long_volume=long_vol,
            min_oi=min(short_oi, long_oi),
            min_volume=min(short_vol, long_vol),
            entry_date=timestamp[:10] if timestamp else None,
            entry_time=timestamp,
        ))

    return results


def _build_call_credit_spreads(
    calls: list[dict],
    underlying_price: float,
    config: GeneratorConfig,
    expiry: str,
    dte: int,
    timestamp: str,
) -> list[CandidateSpread]:
    """
    Bear call credit: SELL lower-strike call, BUY higher-strike call.
    Both OTM (strike > underlying_price).
    """
    if underlying_price <= 0:
        return []

    # Filter to OTM calls, sorted by strike ascending (lowest first)
    otm = sorted(
        [c for c in calls if _to_float(c.get("strike"), 0) > underlying_price],
        key=lambda c: _to_float(c.get("strike"), 0),
    )

    results: list[CandidateSpread] = []
    width = config.strike_width

    for short_row in otm:
        short_strike = _to_float(short_row.get("strike"), 0)
        short_delta = abs(_to_float(short_row.get("delta")) or 0)

        if not (config.delta_min <= short_delta <= config.delta_max):
            continue

        short_oi = _to_int(short_row.get("open_interest"))
        short_vol = _to_int(short_row.get("total_volume"))
        if short_oi < config.min_oi or short_vol < config.min_volume:
            continue

        short_mark = _get_mark(short_row)
        if short_mark <= 0:
            continue

        # Find long leg: exactly $width above, must be strictly above short
        target_long_strike = short_strike + width
        long_candidates = [c for c in otm if _to_float(c.get("strike"), 0) > short_strike]
        long_row = _find_nearest_strike(long_candidates, target_long_strike)
        if long_row is None:
            continue

        long_strike = _to_float(long_row.get("strike"), 0)
        actual_width = long_strike - short_strike

        if abs(actual_width - width) > 1.0:
            continue

        long_oi = _to_int(long_row.get("open_interest"))
        long_vol = _to_int(long_row.get("total_volume"))
        if long_oi < config.min_oi or long_vol < config.min_volume:
            continue

        long_mark = _get_mark(long_row)
        if long_mark <= 0:
            continue

        credit = short_mark - long_mark
        if credit <= 0:
            continue

        max_loss = actual_width - credit
        if max_loss <= 0:
            continue

        roc = (credit / max_loss) * 100.0
        if roc < config.min_roc_pct:
            continue

        results.append(CandidateSpread(
            spread_type="bear_call_credit",
            underlying=config.underlying,
            underlying_price=underlying_price,
            short_strike=short_strike,
            long_strike=long_strike,
            strike_width=actual_width,
            expiration_date=expiry,
            dte=dte,
            short_premium=short_mark,
            long_premium=long_mark,
            credit=credit,
            max_loss=max_loss,
            roc_pct=round(roc, 1),
            short_delta=_to_float(short_row.get("delta")),
            short_theta=_to_float(short_row.get("theta")),
            short_vega=_to_float(short_row.get("vega")),
            short_iv=_to_float(short_row.get("volatility")),
            net_delta=_safe_add(short_row.get("delta"), long_row.get("delta")),
            net_theta=_safe_add(short_row.get("theta"), long_row.get("theta")),
            net_vega=_safe_add(short_row.get("vega"), long_row.get("vega")),
            short_oi=short_oi,
            short_volume=short_vol,
            long_oi=long_oi,
            long_volume=long_vol,
            min_oi=min(short_oi, long_oi),
            min_volume=min(short_vol, long_vol),
            entry_date=timestamp[:10] if timestamp else None,
            entry_time=timestamp,
        ))

    return results


def _find_nearest_strike(legs: list[dict], target: float) -> dict | None:
    """Find the leg closest to target strike."""
    best = None
    best_dist = float("inf")
    for leg in legs:
        strike = _to_float(leg.get("strike"), 0)
        dist = abs(strike - target)
        if dist < best_dist:
            best_dist = dist
            best = leg
    return best


def _to_float(v: Any, default: float | None = None) -> float | None:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_int(v: Any) -> int:
    if v is None:
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _safe_add(a: Any, b: Any) -> float | None:
    """Add two values that might be None."""
    fa = _to_float(a)
    fb = _to_float(b)
    if fa is not None and fb is not None:
        return fa + fb
    return None
