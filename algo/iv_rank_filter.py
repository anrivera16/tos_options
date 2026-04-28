"""
Module 3: IV Rank Gate

Only sell premium when IV rank is in the sweet spot (default 30-95%).
IV rank measures where current IV sits relative to its recent range.
"""
from __future__ import annotations

import logging
from typing import Any

from algo.types import CandidateSpread
from algo.config import IVRankConfig

logger = logging.getLogger(__name__)


def compute_iv_rank(current_iv: float, historical_ivs: list[float]) -> float:
    """
    Compute IV percentile rank (0-100).

    Uses the standard percentile formula:
    rank = (% of values below + 0.5 * % equal) * 100

    Args:
        current_iv: Current ATM IV (whole-number %, e.g. 32.0 = 32%)
        historical_ivs: List of historical IV readings

    Returns:
        Percentile rank 0-100
    """
    if not historical_ivs:
        return 50.0  # unknown, assume middle

    below = sum(1 for iv in historical_ivs if iv < current_iv)
    equal = sum(1 for iv in historical_ivs if iv == current_iv)
    return (below + equal / 2.0) / len(historical_ivs) * 100.0


def apply_iv_rank_filter(
    candidates: list[CandidateSpread],
    current_iv: float | None,
    historical_ivs: list[float],
    config: IVRankConfig,
) -> list[CandidateSpread]:
    """
    Filter candidates based on IV rank.

    Passes through if insufficient history (< 5 points).
    """
    if not config.enabled:
        for c in candidates:
            c.tag("iv_rank:disabled")
        return candidates

    if current_iv is None or current_iv <= 0:
        for c in candidates:
            c.reject("iv_rank", "no IV data available")
        return candidates

    if len(historical_ivs) < 5:
        logger.warning(f"Only {len(historical_ivs)} IV points — pass-through")
        for c in candidates:
            c.iv_rank = None
            c.tag("iv_rank:insufficient_history")
        return candidates

    rank = compute_iv_rank(current_iv, historical_ivs)

    # Set IV rank on all candidates
    for c in candidates:
        c.iv_rank = round(rank, 1)

    if rank < config.iv_rank_min:
        for c in candidates:
            c.reject("iv_rank", f"IV rank {rank:.0f}% < min {config.iv_rank_min}%")
        logger.info(f"IV rank {rank:.0f}% too low — all {len(candidates)} rejected")
        return candidates

    if rank > config.iv_rank_max:
        for c in candidates:
            c.reject("iv_rank", f"IV rank {rank:.0f}% > max {config.iv_rank_max}% (extreme IV)")
        logger.info(f"IV rank {rank:.0f}% too high — all {len(candidates)} rejected")
        return candidates

    for c in candidates:
        c.tag(f"iv_rank:{rank:.0f}%")
    logger.info(f"IV rank {rank:.0f}% in range — {len(candidates)} candidates passed")
    return candidates
