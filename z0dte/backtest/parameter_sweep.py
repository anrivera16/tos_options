"""
Parameter Sweep for Calendar Spread Backtesting

Performs grid search over parameter combinations using multiprocessing.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np

from z0dte.backtest.calendar_backtest import BacktestConfig, CalendarSpreadBacktester, TradeResult
from z0dte.backtest.csv_loader import OptionSnapshot


@dataclass
class ParameterSet:
    """A single parameter combination to test."""
    opportunity_threshold: float
    confidence_threshold: float
    profit_target_pct: float
    stop_loss_pct: float
    max_hold_days: int
    
    def to_config(self) -> BacktestConfig:
        return BacktestConfig(
            opportunity_threshold=self.opportunity_threshold,
            confidence_threshold=self.confidence_threshold,
            profit_target_pct=self.profit_target_pct,
            stop_loss_pct=self.stop_loss_pct,
            max_hold_days=self.max_hold_days,
        )
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_threshold": self.opportunity_threshold,
            "confidence_threshold": self.confidence_threshold,
            "profit_target_pct": self.profit_target_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "max_hold_days": self.max_hold_days,
        }


@dataclass
class ParameterSweepResult:
    """Result of testing a single parameter set."""
    params: ParameterSet
    trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    avg_hold_days: float = 0.0
    exit_reasons: dict[str, int] = field(default_factory=dict)
    trades: list[dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "params": self.params.to_dict(),
            "trade_count": self.trade_count,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": self.total_pnl,
            "win_rate": self.win_rate,
            "avg_pnl": self.avg_pnl,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "profit_factor": self.profit_factor,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "calmar_ratio": self.calmar_ratio,
            "avg_hold_days": self.avg_hold_days,
            "exit_reasons": self.exit_reasons,
        }


def generate_parameter_grid(
    opportunity_thresholds: list[float] | None = None,
    confidence_thresholds: list[float] | None = None,
    profit_targets: list[float] | None = None,
    stop_losses: list[float] | None = None,
    max_hold_days_list: list[int] | None = None,
) -> list[ParameterSet]:
    """Generate all parameter combinations for the sweep."""
    
    if opportunity_thresholds is None:
        opportunity_thresholds = [0.50, 0.60, 0.70, 0.80]
    if confidence_thresholds is None:
        confidence_thresholds = [0.50, 0.55, 0.65]
    if profit_targets is None:
        profit_targets = [0.25, 0.35, 0.50]
    if stop_losses is None:
        stop_losses = [0.10, 0.15, 0.20]
    if max_hold_days_list is None:
        max_hold_days_list = [15, 20, 25, 30]
    
    param_sets = []
    for opp, conf, profit, stop, hold in product(
        opportunity_thresholds,
        confidence_thresholds,
        profit_targets,
        stop_losses,
        max_hold_days_list,
    ):
        param_sets.append(
            ParameterSet(
                opportunity_threshold=opp,
                confidence_threshold=conf,
                profit_target_pct=profit,
                stop_loss_pct=stop,
                max_hold_days=hold,
            )
        )
    
    return param_sets


def compute_result_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute performance metrics from trade results."""
    if not trades:
        return {
            "trade_count": 0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
        }
    
    total_pnl = sum(t.get("pnl", 0) for t in trades)
    winning = [t for t in trades if t.get("pnl", 0) > 0]
    losing = [t for t in trades if t.get("pnl", 0) < 0]
    
    avg_win = sum(t.get("pnl", 0) for t in winning) / len(winning) if winning else 0.0
    avg_loss = sum(t.get("pnl", 0) for t in losing) / len(losing) if losing else 0.0
    
    total_wins = sum(t.get("pnl", 0) for t in winning)
    total_losses = abs(sum(t.get("pnl", 0) for t in losing))
    profit_factor = total_wins / total_losses if total_losses > 0 else float("inf") if total_wins > 0 else 0.0
    
    sorted_trades = sorted(trades, key=lambda t: t.get("exit_timestamp", "") or "")
    cumulative = []
    running = 0.0
    for t in sorted_trades:
        running += t.get("pnl", 0)
        cumulative.append(running)
    
    max_drawdown = 0.0
    peak = 0.0
    for value in cumulative:
        if value > peak:
            peak = value
        drawdown = peak - value
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    pnls = [t.get("pnl", 0) for t in trades]
    if len(pnls) > 1:
        returns_array = np.array(pnls)
        sharpe = np.mean(returns_array) / np.std(returns_array) * np.sqrt(252) if np.std(returns_array) > 0 else 0.0
    else:
        sharpe = 0.0
    
    max_dd = max_drawdown if max_drawdown > 0 else 1.0
    annual_return = total_pnl
    calmar = annual_return / max_dd if max_dd > 0 else 0.0
    
    avg_hold = sum(t.get("hold_days", 0) for t in trades) / len(trades)
    
    exit_reasons: dict[str, int] = {}
    for t in trades:
        reason = t.get("exit_reason", "unknown")
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
    
    return {
        "trade_count": len(trades),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "total_pnl": total_pnl,
        "win_rate": len(winning) / len(trades),
        "avg_pnl": total_pnl / len(trades),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe,
        "calmar_ratio": calmar,
        "avg_hold_days": avg_hold,
        "exit_reasons": exit_reasons,
    }


