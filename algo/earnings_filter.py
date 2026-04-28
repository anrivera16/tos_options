"""
Module 4: Earnings Filter

Black out trading around earnings dates for major SPY holdings.
SPY itself doesn't have earnings, but big moves in top holdings
can swing the index enough to hurt 5-9 DTE spreads.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from algo.types import CandidateSpread
from algo.config import EarningsConfig

logger = logging.getLogger(__name__)


# Static earnings calendar — update quarterly.
# Format: {ticker: [date_strings, ...]}
# For SPY strategies, we care about top holdings' earnings.
DEFAULT_EARNINGS_DATES: dict[str, list[str]] = {
    # Q1 2026 (Jan-Apr)
    "AAPL": ["2026-01-29", "2026-04-30"],
    "MSFT": ["2026-01-28", "2026-04-29"],
    "AMZN": ["2026-02-06", "2026-05-01"],
    "GOOGL": ["2026-02-04", "2026-04-29"],
    "META": ["2026-01-29", "2026-04-30"],
    "NVDA": ["2026-02-26", "2026-05-28"],
    "TSLA": ["2026-01-29", "2026-04-23"],
    "BRK.B": ["2026-02-22", "2026-05-03"],
}


def load_earnings_calendar(config: EarningsConfig | None = None) -> dict[str, list[str]]:
    """
    Load earnings dates. For now uses the static dict above.
    Could be extended to fetch from an API.
    """
    return DEFAULT_EARNINGS_DATES


def is_in_blackout(
    entry_date: str | None,
    expiry_date: str | None,
    earnings_dates: dict[str, list[str]],
    config: EarningsConfig,
) -> tuple[bool, str]:
    """
    Check if the trade period overlaps with any earnings blackout window.

    Returns (in_blackout, reason).
    """
    if not entry_date or not expiry_date:
        return False, ""

    try:
        entry = date.fromisoformat(entry_date[:10])
        expiry = date.fromisoformat(expiry_date[:10])
    except (ValueError, TypeError):
        return False, ""

    before = timedelta(days=config.blackout_before_days)
    after = timedelta(days=config.blackout_after_days)

    for ticker, dates in earnings_dates.items():
        for ed_str in dates:
            try:
                ed = date.fromisoformat(ed_str)
            except ValueError:
                continue

            blackout_start = ed - before
            blackout_end = ed + after

            # Does trade period overlap blackout?
            if entry <= blackout_end and expiry >= blackout_start:
                return True, f"{ticker} earnings {ed_str} (blackout {blackout_start} to {blackout_end})"

    return False, ""


def apply_earnings_filter(
    candidates: list[CandidateSpread],
    config: EarningsConfig,
) -> list[CandidateSpread]:
    """
    Filter out candidates that overlap with earnings blackout periods.
    """
    if not config.enabled:
        for c in candidates:
            c.tag("earnings:disabled")
        return candidates

    earnings_dates = load_earnings_calendar(config)

    # Warn when the calendar may be exhausted
    all_dates = [d for dates in earnings_dates.values() for d in dates]
    if all_dates:
        from datetime import date as _date
        latest = max(all_dates)
        try:
            if _date.fromisoformat(latest) < _date.today():
                logger.warning(
                    f"Earnings calendar may be exhausted — latest date is {latest}. "
                    "Earnings filtering is inactive past this date."
                )
        except ValueError:
            pass

    for c in candidates:
        in_blackout, reason = is_in_blackout(
            c.entry_date, c.expiration_date, earnings_dates, config
        )
        if in_blackout:
            c.reject("earnings", reason)
        else:
            c.tag("earnings:clear")

    passed_count = sum(1 for c in candidates if c.passed)
    logger.info(f"Earnings filter: {passed_count}/{len(candidates)} candidates passed")
    return candidates
