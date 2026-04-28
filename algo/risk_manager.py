"""
Module 8: Risk Manager

Position sizing, circuit breakers, and portfolio-level controls.
Tracks P&L across all open positions and enforces daily/weekly limits.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from dataclasses import dataclass

from algo.types import CandidateSpread
from algo.config import RiskConfig

logger = logging.getLogger(__name__)


@dataclass
class PortfolioState:
    """Track open positions and P&L."""
    bankroll: float = 50000.0
    open_positions: list[CandidateSpread] = None  # type: ignore
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    current_date: str = ""
    week_start_date: str = ""

    def __post_init__(self):
        if self.open_positions is None:
            self.open_positions = []

    @property
    def position_count(self) -> int:
        return len(self.open_positions)

    @property
    def available_capital(self) -> float:
        committed = sum(p.max_loss * 100 * (p.contracts or 1) for p in self.open_positions)
        return self.bankroll - committed


class RiskManager:
    """
    Manages position sizing and circuit breakers for the pipeline.
    """

    def __init__(self, config: RiskConfig):
        self.config = config
        self.state = PortfolioState(bankroll=config.bankroll)
        self._trade_history: list[CandidateSpread] = []

    def can_take_trade(self, candidate: CandidateSpread) -> tuple[bool, str]:
        """
        Check if we can take this trade based on risk rules.

        Returns (allowed, reason).
        """
        # Max positions
        if self.state.position_count >= self.config.max_positions:
            return False, f"max positions reached ({self.state.position_count}/{self.config.max_positions})"

        # Daily loss limit
        if self.state.daily_pnl <= -self.config.daily_loss_limit:
            return False, f"daily loss limit hit (${self.state.daily_pnl:.0f} vs -${self.config.daily_loss_limit:.0f})"

        # Weekly loss limit
        if self.state.weekly_pnl <= -self.config.weekly_loss_limit:
            return False, f"weekly loss limit hit (${self.state.weekly_pnl:.0f} vs -${self.config.weekly_loss_limit:.0f})"

        # Position sizing: can we afford it?
        max_loss_per_contract = candidate.max_loss * 100  # per-contract
        risk_amount = self.config.bankroll * self.config.risk_per_trade_pct

        if max_loss_per_contract > risk_amount:
            # Would exceed risk per trade — but we can size down to 1 contract
            # as long as max_loss * 100 < bankroll
            if max_loss_per_contract > self.config.bankroll:
                return False, f"max loss ${max_loss_per_contract:.0f} exceeds bankroll"

        return True, "approved"

    def position_size(self, candidate: CandidateSpread) -> int:
        """
        Calculate number of contracts for this trade.

        Based on risk_per_trade_pct of bankroll.
        """
        max_loss_per_contract = candidate.max_loss * 100
        if max_loss_per_contract <= 0:
            return 0

        risk_amount = self.config.bankroll * self.config.risk_per_trade_pct
        contracts = int(risk_amount / max_loss_per_contract)
        return max(contracts, 1)  # at least 1

    def open_position(self, candidate: CandidateSpread) -> None:
        """Record a new position."""
        contracts = self.position_size(candidate)
        candidate.contracts = contracts
        candidate.tags.append(f"risk:contracts={contracts}")
        self.state.open_positions.append(candidate)
        self._trade_history.append(candidate)
        logger.info(
            f"Opened {candidate.spread_type} {candidate.short_strike}/{candidate.long_strike} "
            f"exp {candidate.expiration_date} — "
            f"contracts={contracts}, "
            f"open positions={self.state.position_count}"
        )

    def close_position(self, candidate: CandidateSpread, exit_spread_cost: float, exit_date: str) -> None:
        """
        Record closing a position.

        exit_spread_cost: cost to buy back the spread (short_mark - long_mark at exit).
        pnl = credit received - cost to close.
        """
        if candidate in self.state.open_positions:
            self.state.open_positions.remove(candidate)

        candidate.exit_date = exit_date
        candidate.exit_price = exit_spread_cost
        candidate.pnl = candidate.credit - exit_spread_cost

        contracts = candidate.contracts or 1
        candidate.pnl_dollars = candidate.pnl * 100 * contracts
        self.state.daily_pnl += candidate.pnl_dollars
        self.state.weekly_pnl += candidate.pnl_dollars

        if candidate.pnl > 0:
            candidate.trade_result = "win"
        elif candidate.pnl < 0:
            candidate.trade_result = "loss"
        else:
            candidate.trade_result = "scratch"

    def reset_daily(self) -> None:
        """Reset daily P&L counter."""
        self.state.daily_pnl = 0.0

    def reset_weekly(self) -> None:
        """Reset weekly P&L counter."""
        self.state.weekly_pnl = 0.0

    @property
    def trade_history(self) -> list[CandidateSpread]:
        return list(self._trade_history)


def apply_risk_filter(
    candidates: list[CandidateSpread],
    risk_mgr: RiskManager,
) -> list[CandidateSpread]:
    """
    Apply risk management to the ranked candidates.

    Takes the top candidate(s) that pass risk checks.
    Returns approved trades only.
    """
    if not risk_mgr.config.enabled:
        for c in candidates:
            c.tag("risk:disabled")
        return candidates

    approved: list[CandidateSpread] = []
    for c in candidates:
        allowed, reason = risk_mgr.can_take_trade(c)
        if allowed:
            c.tag(f"risk:approved ({reason})")
            approved.append(c)
            break  # only take top candidate per cycle
        else:
            c.reject("risk", reason)

    if approved:
        contracts = risk_mgr.position_size(approved[0])
        approved[0].tag(f"risk:{contracts}_contracts")
        logger.info(f"Risk approved: {approved[0].spread_type} {approved[0].short_strike} — {contracts} contracts")

    return approved
