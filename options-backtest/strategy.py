#!/usr/bin/env python3
"""Core strategy logic for bull put credit spread backtesting.

All pure functions, no I/O. Testable in isolation.

Bull Put Credit Spread:
  - SELL put at K_short (higher strike)
  - BUY  put at K_long  (lower strike, protection)
  - Credit received = short premium - long premium
  - Max profit = credit (both expire OTM)
  - Max loss   = (K_short - K_long) - credit  (both expire ITM)
  - Breakeven  = K_short - credit
"""

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# P&L Calculation
# ---------------------------------------------------------------------------

def compute_pnl(trade: dict, expiry_data: pd.DataFrame) -> dict:
    """Compute P&L at expiry for a bull put credit spread.

    Args:
        trade: dict with short_strike, long_strike, short_premium, long_premium,
               actual_width, short_ticker, long_ticker
        expiry_data: DataFrame with ticker, close columns for the expiry date

    Returns:
        dict with credit, pnl_per_contract, max_loss, result, anomalous flag,
        short_close, long_close
    """
    short_close = _get_close(expiry_data, trade["short_ticker"])
    long_close = _get_close(expiry_data, trade["long_ticker"])

    credit = trade["short_premium"] - trade["long_premium"]  # per share
    width = trade["actual_width"]
    max_profit = credit        # per share
    max_loss = width - credit  # per share

    # Missing data
    if short_close is None or long_close is None:
        return {
            "credit": round(credit, 3),
            "pnl_per_contract": None,
            "max_loss": round(max_loss * 100, 2),
            "result": "NO_EXPIRY_DATA" if short_close is None and long_close is None else "MISSING_DATA",
            "short_close": short_close,
            "long_close": long_close,
            "anomalous": False,
        }

    # Raw P&L calculation:
    # Opening: receive credit = short premium - long premium
    # Closing: pay to close = short close - long close
    # P&L = credit - close_cost
    close_cost = short_close - long_close
    raw_pnl = credit - close_cost

    # Check for data anomalies (P&L outside theoretical bounds)
    anomalous = False
    if raw_pnl > max_profit + 0.05 or raw_pnl < -max_loss - 0.05:
        anomalous = True

    # Bound P&L to theoretical limits
    bounded_pnl = max(-max_loss, min(max_profit, raw_pnl))
    pnl_per_contract = round(bounded_pnl * 100, 2)

    result = classify_trade(bounded_pnl, credit, width)

    return {
        "credit": round(credit, 3),
        "pnl_per_contract": pnl_per_contract,
        "max_loss": round(max_loss * 100, 2),
        "result": result,
        "short_close": round(short_close, 3),
        "long_close": round(long_close, 3),
        "anomalous": anomalous,
    }


def classify_trade(pnl: float, credit: float, width: float) -> str:
    """Classify a trade outcome based on P&L.

    Args:
        pnl: P&L per share
        credit: credit received per share
        width: spread width per share

    Returns:
        One of: FULL_WIN, PARTIAL_WIN, PUSH, PARTIAL_LOSS, MAX_LOSS, ANOMALOUS
    """
    max_profit = credit
    max_loss = width - credit
    tolerance = 0.05  # 5 cent tolerance for boundary cases

    # Anomalous: outside theoretical bounds
    if pnl > max_profit + tolerance:
        return "ANOMALOUS"
    if pnl < -max_loss - tolerance:
        return "ANOMALOUS"

    # Full win: P&L at or near max profit (within 3% of credit)
    if abs(pnl - max_profit) <= max(tolerance, credit * 0.03):
        return "FULL_WIN"

    # Max loss: P&L at or near max loss (within 2.5% of max loss)
    if abs(pnl + max_loss) <= max(tolerance, max_loss * 0.025):
        return "MAX_LOSS"

    # Push: breakeven (within $1 per contract = $0.01 per share)
    if abs(pnl) <= 0.01:
        return "PUSH"

    # Partial win/loss
    if pnl > 0:
        return "PARTIAL_WIN"
    else:
        return "PARTIAL_LOSS"


