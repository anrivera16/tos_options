"""
Module 7: Scoring & Ranking

Scores and ranks candidate spreads using a composite of multiple factors.
Each factor is normalized 0-1, then weighted.
"""
from __future__ import annotations

import math
import logging

from algo.types import CandidateSpread
from algo.config import ScoringConfig

logger = logging.getLogger(__name__)


def score_candidate(spread: CandidateSpread, config: ScoringConfig) -> dict[str, float]:
    """
    Score a single candidate spread. Returns breakdown of each factor.

    Components:
      - ROC% (higher = better)        weight from config
      - Delta center (closer to ideal) weight from config
      - Theta efficiency              weight from config
      - Liquidity (higher = better)   weight from config
      - Distance OTM (further = safer) weight from config
    """
    scores: dict[str, float] = {}

    # 1. ROC score: 10% = 0, 60% = 1, cap at 1.5
    scores["roc"] = min(max((spread.roc_pct - 10.0) / 50.0, 0.0), 1.5)

    # 2. Delta center score: how close short_delta is to ideal (default 0.15)
    if spread.short_delta is not None:
        abs_delta = abs(spread.short_delta)
        delta_dist = abs(abs_delta - config.ideal_delta)
        # 0 = perfect (1.0), 0.10 = edge of range (0.0)
        scores["delta_center"] = max(1.0 - delta_dist / 0.10, 0.0)
    else:
        scores["delta_center"] = 0.0

    # 3. Theta efficiency: |net_theta| / daily_credit
    scores["theta"] = 0.5  # neutral default
    if spread.net_theta is not None and spread.credit > 0:
        daily_credit = spread.credit / max(spread.dte, 1)
        if daily_credit > 0:
            theta_ratio = abs(spread.net_theta) / daily_credit
            # 0.05 = great (1.0), 0.5 = poor (0.0)
            scores["theta"] = max(1.0 - theta_ratio / 0.5, 0.0)

    # 4. Liquidity: log-scaled OI
    oi = max(spread.min_oi, 1)
    scores["liquidity"] = min(max((math.log10(oi) - 1.5) / 2.5, 0.0), 1.0)

    # 5. Distance OTM as safety margin
    scores["distance"] = min(max((spread.distance_otm_pct - 1.0) / 5.0, 0.0), 1.0)

    return scores


def apply_scoring(
    candidates: list[CandidateSpread],
    config: ScoringConfig,
) -> list[CandidateSpread]:
    """
    Score and rank all candidates. Sets composite_score and score_breakdown
    on each candidate, then sorts by score descending.
    """
    if not config.enabled:
        for c in candidates:
            c.tag("scoring:disabled")
        return candidates

    weights = {
        "roc": config.roc_weight,
        "delta_center": config.delta_center_weight,
        "theta": config.theta_weight,
        "liquidity": config.liquidity_weight,
        "distance": config.distance_weight,
    }

    for c in candidates:
        breakdown = score_candidate(c, config)
        c.score_breakdown = breakdown

        composite = sum(breakdown.get(k, 0.0) * w for k, w in weights.items())
        c.composite_score = round(composite, 4)
        c.tag(f"score:{c.composite_score:.3f}")

    # Sort by score descending
    ranked = sorted(candidates, key=lambda c: c.composite_score, reverse=True)

    if ranked:
        logger.info(
            f"Scored {len(ranked)} candidates — "
            f"best: {ranked[0].composite_score:.3f} "
            f"({ranked[0].spread_type} {ranked[0].short_strike}/{ranked[0].long_strike})"
        )

    return ranked