def run_single_parameter_set(
    args: tuple[list[dict[str, Any]], ParameterSet],
) -> ParameterSweepResult:
    """Run backtest for a single parameter set."""
    trade_dicts, params = args
    
    metrics = compute_result_metrics(trade_dicts)
    
    result = ParameterSweepResult(
        params=params,
        trades=trade_dicts,
    )
    
    result.trade_count = metrics["trade_count"]
    result.winning_trades = metrics["winning_trades"]
    result.losing_trades = metrics["losing_trades"]
    result.total_pnl = metrics["total_pnl"]
    result.win_rate = metrics["win_rate"]
    result.avg_pnl = metrics["avg_pnl"]
    result.avg_win = metrics["avg_win"]
    result.avg_loss = metrics["avg_loss"]
    result.profit_factor = metrics["profit_factor"]
    result.max_drawdown = metrics["max_drawdown"]
    result.sharpe_ratio = metrics["sharpe_ratio"]
    result.calmar_ratio = metrics["calmar_ratio"]
    result.avg_hold_days = metrics["avg_hold_days"]
    result.exit_reasons = metrics["exit_reasons"]
    
    return result


def run_parameter_sweep(
    snapshots: list[OptionSnapshot],
    param_sets: list[ParameterSet] | None = None,
    n_workers: int | None = None,
    save_intermediate: bool = True,
    output_dir: str | Path = "results",
) -> list[ParameterSweepResult]:
    """
    Run parameter sweep over all combinations.
    """
    if param_sets is None:
        param_sets = generate_parameter_grid()
    
    if n_workers is None:
        n_workers = min(os.cpu_count() or 1, len(param_sets))
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Running parameter sweep with {len(param_sets)} configurations...")
    print(f"Using {n_workers} workers")
    
    trade_dicts_list = []
    
    for params in param_sets:
        config = params.to_config()
        backtester = CalendarSpreadBacktester(snapshots, config)
        trade_results = backtester.run()
        
        trade_dicts = []
        for r in trade_results:
            trade_dicts.append({
                "trade_id": r.trade_id,
                "entry_timestamp": r.entry_timestamp,
                "exit_timestamp": r.exit_timestamp,
                "entry_price": r.entry_price,
                "exit_price": r.exit_price,
                "strike": r.strike,
                "front_expiry": r.front_expiry,
                "back_expiry": r.back_expiry,
                "option_type": r.option_type,
                "quantity": r.quantity,
                "pnl": r.pnl,
                "pnl_pct": r.pnl_pct,
                "hold_days": r.hold_days,
                "exit_reason": r.exit_reason,
                "max_profit": r.max_profit,
                "front_iv_entry": r.front_iv_entry,
                "back_iv_entry": r.back_iv_entry,
            })
        
        trade_dicts_list.append(trade_dicts)
    
    args_list = list(zip(trade_dicts_list, param_sets))
    
    sweep_results: list[ParameterSweepResult] = []
    
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {
            executor.submit(run_single_parameter_set, args): args[1]
            for args in args_list
        }
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            result = future.result()
            sweep_results.append(result)
            
            if save_intermediate and completed % 10 == 0:
                _save_intermediate_results(sweep_results, output_dir)
            
            print(f"Completed {completed}/{len(param_sets)}: {result.params.to_dict()} -> PnL: ${result.total_pnl:.2f}, Win Rate: {result.win_rate:.1%}")
    
    sweep_results.sort(key=lambda r: r.total_pnl, reverse=True)
    
    _save_final_results(sweep_results, output_dir)
    
    return sweep_results


