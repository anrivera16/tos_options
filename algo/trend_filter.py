"""
Module 2: Trend Filter

Determines market direction bias using SMA on daily prices.
Bullish = price above SMA + positive slope → keep bull puts only
Bearish = price below SMA + negative slope → keep bear calls only
Neutral = configurable (keep both or keep none)
"""
from __future__ import annotations

import logging
from typing import Any

from algo.types import CandidateSpread, TrendDirection
from algo.config import TrendConfig

logger = logging.getLogger(__name__)


def determine_trend(
    current_price: float,
    price_history: list[float],
    config: TrendConfig,
) -> TrendDirection:
    """
    Determine trend direction from price history.

    Args:
        current_price: Current underlying price
        price_history: Daily closing prices, oldest first
        config: Trend filter config

    Returns:
        TrendDirection enum
    """
    n = config.sma_period
    if len(price_history) < n:
        logger.warning(f"Only {len(price_history)} price points, need {n} for SMA — neutral")
        return TrendDirection.NEUTRAL

    sma = sum(price_history[-n:]) / n

    # Calculate SMA slope over lookback period
    if len(price_history) < n + config.slope_lookback:
        # Not enough for slope calc, just use price vs SMA
        if current_price > sma:
            return TrendDirection.BULLISH
        elif current_price < sma:
            return TrendDirection.BEARISH
        return TrendDirection.NEUTRAL

    # SMA at current and slope_lookback periods ago
    current_sma = sum(price_history[-n:]) / n
    prior_sma = sum(price_history[-(n + config.slope_lookback):-config.slope_lookback]) / n

    slope_positive = current_sma > prior_sma
    price_above = current_price > current_sma

    if price_above and slope_positive:
        return TrendDirection.BULLISH
    elif not price_above and not slope_positive:
        return TrendDirection.BEARISH
    else:
        return TrendDirection.NEUTRAL


def apply_trend_filter(
    candidates: list[CandidateSpread],
    current_price: float,
    price_history: list[float],
    config: TrendConfig,
) -> list[CandidateSpread]:
    """
    Filter candidates based on trend direction.

    Bullish → keep bull_put_credit only
    Bearish → keep bear_call_credit only
    Neutral → depends on config.neutral_action
    """
    if not config.enabled:
        for c in candidates:
            c.tag("trend:disabled")
        return candidates

    trend = determine_trend(current_price, price_history, config)

    # Set trend direction on all candidates
    for c in candidates:
        c.trend_direction = trend.value

    if trend == TrendDirection.NEUTRAL and config.neutral_action == "keep_both":
        for c in candidates:
            c.tag(f"trend:neutral_keep")
        logger.info(f"Trend NEUTRAL — keeping all {len(candidates)} candidates")
        return candidates

    kept: list[CandidateSpread] = []
    for c in candidates:
        if trend == TrendDirection.BULLISH:
            if c.spread_type == "bull_put_credit":
                c.tag("trend:bullish_match")
                kept.append(c)
            else:
                c.reject("trend", f"bear call rejected in bullish trend")
        elif trend == TrendDirection.BEARISH:
            if c.spread_type == "bear_call_credit":
                c.tag("trend:bearish_match")
                kept.append(c)
            else:
                c.reject("trend", f"bull put rejected in bearish trend")
        else:
            # Neutral + keep_none
            c.reject("trend", "neutral trend, no trades taken")

    logger.info(f"Trend {trend.value}: {len(kept)}/{len(candidates)} candidates passed")
    return kept
