"""
Module 6: Wall Proximity Filter

Rejects spreads whose short strike is too close to an OI/Volume wall.
The idea: if there's a massive put OI wall (support) just below your
short put strike, a small move down breaches support and your spread
is under water.
"""
from __future__ import annotations

import logging

from algo.types import CandidateSpread, OIWall
from algo.config import ProximityConfig

logger = logging.getLogger(__name__)


def apply_proximity_filter(
    candidates: list[CandidateSpread],
    walls: list[OIWall],
    underlying_price: float,
    config: ProximityConfig,
) -> list[CandidateSpread]:
    """
    Filter candidates based on proximity to OI walls.

    For bull puts: check if short strike is within X% of a support wall below it
    For bear calls: check if short strike is within X% of a resistance wall above it
    """
    if not config.enabled:
        for c in candidates:
            c.tag("proximity:disabled")
        return candidates

    if not walls:
        for c in candidates:
            c.tag("proximity:no_walls")
        return candidates

    for c in candidates:
        relevant_walls = _get_relevant_walls(c, walls, config)

        if not relevant_walls:
            c.nearest_wall_strike = None
            c.nearest_wall_distance_pct = None
            c.tag("proximity:no_nearby_walls")
            continue

        # Find closest wall
        nearest = min(relevant_walls, key=lambda w: abs(w.strike - c.short_strike))
        distance_pct = abs(c.short_strike - nearest.strike) / underlying_price * 100.0

        c.nearest_wall_strike = nearest.strike
        c.nearest_wall_distance_pct = round(distance_pct, 2)

        if distance_pct < config.proximity_pct:
            c.reject(
                "proximity",
                f"short strike {c.short_strike} within {distance_pct:.2f}% "
                f"of {nearest.wall_type} wall at {nearest.strike} "
                f"(OI={nearest.total_oi:,})"
            )
        else:
            c.tag(f"proximity:clear ({distance_pct:.2f}% from nearest wall)")

    passed_count = sum(1 for c in candidates if c.passed)
    logger.info(f"Wall proximity: {passed_count}/{len(candidates)} candidates passed")
    return candidates


def _get_relevant_walls(
    candidate: CandidateSpread,
    walls: list[OIWall],
    config: ProximityConfig,
) -> list[OIWall]:
    """
    Get walls relevant to this candidate's spread type.

    same_side_only:
      - Bull puts → support walls (below price) only
      - Bear calls → resistance walls (above price) only

    any:
      - All walls
    """
    if config.direction == "any":
        return walls

    relevant = []
    for w in walls:
        if candidate.spread_type == "bull_put_credit" and w.wall_type == "support":
            # Only care about support walls that could be breached downward
            if w.strike < candidate.short_strike:
                relevant.append(w)
        elif candidate.spread_type == "bear_call_credit" and w.wall_type == "resistance":
            # Only care about resistance walls that could be breached upward
            if w.strike > candidate.short_strike:
                relevant.append(w)

    return relevant
