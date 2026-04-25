"""
Spread Scoring — rank spread candidates by composite score.

Each spread type has its own scoring weights tuned to what matters for that structure.
"""

from __future__ import annotations

import math
import logging
from typing import Any

from spread_hunter.spread_types import (
    AnySpread,
    CalendarSpread,
    IronCondor,
    IronFly,
    VerticalSpread,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Vertical spread scoring (bull put credit, bear call credit)
# ---------------------------------------------------------------------------

def score_vertical(spread: VerticalSpread) -> float:
    """
    Score a vertical spread. Higher = more attractive.

    Components:
      - ROI% (want high)              30% — normalize 10-60%
      - Distance OTM (want high)      25% — further from price = safer
      - Liquidity (want high)         20% — log-scaled OI
      - Theta/credit ratio (want low) 15% — less time cost per dollar
      - Bid-ask tightness (want low)  10% — tighter = better fills
    """
    # ROI normalization: 10% = 0, 60% = 1, cap at 1.5
    roi_score = min(max((spread.roi_pct - 10) / 50.0, 0.0), 1.5)

    # Distance OTM as % of underlying price
    if spread.underlying_price > 0:
        if spread.is_credit:
            # Distance from short strike to underlying
            dist = abs(spread.underlying_price - spread.short_leg.strike)
        else:
            dist = abs(spread.underlying_price - spread.long_leg.strike)
        dist_pct = dist / spread.underlying_price * 100.0
        # 2% = 0, 10% = 1
        dist_score = min(max((dist_pct - 2) / 8.0, 0.0), 1.0)
    else:
        dist_score = 0.0

    # Liquidity: log-scaled OI
    oi = max(spread.min_oi, 1)
    oi_score = min(max((math.log10(oi) - 1.5) / 2.5, 0.0), 1.0)  # 30 = 0, 10000 = 1

    # Theta/credit: lower ratio = better (theta decay works for you)
    theta_ratio_score = 0.5  # neutral default
    if spread.net_theta is not None and spread.net_premium > 0:
        # For credit spreads, net_theta should be positive (good)
        # Ratio of |theta| / credit_per_day
        daily_credit = spread.net_premium / max(spread.dte, 1)
        if daily_credit > 0:
            theta_ratio = abs(spread.net_theta) / daily_credit
            # 0.05 = great (1.0), 0.5 = poor (0.0)
            theta_ratio_score = max(1.0 - (theta_ratio / 0.5), 0.0)

    # Bid-ask spread: tighter = better
    spread_score = max(1.0 - (spread.max_spread_pct / 25.0), 0.0)

    composite = (
        roi_score * 0.30
        + dist_score * 0.25
        + oi_score * 0.20
        + theta_ratio_score * 0.15
        + spread_score * 0.10
    )

    return round(composite, 4)


# ---------------------------------------------------------------------------
# Iron Condor scoring
# ---------------------------------------------------------------------------

def score_iron_condor(ic: IronCondor) -> float:
    """
    Score an iron condor.

    Components:
      - ROI% (want high)                25%
      - Breakeven range width (want wide) 25% — wider range = more room
      - Liquidity (want high)           20%
      - Net theta (want positive)       15%
      - Wing symmetry (want balanced)   15%
    """
    # ROI
    roi_score = min(max((ic.roi_pct - 10) / 40.0, 0.0), 1.5)

    # Breakeven range as % of underlying
    if ic.underlying_price > 0:
        range_pct = (ic.breakeven_high - ic.breakeven_low) / ic.underlying_price * 100.0
        # 2% = 0, 8% = 1
        range_score = min(max((range_pct - 2) / 6.0, 0.0), 1.0)
    else:
        range_score = 0.0

    # Liquidity
    oi = max(ic.min_oi, 1)
    oi_score = min(max((math.log10(oi) - 1.5) / 2.5, 0.0), 1.0)

    # Net theta (positive = good for credit)
    theta_score = 0.5
    if ic.net_theta is not None:
        # Normalize: 0 = neutral, 0.05 = good, 0.15 = great
        theta_score = min(max(ic.net_theta / 0.15, 0.0), 1.0)

    # Wing symmetry
    sym_score = 0.0
    if ic.put_width > 0 and ic.call_width > 0:
        ratio = min(ic.put_width, ic.call_width) / max(ic.put_width, ic.call_width)
        # 1.0 = perfect symmetry, 0.5 = still ok
        sym_score = min(ratio * 1.5, 1.0)

    composite = (
        roi_score * 0.25
        + range_score * 0.25
        + oi_score * 0.20
        + theta_score * 0.15
        + sym_score * 0.15
    )

    return round(composite, 4)


# ---------------------------------------------------------------------------
# Iron Fly scoring
# ---------------------------------------------------------------------------

def score_iron_fly(fly: IronFly) -> float:
    """
    Score an iron fly (pinning play).

    Components:
      - ROI% (want high)                30% — flys need good risk/reward
      - Center strike proximity to ATM  25% — closer = better for pinning
      - Liquidity (want high)           20%
      - Net theta (want positive)       15%
      - Credit relative to width        10%
    """
    roi_score = min(max((fly.roi_pct - 15) / 50.0, 0.0), 1.5)

    # Proximity of center to current price
    if fly.underlying_price > 0:
        prox = abs(fly.center_strike - fly.underlying_price) / fly.underlying_price * 100.0
        # 0% = perfect (1.0), 1% = ok (0.5), 2% = bad (0.0)
        prox_score = max(1.0 - prox / 2.0, 0.0)
    else:
        prox_score = 0.0

    oi = max(fly.min_oi, 1)
    oi_score = min(max((math.log10(oi) - 1.5) / 2.5, 0.0), 1.0)

    theta_score = 0.5
    if fly.net_theta is not None:
        theta_score = min(max(fly.net_theta / 0.15, 0.0), 1.0)

    # Credit per unit width
    max_wing = max(fly.put_width, fly.call_width, 1)
    credit_eff = fly.total_credit / max_wing
    credit_score = min(max(credit_eff / 0.5, 0.0), 1.0)

    composite = (
        roi_score * 0.30
        + prox_score * 0.25
        + oi_score * 0.20
        + theta_score * 0.15
        + credit_score * 0.10
    )

    return round(composite, 4)


# ---------------------------------------------------------------------------
# Calendar spread scoring
# ---------------------------------------------------------------------------

def score_calendar(cal: CalendarSpread) -> float:
    """
    Score a calendar spread.

    Components:
      - Theta/vega ratio (want high positive theta, positive vega)  30%
      - IV contango (near > far)                                    25%
      - Liquidity (want high)                                       20%
      - DTE gap (7-21 days ideal)                                   15%
      - Debit cost relative to strike (want cheap)                  10%
    """
    # Theta/vega efficiency
    tv_score = 0.0
    if cal.net_theta is not None and cal.net_vega is not None:
        if cal.net_vega != 0:
            # Positive theta per unit of vega risk
            ratio = cal.net_theta / abs(cal.net_vega) if cal.net_vega != 0 else 0
            tv_score = min(max(ratio / 2.0, 0.0), 1.0)
        elif cal.net_theta > 0:
            tv_score = 0.7

    # IV contango bonus
    iv_score = 0.5  # neutral
    if cal.iv_diff is not None:
        # positive = near IV > far IV = contango = good
        iv_score = min(max((cal.iv_diff + 5) / 15.0, 0.0), 1.0)

    # Liquidity
    oi = max(cal.min_oi, 1)
    oi_score = min(max((math.log10(oi) - 1.5) / 2.5, 0.0), 1.0)

    # DTE gap: sweet spot is 7-21 days
    gap = cal.far_dte - cal.near_dte
    if 7 <= gap <= 21:
        gap_score = 1.0
    elif gap < 7:
        gap_score = gap / 7.0
    else:
        gap_score = max(1.0 - (gap - 21) / 15.0, 0.0)

    # Debit cost relative to strike
    if cal.strike > 0:
        cost_pct = cal.debit / cal.strike * 100.0
        # 0.5% = cheap (1.0), 3% = expensive (0.0)
        cost_score = max(1.0 - (cost_pct - 0.5) / 2.5, 0.0)
    else:
        cost_score = 0.0

    composite = (
        tv_score * 0.30
        + iv_score * 0.25
        + oi_score * 0.20
        + gap_score * 0.15
        + cost_score * 0.10
    )

    return round(composite, 4)


# ---------------------------------------------------------------------------
# Apply scoring
# ---------------------------------------------------------------------------

def score_all(results: dict[str, list[AnySpread]]) -> dict[str, list[AnySpread]]:
    """Score and sort all spread candidates. Returns new dict (does not mutate)."""
    scored: dict[str, list[AnySpread]] = {}

    for stype, spreads in results.items():
        for s in spreads:
            if isinstance(s, VerticalSpread):
                s.score = score_vertical(s)
            elif isinstance(s, IronCondor):
                s.score = score_iron_condor(s)
            elif isinstance(s, IronFly):
                s.score = score_iron_fly(s)
            elif isinstance(s, CalendarSpread):
                s.score = score_calendar(s)

        # Sort by score descending
        sorted_spreads = sorted(spreads, key=lambda s: s.score, reverse=True)
        scored[stype] = sorted_spreads

    return scored
