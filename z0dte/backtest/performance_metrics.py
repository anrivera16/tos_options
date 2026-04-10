"""
Performance Metrics for Calendar Spread Backtesting

Calculates comprehensive performance metrics including:
- Win rate, profit factor
- Sharpe ratio, Calmar ratio
- Max drawdown
- Average hold time
- P&L per trade
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

from z0dte.backtest.calendar_backtest import TradeResult


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for a backtest."""
    
    trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    
    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_pnl: float = 0.0
    
    profit_factor: float = 0.0
    expected_value: float = 0.0
    
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_days: float = 0.0
    
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    
    avg_hold_days: float = 0.0
    median_hold_days: float = 0.0
    min_hold_days: float = 0.0
    max_hold_days: float = 0.0
    
    best_trade: float = 0.0
    worst_trade: float = 0.0
    
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    
    exit_reasons: dict[str, int] = field(default_factory=dict)
    
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    
    @classmethod
    def from_trades(
        cls,
        trades: list[TradeResult],
        risk_free_rate: float = 0.045,
    ) -> PerformanceMetrics:
        """Calculate metrics from trade results."""
        return calculate_performance_metrics(trades, risk_free_rate)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "trade_count": self.trade_count,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "breakeven_trades": self.breakeven_trades,
            "total_pnl": self.total_pnl,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "win_rate": self.win_rate,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "avg_pnl": self.avg_pnl,
            "profit_factor": self.profit_factor,
            "expected_value": self.expected_value,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "avg_hold_days": self.avg_hold_days,
            "median_hold_days": self.median_hold_days,
            "min_hold_days": self.min_hold_days,
            "max_hold_days": self.max_hold_days,
            "best_trade": self.best_trade,
            "worst_trade": self.worst_trade,
            "consecutive_wins": self.consecutive_wins,
            "consecutive_losses": self.consecutive_losses,
            "exit_reasons": self.exit_reasons,
        }


def calculate_performance_metrics(
    trades: list[TradeResult],
    risk_free_rate: float = 0.045,
) -> PerformanceMetrics:
    """Calculate comprehensive performance metrics from trade results."""
    
    if not trades:
        return PerformanceMetrics()
    
    metrics = PerformanceMetrics()
    
    metrics.trade_count = len(trades)
    
    winning = [t for t in trades if t.pnl > 0]
    losing = [t for t in trades if t.pnl < 0]
    breakeven = [t for t in trades if t.pnl == 0]
    
    metrics.winning_trades = len(winning)
    metrics.losing_trades = len(losing)
    metrics.breakeven_trades = len(breakeven)
    
    metrics.gross_profit = sum(t.pnl for t in winning)
    metrics.gross_loss = abs(sum(t.pnl for t in losing))
    metrics.total_pnl = sum(t.pnl for t in trades)
    
    metrics.win_rate = metrics.winning_trades / metrics.trade_count if metrics.trade_count > 0 else 0.0
    
    metrics.avg_win = metrics.gross_profit / metrics.winning_trades if metrics.winning_trades > 0 else 0.0
    metrics.avg_loss = metrics.gross_loss / metrics.losing_trades if metrics.losing_trades > 0 else 0.0
    metrics.avg_pnl = metrics.total_pnl / metrics.trade_count if metrics.trade_count > 0 else 0.0
    
    metrics.profit_factor = (
        metrics.gross_profit / metrics.gross_loss
        if metrics.gross_loss > 0 else
        float("inf") if metrics.gross_profit > 0 else 0.0
    )
    
    metrics.expected_value = metrics.avg_pnl
    
    drawdown_metrics = calculate_max_drawdown(trades)
    metrics.max_drawdown = drawdown_metrics["max_drawdown"]
    metrics.max_drawdown_pct = drawdown_metrics["max_drawdown_pct"]
    metrics.max_drawdown_duration_days = drawdown_metrics["duration_days"]
    
    sharpe = calculate_sharpe_ratio(trades, risk_free_rate)
    metrics.sharpe_ratio = sharpe
    
    sortino = calculate_sortino_ratio(trades, risk_free_rate)
    metrics.sortino_ratio = sortino
    
    metrics.calmar_ratio = (
        metrics.total_pnl / metrics.max_drawdown
        if metrics.max_drawdown > 0 else 0.0
    )
    
    hold_times = [t.hold_days for t in trades]
    if hold_times:
        metrics.avg_hold_days = np.mean(hold_times)
        metrics.median_hold_days = np.median(hold_times)
        metrics.min_hold_days = np.min(hold_times)
        metrics.max_hold_days = np.max(hold_times)
    
    pnls = [t.pnl for t in trades]
    if pnls:
        metrics.best_trade = max(pnls)
        metrics.worst_trade = min(pnls)
    
    consecutive = calculate_consecutive_trades(trades)
    metrics.consecutive_wins = consecutive["max_consecutive_wins"]
    metrics.consecutive_losses = consecutive["max_consecutive_losses"]
    
    metrics.exit_reasons = {}
    for t in trades:
        reason = t.exit_reason
        metrics.exit_reasons[reason] = metrics.exit_reasons.get(reason, 0) + 1
    
    sorted_trades = sorted(trades, key=lambda t: t.exit_timestamp)
    metrics.equity_curve = []
    cumulative = 0.0
    for t in sorted_trades:
        cumulative += t.pnl
        metrics.equity_curve.append((t.exit_timestamp, cumulative))
    
    return metrics


