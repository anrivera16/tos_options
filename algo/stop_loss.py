"""
Module 9: Stop-Loss Manager

Monitors open positions and triggers exits when:
- Unrealized loss exceeds X% of max loss (stop-loss)
- Unrealized profit reaches Y% of credit (profit target)

Works with the RiskManager's open_positions list.
In backtest mode, checks against daily option prices.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from algo.types import CandidateSpread
from algo.config import StopLossConfig

logger = logging.getLogger(__name__)


@dataclass
class ExitSignal:
    """Result of checking a position for stop/target."""
    should_exit: bool = False
    reason: str = ""          # "stop_loss", "profit_target", "max_hold"
    unrealized_pnl: float = 0.0
    current_spread_cost: float = 0.0
    days_held: int = 0


def check_exit(
    candidate: CandidateSpread,
    current_short_price: float,
    current_long_price: float,
    days_held: int,
    config: StopLossConfig,
) -> ExitSignal:
    """
    Check if a position should be exited based on current prices.

    Args:
        candidate: The open position
        current_short_price: Current mid price of the short leg
        current_long_price: Current mid price of the long leg
        days_held: Calendar days since entry
        config: Stop-loss configuration

    Returns:
        ExitSignal with exit decision and details
    """
    if not config.enabled:
        return ExitSignal()

    # Current cost to close the spread
    current_spread = current_short_price - current_long_price
    unrealized_pnl = candidate.credit - current_spread

    # Min hold days check
    if days_held < config.min_hold_days:
        return ExitSignal(
            unrealized_pnl=unrealized_pnl,
            current_spread_cost=current_spread,
            days_held=days_held,
        )

    # Stop-loss: unrealized loss exceeds X% of max loss
    if config.stop_loss_pct > 0 and unrealized_pnl < 0:
        stop_line = -(candidate.max_loss * config.stop_loss_pct / 100.0)
        if unrealized_pnl <= stop_line:
            return ExitSignal(
                should_exit=True,
                reason="stop_loss",
                unrealized_pnl=unrealized_pnl,
                current_spread_cost=current_spread,
                days_held=days_held,
            )

    # Profit target: unrealized profit reaches X% of credit
    if config.profit_target_pct > 0:
        target_line = candidate.credit * config.profit_target_pct / 100.0
        if unrealized_pnl >= target_line:
            return ExitSignal(
                should_exit=True,
                reason="profit_target",
                unrealized_pnl=unrealized_pnl,
                current_spread_cost=current_spread,
                days_held=days_held,
            )

    # Max hold days
    if config.max_hold_days > 0 and days_held >= config.max_hold_days:
        return ExitSignal(
            should_exit=True,
            reason="max_hold",
            unrealized_pnl=unrealized_pnl,
            current_spread_cost=current_spread,
            days_held=days_held,
        )

    return ExitSignal(
        unrealized_pnl=unrealized_pnl,
        current_spread_cost=current_spread,
        days_held=days_held,
    )


def apply_stop_loss(
    candidates: list[CandidateSpread],
    config: StopLossConfig,
) -> list[CandidateSpread]:
    """
    Tag candidates with stop-loss metadata.

    In the pipeline flow, this runs after scoring and before risk management.
    It doesn't reject candidates — it tags them with the stop/target levels
    so the risk manager knows the planned exit rules.

    This is primarily for display/reporting. The actual exit logic runs
    in the backtest loop (checking prices each day).
    """
    if not config.enabled:
        for c in candidates:
            c.tag("stop_loss:disabled")
        return candidates

    for c in candidates:
        stop_price = -(c.max_loss * config.stop_loss_pct / 100.0)
        target_price = c.credit * config.profit_target_pct / 100.0
        c.tag(f"stop_loss:sl@${stop_price:.2f}_tgt@${target_price:.2f}")

    return candidates