def _get_close(expiry_data: pd.DataFrame, ticker: str) -> Optional[float]:
    """Get the closing price for a specific ticker from expiry data."""
    if expiry_data.empty:
        return None
    match = expiry_data[expiry_data["ticker"] == ticker]
    if match.empty:
        return None
    return float(match.iloc[0]["close"])


# ---------------------------------------------------------------------------
# Spread Selection
# ---------------------------------------------------------------------------

def select_spread(day_puts: pd.DataFrame, dte_range: tuple, width: float,
                  delta_pct: float) -> Optional[dict]:
    """Select a bull put credit spread for a given day.

    Strategy:
    1. Filter puts to the target DTE range
    2. Pick the expiry closest to dte_range[1] (prefer longer DTE)
    3. Rank puts by strike to approximate delta
    4. Select short leg at ~delta_pct percentile OTM
    5. Select long leg at short_strike - width

    For puts: higher strike = more ITM, lower strike = more OTM
    So to pick an OTM put, we go below ATM.

    Args:
        day_puts: DataFrame of puts for a single day (must have: strike, open,
                  volume, dte, expiry, ticker, date)
        dte_range: (min_dte, max_dte) inclusive
        width: desired spread width in dollars
        delta_pct: target delta for short leg (e.g. 15 = 15 delta)

    Returns:
        dict with trade details, or None if no valid spread found
    """
    if day_puts.empty:
        return None

    dte_lo, dte_hi = dte_range
    candidates = day_puts[
        (day_puts["dte"] >= dte_lo) & (day_puts["dte"] <= dte_hi)
    ].copy()

    if candidates.empty:
        return None

    # Find the best expiry: closest to dte_hi (prefer 7 DTE over 5)
    expiry_dte = {}
    for expiry, grp in candidates.groupby("expiry"):
        dte = int(grp["dte"].iloc[0])
        expiry_dte[expiry] = dte

    if not expiry_dte:
        return None

    best_expiry = min(expiry_dte.keys(), key=lambda e: abs(expiry_dte[e] - dte_hi))
    best_dte = expiry_dte[best_expiry]

    expiry_puts = candidates[candidates["expiry"] == best_expiry].copy()
    if len(expiry_puts) < 2:
        return None

    # Sort strikes descending (ITM -> OTM for puts)
    strikes = expiry_puts.sort_values("strike", ascending=False)

    # Approximate delta selection:
    # Rank 0 = most ITM (highest strike), Rank N-1 = most OTM (lowest strike)
    # For a 15 delta short put, we want ~15% of puts below ATM
    # Use percentile from the ITM end: index = n * (delta_pct / 100)
    n = len(strikes)
    idx = int(n * (delta_pct / 100))

    # Ensure we have room for the long leg below
    idx = max(1, min(idx, n - 2))

    short_leg = strikes.iloc[idx]

    # Find long leg: closest strike to (short_strike - width)
    target_long_strike = short_leg["strike"] - width
    long_candidates = strikes[strikes["strike"] <= short_leg["strike"] - width]

    if long_candidates.empty:
        # Can't build the spread, not enough strike range
        return None

    # Pick the long leg closest to the target width
    long_leg = long_candidates.iloc[
        (long_candidates["strike"] - target_long_strike).abs().argsort().iloc[0]
    ]

    actual_width = short_leg["strike"] - long_leg["strike"]

    # Sanity: width should be positive and reasonable
    if actual_width <= 0 or actual_width > width * 2:
        return None

    return {
        "short_strike": short_leg["strike"],
        "long_strike": long_leg["strike"],
        "short_premium": short_leg["open"],
        "long_premium": long_leg["open"],
        "expiry": best_expiry,
        "dte": best_dte,
        "short_ticker": short_leg["ticker"],
        "long_ticker": long_leg["ticker"],
        "actual_width": actual_width,
    }


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def build_trading_days(start_str: str, end_str: str) -> list:
    """Generate weekday dates between start and end (inclusive).

    Does NOT account for market holidays -- those are handled by
    the download step (404s are expected and skipped).
    """
    start = datetime.strptime(start_str, "%Y-%m-%d").date()
    end = datetime.strptime(end_str, "%Y-%m-%d").date()
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days
