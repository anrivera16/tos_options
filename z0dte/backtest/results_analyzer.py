"""
Results Analyzer for Calendar Spread Backtesting

Analyzes and visualizes backtest results including:
- Best parameter sets by metric
- Equity curves for top performers
- Sensitivity analysis (which parameters matter most)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from z0dte.backtest.calendar_backtest import TradeResult
from z0dte.backtest.parameter_sweep import ParameterSweepResult, ParameterSet
from z0dte.backtest.performance_metrics import PerformanceMetrics, calculate_performance_metrics


@dataclass
class AnalysisConfig:
    """Configuration for analysis."""
    output_dir: Path = Path("results")
    equity_curves_dir: Path = Path("results/equity_curves")
    trade_logs_dir: Path = Path("results/trade_logs")
    top_n_configs: int = 5


@dataclass
class SensitivityAnalysis:
    """Sensitivity analysis results."""
    parameter: str
    values: list[float]
    metric_by_value: dict[float, list[float]]
    avg_metric_by_value: dict[float, float]
    impact_score: float


@dataclass
class AnalysisReport:
    """Complete analysis report."""
    timestamp: datetime
    total_configs_tested: int
    
    best_by_pnl: list[ParameterSweepResult]
    best_by_sharpe: list[ParameterSweepResult]
    best_by_win_rate: list[ParameterSweepResult]
    best_by_profit_factor: list[ParameterSweepResult]
    
    sensitivity_analysis: list[SensitivityAnalysis]
    
    trade_distribution: dict[str, Any]
    exit_reason_analysis: dict[str, Any]
    hold_time_analysis: dict[str, Any]
    
    summary_stats: dict[str, float]


class ResultsAnalyzer:
    """Analyze backtest results and generate reports."""
    
    def __init__(
        self,
        results: list[ParameterSweepResult],
        trades: list[list[TradeResult]] | None = None,
        config: AnalysisConfig | None = None,
    ):
        self.results = results
        self.trades = trades or []
        self.config = config or AnalysisConfig()
        
        self._setup_directories()
    
    def _setup_directories(self) -> None:
        """Create output directories."""
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.equity_curves_dir.mkdir(parents=True, exist_ok=True)
        self.config.trade_logs_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_report(self) -> AnalysisReport:
        """Generate comprehensive analysis report."""
        report = AnalysisReport(
            timestamp=datetime.now(),
            total_configs_tested=len(self.results),
            best_by_pnl=self._get_best_by_metric("total_pnl"),
            best_by_sharpe=self._get_best_by_metric("sharpe_ratio"),
            best_by_win_rate=self._get_best_by_metric("win_rate"),
            best_by_profit_factor=self._get_best_by_metric("profit_factor"),
            sensitivity_analysis=self._compute_sensitivity_analysis(),
            trade_distribution={},
            exit_reason_analysis={},
            hold_time_analysis={},
            summary_stats={},
        )
        
        self._compute_distributions(report)
        self._compute_summary_stats(report)
        
        return report
    
    def _get_best_by_metric(self, metric: str, top_n: int | None = None) -> list[ParameterSweepResult]:
        """Get best results by a given metric."""
        if top_n is None:
            top_n = self.config.top_n_configs
        
        if metric == "total_pnl":
            return sorted(self.results, key=lambda r: r.total_pnl, reverse=True)[:top_n]
        elif metric == "sharpe_ratio":
            return sorted(self.results, key=lambda r: r.sharpe_ratio, reverse=True)[:top_n]
        elif metric == "win_rate":
            return sorted(self.results, key=lambda r: r.win_rate, reverse=True)[:top_n]
        elif metric == "profit_factor":
            return sorted(self.results, key=lambda r: r.profit_factor, reverse=True)[:top_n]
        else:
            return []
    
    def _compute_sensitivity_analysis(self) -> list[SensitivityAnalysis]:
        """Compute sensitivity analysis for each parameter."""
        parameters = [
            ("opportunity_threshold", [0.50, 0.60, 0.70, 0.80]),
            ("confidence_threshold", [0.50, 0.55, 0.65]),
            ("profit_target_pct", [0.25, 0.35, 0.50]),
            ("stop_loss_pct", [0.10, 0.15, 0.20]),
            ("max_hold_days", [15, 20, 25, 30]),
        ]
        
        sensitivity_results = []
        
        for param_name, param_values in parameters:
            metric_by_value: dict[float, list[float]] = {v: [] for v in param_values}
            avg_metric_by_value: dict[float, float] = {}
            
            for result in self.results:
                params = result.params
                value = getattr(params, param_name)
                value = float(value)
                
                for v in param_values:
                    if abs(value - v) < 0.001:
                        metric_by_value[v].append(result.total_pnl)
                        break
            
            for v in param_values:
                if metric_by_value[v]:
                    avg_metric_by_value[v] = np.mean(metric_by_value[v])
                else:
                    avg_metric_by_value[v] = 0.0
            
            impact_score = self._calculate_impact_score(
                list(avg_metric_by_value.values())
            )
            
            sensitivity_results.append(
                SensitivityAnalysis(
                    parameter=param_name,
                    values=param_values,
                    metric_by_value=metric_by_value,
                    avg_metric_by_value=avg_metric_by_value,
                    impact_score=impact_score,
                )
            )
        
        sensitivity_results.sort(key=lambda s: s.impact_score, reverse=True)
        
        return sensitivity_results
    
    def _calculate_impact_score(self, values: list[float]) -> float:
        """Calculate impact score (normalized spread of values)."""
        if not values or len(values) < 2:
            return 0.0
        
        mean = np.mean(values)
        if mean == 0:
            return 0.0
        
        std = np.std(values)
        return std / abs(mean) if mean != 0 else 0.0
    
    def _compute_distributions(self, report: AnalysisReport) -> None:
        """Compute trade distributions across all results."""
        all_trades = []
        for result in self.results:
            for trade in result.trades:
                all_trades.append(trade)
        
        if not all_trades:
            return
        
        pnls = [t.get("pnl", 0) if isinstance(t, dict) else t.pnl for t in all_trades]
        hold_days = [t.get("hold_days", 0) if isinstance(t, dict) else t.hold_days for t in all_trades]
        
        report.trade_distribution = {
            "count": len(all_trades),
            "mean_pnl": np.mean(pnls),
            "median_pnl": np.median(pnls),
            "std_pnl": np.std(pnls),
            "min_pnl": np.min(pnls),
            "max_pnl": np.max(pnls),
            "avg_hold_days": np.mean(hold_days),
        }
        
        exit_reasons: dict[str, int] = {}
        for trade in all_trades:
            reason = trade.get("exit_reason", "unknown") if isinstance(trade, dict) else trade.exit_reason
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
        report.exit_reason_analysis = exit_reasons
        
        hold_buckets = {"0-5": [], "5-10": [], "10-20": [], "20+": []}
        for hold in hold_days:
            if hold <= 5:
                hold_buckets["0-5"].append(hold)
            elif hold <= 10:
                hold_buckets["5-10"].append(hold)
            elif hold <= 20:
                hold_buckets["10-20"].append(hold)
            else:
                hold_buckets["20+"].append(hold)
        
        report.hold_time_analysis = {
            bucket: len(trades) for bucket, trades in hold_buckets.items()
        }
    
    def _compute_summary_stats(self, report: AnalysisReport) -> None:
        """Compute summary statistics."""
        if not self.results:
            return
        
        pnls = [r.total_pnl for r in self.results]
        sharpes = [r.sharpe_ratio for r in self.results]
        win_rates = [r.win_rate for r in self.results]
        
        report.summary_stats = {
            "avg_pnl": np.mean(pnls),
            "median_pnl": np.median(pnls),
            "std_pnl": np.std(pnls),
            "best_pnl": max(pnls),
            "worst_pnl": min(pnls),
            "avg_sharpe": np.mean(sharpes),
            "avg_win_rate": np.mean(win_rates),
        }
    
    def save_equity_curves(self) -> None:
        """Save equity curves for top performers."""
        best_configs = self._get_best_by_metric("total_pnl")
        
        for i, result in enumerate(best_configs[:5]):
            params = result.params
            filename = f"equity_{params.opportunity_threshold}_{params.confidence_threshold}_{params.profit_target_pct}_{params.stop_loss_pct}_{params.max_hold_days}.json"
            filepath = self.config.equity_curves_dir / filename
            
            equity_curve = []
            trades = sorted(result.trades, key=lambda t: t.get("exit_timestamp", "") if isinstance(t, dict) else t.exit_timestamp)
            
            cumulative = 0.0
            for trade in trades:
                pnl = trade.get("pnl", 0) if isinstance(trade, dict) else trade.pnl
                timestamp = trade.get("exit_timestamp", "") if isinstance(trade, dict) else trade.exit_timestamp
                cumulative += pnl
                equity_curve.append({"timestamp": str(timestamp), "equity": cumulative})
            
            with open(filepath, "w") as f:
                json.dump({
                    "params": result.params.to_dict(),
                    "equity_curve": equity_curve,
                }, f, indent=2, default=str)
    
    def save_trade_logs(self) -> None:
        """Save detailed trade logs."""
        for i, result in enumerate(self.results[:10]):
            params = result.params
            filename = f"trades_{params.opportunity_threshold}_{params.confidence_threshold}_{params.profit_target_pct}_{params.stop_loss_pct}_{params.max_hold_days}.csv"
            filepath = self.config.trade_logs_dir / filename
            
            with open(filepath, "w") as f:
                f.write("trade_id,entry_timestamp,exit_timestamp,entry_price,exit_price,pnl,pnl_pct,hold_days,exit_reason\n")
                
                for trade in result.trades:
                    trade_dict = trade if isinstance(trade, dict) else trade.__dict__
                    f.write(f"{trade_dict.get('trade_id', '')},")
                    f.write(f"{trade_dict.get('entry_timestamp', '')},")
                    f.write(f"{trade_dict.get('exit_timestamp', '')},")
                    f.write(f"{trade_dict.get('entry_price', 0):.4f},")
                    f.write(f"{trade_dict.get('exit_price', 0):.4f},")
                    f.write(f"{trade_dict.get('pnl', 0):.4f},")
                    f.write(f"{trade_dict.get('pnl_pct', 0):.4f},")
                    f.write(f"{trade_dict.get('hold_days', 0):.2f},")
                    f.write(f"{trade_dict.get('exit_reason', '')}\n")
    
    def generate_sensitivity_plot_data(self) -> dict[str, Any]:
        """Generate data for sensitivity analysis plots."""
        sensitivity = self._compute_sensitivity_analysis()
        
        plot_data = {}
        for s in sensitivity:
            plot_data[s.parameter] = {
                "values": s.values,
                "avg_metric": [s.avg_metric_by_value[v] for v in s.values],
                "impact_score": s.impact_score,
            }
        
        return plot_data
    
    def save_report(self, report: AnalysisReport) -> None:
        """Save analysis report to files."""
        report_path = self.config.output_dir / "analysis_report.json"
        
        report_dict = {
            "timestamp": report.timestamp.isoformat(),
            "total_configs_tested": report.total_configs_tested,
            "best_by_pnl": [
                {"params": r.params.to_dict(), "total_pnl": r.total_pnl, "win_rate": r.win_rate}
                for r in report.best_by_pnl
            ],
            "best_by_sharpe": [
                {"params": r.params.to_dict(), "sharpe_ratio": r.sharpe_ratio}
                for r in report.best_by_sharpe
            ],
            "sensitivity_analysis": [
                {
                    "parameter": s.parameter,
                    "values": s.values,
                    "avg_metric_by_value": {str(k): v for k, v in s.avg_metric_by_value.items()},
                    "impact_score": s.impact_score,
                }
                for s in report.sensitivity_analysis
            ],
            "summary_stats": report.summary_stats,
        }
        
        with open(report_path, "w") as f:
            json.dump(report_dict, f, indent=2)
        
        sensitivity_path = self.config.output_dir / "sensitivity_analysis.csv"
        with open(sensitivity_path, "w") as f:
            f.write("parameter,values,impact_score\n")
            for s in report.sensitivity_analysis:
                f.write(f"{s.parameter},")
                f.write(f"{','.join(str(v) for v in s.values)},")
                f.write(f"{s.impact_score:.4f}\n")
        
        print(f"Analysis report saved to {self.config.output_dir}")


def load_sweep_results(results_dir: Path) -> list[ParameterSweepResult]:
    """Load sweep results from JSON file."""
    results_path = results_dir / "full_sweep_results.json"
    
    if not results_path.exists():
        return []
    
    with open(results_path, "r") as f:
        data = json.load(f)
    
    results = []
    for item in data:
        params = item["params"]
        param_set = ParameterSet(
            opportunity_threshold=params["opportunity_threshold"],
            confidence_threshold=params["confidence_threshold"],
            profit_target_pct=params["profit_target_pct"],
            stop_loss_pct=params["stop_loss_pct"],
            max_hold_days=params["max_hold_days"],
        )
        
        result = ParameterSweepResult(
            params=param_set,
            trade_count=item.get("trade_count", 0),
            winning_trades=item.get("winning_trades", 0),
            losing_trades=item.get("losing_trades", 0),
            total_pnl=item.get("total_pnl", 0.0),
            win_rate=item.get("win_rate", 0.0),
            avg_pnl=item.get("avg_pnl", 0.0),
            avg_win=item.get("avg_win", 0.0),
            avg_loss=item.get("avg_loss", 0.0),
            profit_factor=item.get("profit_factor", 0.0),
            max_drawdown=item.get("max_drawdown", 0.0),
            sharpe_ratio=item.get("sharpe_ratio", 0.0),
            calmar_ratio=item.get("calmar_ratio", 0.0),
            avg_hold_days=item.get("avg_hold_days", 0.0),
            exit_reasons=item.get("exit_reasons", {}),
        )
        results.append(result)
    
    return results


def run_analysis(results_dir: Path | str = "results") -> AnalysisReport:
    """Run complete analysis on sweep results."""
    results_dir = Path(results_dir)
    
    results = load_sweep_results(results_dir)
    
    if not results:
        print("No results found to analyze")
        return AnalysisReport(
            timestamp=datetime.now(),
            total_configs_tested=0,
            best_by_pnl=[],
            best_by_sharpe=[],
            best_by_win_rate=[],
            best_by_profit_factor=[],
            sensitivity_analysis=[],
            trade_distribution={},
            exit_reason_analysis={},
            hold_time_analysis={},
            summary_stats={},
        )
    
    analyzer = ResultsAnalyzer(results)
    report = analyzer.generate_report()
    analyzer.save_equity_curves()
    analyzer.save_trade_logs()
    analyzer.save_report(report)
    
    return report


def print_top_configs(results: list[ParameterSweepResult], metric: str = "total_pnl", top_n: int = 10) -> None:
    """Print top N configurations by a given metric."""
    if metric == "total_pnl":
        sorted_results = sorted(results, key=lambda r: r.total_pnl, reverse=True)
    elif metric == "sharpe_ratio":
        sorted_results = sorted(results, key=lambda r: r.sharpe_ratio, reverse=True)
    elif metric == "win_rate":
        sorted_results = sorted(results, key=lambda r: r.win_rate, reverse=True)
    elif metric == "profit_factor":
        sorted_results = sorted(results, key=lambda r: r.profit_factor, reverse=True)
    else:
        sorted_results = results
    
    print(f"\nTop {top_n} configurations by {metric}:")
    print("-" * 100)
    print(f"{'Rank':<5} {'OppThresh':<10} {'ConfThresh':<10} {'ProfitTgt':<10} {'StopLoss':<10} {'MaxHold':<8} {'Trades':<7} {'P&L':<10} {'WinRate':<8} {'Sharpe':<8}")
    print("-" * 100)
    
    for i, result in enumerate(sorted_results[:top_n], 1):
        params = result.params
        print(f"{i:<5} {params.opportunity_threshold:<10.2f} {params.confidence_threshold:<10.2f} "
              f"{params.profit_target_pct:<10.2f} {params.stop_loss_pct:<10.2f} {params.max_hold_days:<8} "
              f"{result.trade_count:<7} {result.total_pnl:<10.2f} {result.win_rate:<8.1%} {result.sharpe_ratio:<8.2f}")
    
    print("-" * 100)


def print_sensitivity_analysis(sensitivity: list[SensitivityAnalysis]) -> None:
    """Print sensitivity analysis results."""
    print("\nSensitivity Analysis:")
    print("-" * 60)
    print(f"{'Parameter':<25} {'Impact Score':<15} {'Best Value':<15}")
    print("-" * 60)
    
    for s in sensitivity:
        best_value = max(s.avg_metric_by_value.items(), key=lambda x: x[1])[0]
        print(f"{s.parameter:<25} {s.impact_score:<15.4f} {best_value:<15}")
    
    print("-" * 60)