def calculate_max_drawdown(trades: list[TradeResult]) -> dict[str, float]:
    """Calculate maximum drawdown and duration."""
    if not trades:
        return {"max_drawdown": 0.0, "max_drawdown_pct": 0.0, "duration_days": 0.0}
    
    sorted_trades = sorted(trades, key=lambda t: t.exit_timestamp)
    
    cumulative = []
    running = 0.0
    for t in sorted_trades:
        running += t.pnl
        cumulative.append((t.exit_timestamp, running))
    
    peak = 0.0
    max_dd = 0.0
    max_dd_pct = 0.0
    max_dd_start = None
    max_dd_end = None
    current_dd_start = None
    
    for i, (timestamp, value) in enumerate(cumulative):
        if value >= peak:
            peak = value
            current_dd_start = None
        else:
            dd = peak - value
            dd_pct = dd / peak if peak > 0 else 0
            
            if current_dd_start is None:
                current_dd_start = timestamp
            
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct
                max_dd_start = current_dd_start
                max_dd_end = timestamp
    
    duration_days = 0.0
    if max_dd_start and max_dd_end:
        duration_days = (max_dd_end - max_dd_start).total_seconds() / 86400
    
    return {
        "max_drawdown": max_dd,
        "max_drawdown_pct": max_dd_pct,
        "duration_days": duration_days,
    }


def calculate_sharpe_ratio(
    trades: list[TradeResult],
    risk_free_rate: float = 0.045,
    periods_per_year: int = 252,
) -> float:
    """Calculate Sharpe ratio from trade results."""
    if len(trades) < 2:
        return 0.0
    
    pnls = np.array([t.pnl for t in trades])
    
    mean_return = np.mean(pnls)
    std_return = np.std(pnls, ddof=1)
    
    if std_return == 0:
        return 0.0
    
    sharpe = (mean_return - risk_free_rate / periods_per_year) / std_return * math.sqrt(periods_per_year)
    
    return sharpe


def calculate_sortino_ratio(
    trades: list[TradeResult],
    risk_free_rate: float = 0.045,
    periods_per_year: int = 252,
) -> float:
    """Calculate Sortino ratio (uses downside deviation)."""
    if len(trades) < 2:
        return 0.0
    
    pnls = np.array([t.pnl for t in trades])
    
    mean_return = np.mean(pnls)
    
    downside_returns = pnls[pnls < 0]
    
    if len(downside_returns) == 0:
        return float("inf") if mean_return > 0 else 0.0
    
    downside_std = np.std(downside_returns, ddof=1)
    
    if downside_std == 0:
        return 0.0
    
    sortino = (mean_return - risk_free_rate / periods_per_year) / downside_std * math.sqrt(periods_per_year)
    
    return sortino


