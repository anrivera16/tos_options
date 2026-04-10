"""
Calendar Spread Opportunity Signal

Scores the quality of a calendar spread trade setup.

Key factors in the score:
1. Violation Severity (35%): How inverted is the term structure?
2. Theta Accumulation (30%): How much time decay will we collect?
3. IV Regime (20%): Is IV low enough to safely sell premium?
4. Momentum (15%): Is the inversion getting worse (good entry) or recovering?

Score Interpretation:
- 0.0-0.4: Poor opportunity, likely won't profit
- 0.4-0.6: Marginal, trade only with strict stops
- 0.6-0.8: Good opportunity, normal entry conditions
- 0.8-1.0: Excellent opportunity, textbook setup
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import math

from .base import Signal
from .calendar_spread_violation import get_expiration_pair


def score_violation_severity(violation_severity: float, scale: float = 0.015) -> float:
    """
    Score based on severity of inversion.

    Args:
        violation_severity: abs(iv_slope) when inverted
        scale: Maximum severity we consider (e.g., 0.015 = 150 bps)

    Returns:
        Score from 0 to 1.0
    """
    if violation_severity <= 0:
        return 0.0

    score = min(violation_severity / scale, 1.0)
    return score


def score_theta_accumulation(front_dte: int, back_dte: int) -> float:
    """
    Score based on theta (time decay) opportunity.

    Optimal range: Front month is 15-45 DTE
    (30 DTE is classic calendar spread maturity)

    Args:
        front_dte: Days to expiration (front month)
        back_dte: Days to expiration (back month)

    Returns:
        Score from 0 to 1.0
    """

    # Sweet spot: 20-50 DTE front month
    if 20 <= front_dte <= 50:
        # Higher score for middle of range
        distance_from_center = abs(front_dte - 35) / 15
        return 1.0 - (distance_from_center * 0.2)  # 0.8-1.0 in sweet spot

    # Acceptable: 15-70 DTE
    if 15 <= front_dte <= 70:
        return 0.7

    # Not ideal: Too short or too long
    if front_dte < 15:
        return max(0.3, front_dte / 15 * 0.5)  # Decay below 15 DTE

    if front_dte > 70:
        return 0.4  # Too much time, theta accrues slowly

    return 0.0


def score_iv_regime(front_atm_iv: float, back_atm_iv: float) -> float:
    """
    Score based on absolute IV level (how safe is it to sell premium?).

    Low IV (10-15%): Very safe, high probability of profit
    Medium IV (15-25%): Safe, good for selling
    High IV (25-50%): Risky, potential for large adverse moves
    Extreme IV (50%+): Dangerous, avoid

    Args:
        front_atm_iv: IV of front month (decimal, e.g., 0.173)
        back_atm_iv: IV of back month (decimal)

    Returns:
        Score from 0 to 1.0
    """

    # Use average IV as regime indicator
    avg_iv = (front_atm_iv + back_atm_iv) / 2

    # Optimal range: 12-20% IV
    if 0.12 <= avg_iv <= 0.20:
        distance_from_center = abs(avg_iv - 0.16) / 0.04
        return 1.0 - (distance_from_center * 0.15)  # 0.85-1.0

    # Acceptable: 10-25%
    if 0.10 <= avg_iv <= 0.25:
        return 0.75

    # Elevated: 25-35%
    if 0.25 < avg_iv <= 0.35:
        return 0.5  # Riskier, smaller edge

    # Dangerous: > 35%
    if avg_iv > 0.35:
        return 0.2  # High risk, require exceptional setup

    # Very low: < 10% (rare, but very profitable)
    if avg_iv < 0.10:
        return 0.6  # Good profitability but narrow

    return 0.0


def score_momentum(
    current_iv_slope: float,
    prior_iv_slope: float | None,
    window_size: int = 3,
) -> float:
    """
    Score based on violation momentum (trend).

    Intensifying inversion (getting worse): Good signal - entry likely profitable
    Easing inversion (recovering): Warning - might expire before profit
    Stable: Neutral

    Args:
        current_iv_slope: Current front_iv - back_iv
        prior_iv_slope: IV slope from previous bar
        window_size: Not used here, but for consistency

    Returns:
        Score from 0 to 1.0
    """

    if prior_iv_slope is None:
        return 0.5  # Neutral if we can't compute momentum

    slope_change = current_iv_slope - prior_iv_slope

    # Negative slope_change = inversion getting WORSE = GOOD for calendar spread
    # (We're selling expensive vol that's becoming even more expensive)

    if slope_change < -0.002:  # Getting worse by 20+ bps
        return 1.0  # Excellent momentum

    if slope_change < 0:  # Getting slightly worse
        return 0.8  # Good momentum

    if slope_change < 0.002:  # Stable (little change)
        return 0.5  # Neutral momentum

    if slope_change < 0.005:  # Getting slightly better
        return 0.3  # Warning: inversion easing

    # Easing rapidly
    return 0.1


def compute_confidence(
    opportunity_score: float,
    violation_severity: float,
    days_until_expiry: int,
    prior_slope: float | None,
) -> float:
    """
    Compute overall confidence in the opportunity.

    Factors:
    - High opportunity score + confirmed by streak = higher confidence
    - Decay as front month gets very close (< 5 DTE)
    - Reduce confidence if inversion is easing

    Returns:
        0.0 to 1.0 confidence score
    """

    # Start with opportunity score
    confidence = opportunity_score

    # Penalty if front month is too close (hard to manage)
    if days_until_expiry < 5:
        confidence *= 0.6  # Reduce by 40%
    elif days_until_expiry < 10:
        confidence *= 0.8  # Reduce by 20%

    # Penalty if violation is very small (insufficient edge)
    if violation_severity < 0.003:
        confidence *= 0.7

    return max(0.0, min(confidence, 1.0))


class CalendarSpreadOpportunity(Signal):
    """
    Score the quality of calendar spread opportunities.

    Inputs:
    - Current term structure violation (from CalendarSpreadViolation signal)
    - Prior term structure data (from database history)
    - Current IV regime
    - Days to expiration

    Outputs:
    - Opportunity score (0-1)
    - Component scores (severity, theta, regime, momentum)
    - Trade setup recommendation
    - Confidence level
    """

    name = "calendar_spread_opportunity"
    table = "signal_calendar_opportunities"

    # Thresholds for trading
    MINIMUM_OPPORTUNITY_SCORE = 0.50  # Don't trade below this
    IDEAL_OPPORTUNITY_SCORE = 0.70  # Target this

    def compute(self, snapshot_id: int, db_conn: Any) -> None:
        """
        Score the current calendar spread opportunity.
        """

        # Get the violation data for this snapshot (should be recent)
        violation = self._get_latest_violation(snapshot_id, db_conn)

        if not violation:
            return

        # Ensure this violation is indeed an opportunity
        if not violation.get("is_violation"):
            return

        # Get prior violation for momentum calculation
        prior_violation = self._get_prior_violation(violation, db_conn)

        # Compute component scores
        severity_score = score_violation_severity(violation["violation_severity"] or 0)

        theta_score = score_theta_accumulation(
            violation["front_dte"] or 0, violation["back_dte"] or 0
        )

        iv_regime_score = score_iv_regime(
            violation["front_atm_iv"] or 0.17, violation["back_atm_iv"] or 0.17
        )

        momentum_score = score_momentum(
            violation["iv_slope"] or 0,
            prior_violation["iv_slope"] if prior_violation else None,
        )

        # Weighted combination
        opportunity_score = (
            0.35 * severity_score
            + 0.30 * theta_score
            + 0.20 * iv_regime_score
            + 0.15 * momentum_score
        )

        # Compute confidence
        confidence = compute_confidence(
            opportunity_score,
            violation["violation_severity"] or 0,
            violation["front_dte"] or 0,
            prior_violation["iv_slope"] if prior_violation else None,
        )

        # Suggested strike is ATM (safest)
        strike = violation["front_atm_strike"]

        # Estimate theta decay for hold period
        # Rough estimate: 1 day of 30 DTE call ≈ 0.5% of value
        estimated_theta_daily = 0.005

        # Entry cost estimate (use rough bid-ask)
        # Assuming ~$2 bid-ask on the spread
        estimated_entry_cost = 2.0

        # Max profit = full spread width (approximately) - entry cost
        # For ATM spreads, rough estimate = 0.5-1.0% of strike
        max_spread_width = strike * 0.01
        estimated_max_profit = max(max_spread_width - estimated_entry_cost, 0.50)

        # Determine entry signal type
        entry_signal = "short_call_spread"  # Default
        if violation.get("back_atm_iv", 0) > violation.get("front_atm_iv", 0):
            # Back month more expensive - shorter puts instead
            entry_signal = "short_put_spread"

        # Store opportunity
        db_conn.execute(
            """
            INSERT INTO signal_calendar_opportunities
                (snapshot_id, symbol, captured_at, violation_id,
                 opportunity_score, severity_score, theta_score, 
                 iv_regime_score, momentum_score, confidence,
                 entry_signal, suggested_strike, suggested_quantity,
                 estimated_entry_cost, estimated_max_profit,
                 optimal_hold_days, days_to_roll)
            VALUES (%(snapshot_id)s, %(symbol)s, %(captured_at)s, %(violation_id)s,
                    %(opp_score)s, %(sev_score)s, %(theta_score)s,
                    %(iv_score)s, %(mom_score)s, %(confidence)s,
                    %(entry_signal)s, %(strike)s, %(qty)s,
                    %(entry_cost)s, %(max_profit)s,
                    %(hold_days)s, %(roll_days)s)
            """,
            {
                "snapshot_id": snapshot_id,
                "symbol": violation["symbol"],
                "captured_at": violation["captured_at"],
                "violation_id": violation["id"],
                "opp_score": opportunity_score,
                "sev_score": severity_score,
                "theta_score": theta_score,
                "iv_score": iv_regime_score,
                "mom_score": momentum_score,
                "confidence": confidence,
                "entry_signal": entry_signal,
                "strike": strike,
                "qty": 1,
                "entry_cost": estimated_entry_cost,
                "max_profit": estimated_max_profit,
                "hold_days": max(3, (violation["back_dte"] or 1) // 2),
                "roll_days": (violation["front_dte"] or 1) - 3,
            },
        )

        db_conn.commit()

    def _get_latest_violation(self, snapshot_id: int, db_conn: Any) -> dict | None:
        """Get the violation record for this snapshot."""
        result = db_conn.execute(
            """
            SELECT * FROM signal_calendar_violations
            WHERE snapshot_id = %s
            """,
            [snapshot_id],
        ).fetchone()
        return result

    def _get_prior_violation(self, violation: dict, db_conn: Any) -> dict | None:
        """Get the prior violation for momentum calculation."""
        result = db_conn.execute(
            """
            SELECT * FROM signal_calendar_violations
            WHERE symbol = %s
              AND captured_at < %s
            ORDER BY captured_at DESC
            LIMIT 1
            """,
            [violation["symbol"], violation["captured_at"]],
        ).fetchone()
        return result

    def get_best_opportunities(
        self,
        symbol: str,
        limit: int = 5,
        db_conn: Any = None,
    ) -> list[dict]:
        """
        Get the best calendar spread opportunities for a symbol.

        Ranked by opportunity_score, filtered by minimum confidence.
        """
        results = db_conn.execute(
            """
            SELECT * FROM signal_calendar_opportunities
            WHERE symbol = %s
              AND confidence > 0.5
            ORDER BY opportunity_score DESC
            LIMIT %s
            """,
            [symbol, limit],
        ).fetchall()

        return results or []
