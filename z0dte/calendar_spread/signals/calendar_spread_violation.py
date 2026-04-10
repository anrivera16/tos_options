"""
Calendar Spread Violation Signal

Detects when the volatility term structure is inverted:
- Front-month IV > Back-month IV

This is a profitable setup for calendar spreads because:
1. You sell the expensive front-month options
2. You buy the cheaper back-month options
3. As time passes, the front-month decays faster
4. As the term structure normalizes, you profit

Example:
    - Front (30 DTE): 17.3% IV
    - Back (60 DTE): 16.8% IV
    - Slope: +50 basis points (INVERTED - an opportunity!)

    Entry: Sell 30 DTE Call Spread, Buy 60 DTE Call Spread
    Hold: 5-10 days until theta does its work
    Exit: When front month decays or back month rises (normalizes)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .base import Signal


def find_atm_strike(contracts: list[dict], underlying_price: float) -> float | None:
    """Find the strike closest to underlying price."""
    strikes = sorted(set(c["strike"] for c in contracts if c.get("strike") is not None))
    if not strikes:
        return None
    return min(strikes, key=lambda s: abs(s - underlying_price))


def extract_atm_iv(
    contracts: list[dict],
    expiration_date: str,
    atm_strike: float | None,
) -> float | None:
    """Extract ATM IV for a specific expiration."""
    if atm_strike is None:
        return None

    atm_contracts = [
        c
        for c in contracts
        if str(c.get("expiration_date") or "") == str(expiration_date)
        and c.get("strike") == atm_strike
        and c.get("volatility") is not None
        and c.get("volatility", 0) > 0
    ]

    if not atm_contracts:
        return None

    # Average call and put IV at this strike
    ivs = [c["volatility"] for c in atm_contracts]
    return sum(ivs) / len(ivs)


def get_expiration_pair(contracts: list[dict]) -> tuple[str, str] | None:
    """
    Get the two nearest expirations with valid IV data.
    Returns (front_expiry, back_expiry)
    """
    expirations_with_iv = {}

    for c in contracts:
        exp = str(c.get("expiration_date") or "")
        iv = c.get("volatility")

        if exp and iv and iv > 0:
            if exp not in expirations_with_iv:
                expirations_with_iv[exp] = []
            expirations_with_iv[exp].append(iv)

    # Need at least 2 expirations with valid IV
    if len(expirations_with_iv) < 2:
        return None

    # Sort by date
    sorted_exps = sorted(expirations_with_iv.keys())
    return (sorted_exps[0], sorted_exps[1])


def days_to_expiration(expiry_date: str, current_date: datetime) -> int:
    """Calculate days to expiration."""
    try:
        # Parse expiry_date (assume YYYY-MM-DD format)
        exp = datetime.strptime(str(expiry_date), "%Y-%m-%d")
        delta = exp - current_date.replace(hour=0, minute=0, second=0, microsecond=0)
        return max(0, delta.days)
    except:
        return 0


class CalendarSpreadViolation(Signal):
    """
    Detect term structure violations (inverted slopes).

    Configuration:
    - VIOLATION_THRESHOLD: Minimum inversion to flag as opportunity (in decimals, e.g., 0.005 = 50 bps)
    - SEVERITY_SCALE: For scoring severity from 0-1
    """

    name = "calendar_spread_violation"
    table = "signal_calendar_violations"

    # A term structure violation occurs when near-term vol is 50+ bps higher than back-term
    VIOLATION_THRESHOLD = 0.005  # 50 basis points
    SEVERITY_SCALE = 0.015  # Scale for converting bps to 0-1 score

    def compute(self, snapshot_id: int, db_conn: Any) -> None:
        """
        For each snapshot, compute the IV term structure and detect violations.

        A violation is when:
            front_iv - back_iv < -VIOLATION_THRESHOLD

        Which means:
            back_iv > front_iv + threshold

        This is unusual because typically term structure is upward sloping
        (longer-dated options have higher IV due to more uncertainty).
        """

        # Load contract data for this snapshot
        contracts = self._load_contracts(snapshot_id, db_conn)
        snapshot = self._load_snapshot(snapshot_id, db_conn)

        if not contracts:
            return

        # Get the two nearest expirations
        expiry_pair = get_expiration_pair(contracts)
        if not expiry_pair:
            return

        front_expiry, back_expiry = expiry_pair

        # Find ATM strike
        underlying_price = snapshot.get("underlying_price")
        if not underlying_price:
            return

        atm_strike = find_atm_strike(contracts, underlying_price)
        if not atm_strike:
            return

        # Extract ATM IVs for each expiration
        front_iv = extract_atm_iv(contracts, front_expiry, atm_strike)
        back_iv = extract_atm_iv(contracts, back_expiry, atm_strike)

        if not front_iv or not back_iv:
            return

        # Compute term structure metrics
        iv_slope = front_iv - back_iv  # Negative = inverted
        is_violation = iv_slope < -self.VIOLATION_THRESHOLD
        violation_severity = abs(iv_slope) if is_violation else 0.0
        violation_bps = int(iv_slope * 10000)  # Convert to basis points

        # Calculate DTE
        front_dte = days_to_expiration(front_expiry, snapshot["captured_at"])
        back_dte = days_to_expiration(back_expiry, snapshot["captured_at"])

        # Store in database
        db_conn.execute(
            """
            INSERT INTO signal_calendar_violations
                (snapshot_id, symbol, captured_at,
                 front_expiry, front_atm_strike, front_atm_iv,
                 back_expiry, back_atm_strike, back_atm_iv,
                 iv_slope, violation_severity, is_violation, violation_basis_points,
                 front_dte, back_dte, underlying_price)
            VALUES (%(snapshot_id)s, %(symbol)s, %(captured_at)s,
                    %(front_expiry)s, %(front_strike)s, %(front_iv)s,
                    %(back_expiry)s, %(back_strike)s, %(back_iv)s,
                    %(iv_slope)s, %(severity)s, %(is_violation)s, %(bps)s,
                    %(front_dte)s, %(back_dte)s, %(underlying_price)s)
            """,
            {
                "snapshot_id": snapshot_id,
                "symbol": snapshot["symbol"],
                "captured_at": snapshot["captured_at"],
                "front_expiry": front_expiry,
                "front_strike": atm_strike,
                "front_iv": front_iv,
                "back_expiry": back_expiry,
                "back_strike": atm_strike,
                "back_iv": back_iv,
                "iv_slope": iv_slope,
                "severity": violation_severity,
                "is_violation": is_violation,
                "bps": violation_bps,
                "front_dte": front_dte,
                "back_dte": back_dte,
                "underlying_price": underlying_price,
            },
        )

        db_conn.commit()

    def get_latest_violation(self, symbol: str, db_conn: Any) -> dict | None:
        """Get the most recent violation record for a symbol."""
        result = db_conn.execute(
            """
            SELECT * FROM signal_calendar_violations
            WHERE symbol = %s
            ORDER BY captured_at DESC
            LIMIT 1
            """,
            [symbol],
        ).fetchone()
        return result

    def get_current_streak(self, symbol: str, db_conn: Any) -> dict | None:
        """
        Analyze the current streak of violations.

        Returns:
            {
                "is_violation": bool,
                "streak_length": int,  # How many consecutive bars with violation
                "avg_severity": float,
                "trend": "intensifying" | "easing" | "stable"
            }
        """

        # Get last 10 violations
        results = db_conn.execute(
            """
            SELECT is_violation, violation_severity, captured_at
            FROM signal_calendar_violations
            WHERE symbol = %s
            ORDER BY captured_at DESC
            LIMIT 10
            """,
            [symbol],
        ).fetchall()

        if not results:
            return None

        # Count consecutive violations from the top
        streak_length = 0
        severities = []
        for row in results:
            if row["is_violation"]:
                streak_length += 1
                severities.append(row["violation_severity"])
            else:
                break

        if streak_length == 0:
            return None

        # Compute trend
        if len(severities) >= 2:
            recent_avg = sum(severities[:3]) / len(severities[:3])  # Last 3
            older_avg = (
                sum(severities[3:]) / len(severities[3:])
                if len(severities) > 3
                else recent_avg
            )

            if recent_avg > older_avg * 1.1:  # 10% increase
                trend = "intensifying"
            elif recent_avg < older_avg * 0.9:  # 10% decrease
                trend = "easing"
            else:
                trend = "stable"
        else:
            trend = "stable"

        return {
            "is_violation": True,
            "streak_length": streak_length,
            "avg_severity": sum(severities) / len(severities),
            "trend": trend,
        }