def calculate_consecutive_trades(trades: list[TradeResult]) -> dict[str, int]:
    """Calculate maximum consecutive winning/losing trades."""
    if not trades:
        return {"max_consecutive_wins": 0, "max_consecutive_losses": 0}
    
    max_consec_wins = 0
    max_consec_losses = 0
    
    current_wins = 0
    current_losses = 0
    
    for trade in trades:
        if trade.pnl > 0:
            current_wins += 1
            current_losses = 0
            max_consec_wins = max(max_consec_wins, current_wins)
        elif trade.pnl < 0:
            current_losses += 1
            current_wins = 0
            max_consec_losses = max(max_consec_losses, current_losses)
        else:
            current_wins = 0
            current_losses = 0
    
    return {
        "max_consecutive_wins": max_consec_wins,
        "max_consecutive_losses": max_consec_losses,
    }


def calculate_trade_distribution(trades: list[TradeResult]) -> dict[str, Any]:
    """Calculate distribution statistics of trade P&Ls."""
    if not trades:
        return {}
    
    pnls = [t.pnl for t in trades]
    
    return {
        "mean": np.mean(pnls),
        "median": np.median(pnls),
        "std": np.std(pnls, ddof=1),
        "min": np.min(pnls),
        "max": np.max(pnls),
        "q1": np.percentile(pnls, 25),
        "q3": np.percentile(pnls, 75),
        "percentile_5": np.percentile(pnls, 5),
        "percentile_95": np.percentile(pnls, 95),
    }


def calculate_exit_reason_analysis(trades: list[TradeResult]) -> dict[str, dict[str, Any]]:
    """Analyze P&L by exit reason."""
    if not trades:
        return {}
    
    reasons: dict[str, list[float]] = {}
    
    for t in trades:
        reason = t.exit_reason
        if reason not in reasons:
            reasons[reason] = []
        reasons[reason].append(t.pnl)
    
    analysis = {}
    for reason, pnls in reasons.items():
        analysis[reason] = {
            "count": len(pnls),
            "total_pnl": sum(pnls),
            "avg_pnl": sum(pnls) / len(pnls),
            "win_rate": sum(1 for p in pnls if p > 0) / len(pnls),
            "avg_hold": np.mean([t.hold_days for t in trades if t.exit_reason == reason]) if trades else 0,
        }
    
    return analysis


def calculate_hold_time_analysis(trades: list[TradeResult]) -> dict[str, Any]:
    """Analyze P&L by hold time buckets."""
    if not trades:
        return {}
    
    buckets = {
        "0-5_days": [],
        "5-10_days": [],
        "10-20_days": [],
        "20+_days": [],
    }
    
    for t in trades:
        hold = t.hold_days
        if hold <= 5:
            buckets["0-5_days"].append(t.pnl)
        elif hold <= 10:
            buckets["5-10_days"].append(t.pnl)
        elif hold <= 20:
            buckets["10-20_days"].append(t.pnl)
        else:
            buckets["20+_days"].append(t.pnl)
    
    analysis = {}
    for bucket, pnls in buckets.items():
        if pnls:
            analysis[bucket] = {
                "count": len(pnls),
                "total_pnl": sum(pnls),
                "avg_pnl": sum(pnls) / len(pnls),
                "win_rate": sum(1 for p in pnls if p > 0) / len(pnls),
            }
        else:
            analysis[bucket] = {
                "count": 0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "win_rate": 0.0,
            }
    
    return analysis


def calculate_opportunity_score_analysis(trades: list[TradeResult]) -> dict[str, Any]:
    """Analyze P&L by opportunity score buckets."""
    if not trades:
        return {}
    
    buckets = {
        "0.5-0.6": [],
        "0.6-0.7": [],
        "0.7-0.8": [],
        "0.8+": [],
    }
    
    for t in trades:
        score = t.max_profit / t.entry_price if t.entry_price > 0 else 0
        
        if score <= 0.6:
            buckets["0.5-0.6"].append(t.pnl)
        elif score <= 0.7:
            buckets["0.6-0.7"].append(t.pnl)
        elif score <= 0.8:
            buckets["0.7-0.8"].append(t.pnl)
        else:
            buckets["0.8+"].append(t.pnl)
    
    analysis = {}
    for bucket, pnls in buckets.items():
        if pnls:
            analysis[bucket] = {
                "count": len(pnls),
                "total_pnl": sum(pnls),
                "avg_pnl": sum(pnls) / len(pnls),
                "win_rate": sum(1 for p in pnls if p > 0) / len(pnls),
            }
        else:
            analysis[bucket] = {
                "count": 0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "win_rate": 0.0,
            }
    
    return analysis