def _save_intermediate_results(
    results: list[ParameterSweepResult],
    output_dir: Path,
) -> None:
    """Save intermediate results."""
    summary_path = output_dir / "sweep_intermediate.json"
    
    data = [r.to_dict() for r in results]
    with open(summary_path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _save_final_results(
    results: list[ParameterSweepResult],
    output_dir: Path,
) -> None:
    """Save final sweep results."""
    summary_path = output_dir / "calendar_backtest_summary.csv"
    
    with open(summary_path, "w") as f:
        f.write("rank,opportunity_threshold,confidence_threshold,profit_target,stop_loss,max_hold_days,")
        f.write("trade_count,winning_trades,losing_trades,total_pnl,win_rate,avg_pnl,")
        f.write("avg_win,avg_loss,profit_factor,max_drawdown,sharpe_ratio,calmar_ratio,avg_hold_days\n")
        
        for rank, result in enumerate(results, 1):
            params = result.params
            f.write(f"{rank},")
            f.write(f"{params.opportunity_threshold},")
            f.write(f"{params.confidence_threshold},")
            f.write(f"{params.profit_target_pct},")
            f.write(f"{params.stop_loss_pct},")
            f.write(f"{params.max_hold_days},")
            f.write(f"{result.trade_count},")
            f.write(f"{result.winning_trades},")
            f.write(f"{result.losing_trades},")
            f.write(f"{result.total_pnl:.4f},")
            f.write(f"{result.win_rate:.4f},")
            f.write(f"{result.avg_pnl:.4f},")
            f.write(f"{result.avg_win:.4f},")
            f.write(f"{result.avg_loss:.4f},")
            f.write(f"{result.profit_factor:.4f},")
            f.write(f"{result.max_drawdown:.4f},")
            f.write(f"{result.sharpe_ratio:.4f},")
            f.write(f"{result.calmar_ratio:.4f},")
            f.write(f"{result.avg_hold_days:.4f}\n")
    
    best_configs_path = output_dir / "best_configs.json"
    best_configs = []
    for i, result in enumerate(results[:5]):
        data = result.to_dict()
        data["rank"] = i + 1
        best_configs.append(data)
    
    with open(best_configs_path, "w") as f:
        json.dump(best_configs, f, indent=2, default=str)
    
    full_results_path = output_dir / "full_sweep_results.json"
    with open(full_results_path, "w") as f:
        json.dump([r.to_dict() for r in results], f, indent=2, default=str)
    
    print(f"\nResults saved to {output_dir}")
    print(f"  - {summary_path}")
    print(f"  - {best_configs_path}")
    print(f"  - {full_results_path}")


def get_best_configs(
    results: list[ParameterSweepResult],
    metric: str = "total_pnl",
    top_n: int = 5,
) -> list[ParameterSweepResult]:
    """Get top N parameter configurations by a given metric."""
    if metric == "win_rate":
        return sorted(results, key=lambda r: r.win_rate, reverse=True)[:top_n]
    elif metric == "sharpe_ratio":
        return sorted(results, key=lambda r: r.sharpe_ratio, reverse=True)[:top_n]
    elif metric == "profit_factor":
        return sorted(results, key=lambda r: r.profit_factor, reverse=True)[:top_n]
    elif metric == "calmar_ratio":
        return sorted(results, key=lambda r: r.calmar_ratio, reverse=True)[:top_n]
    else:
        return sorted(results, key=lambda r: r.total_pnl, reverse=True)[:top_n]