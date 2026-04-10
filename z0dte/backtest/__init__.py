"""
Calendar Spread Backtest Package

A comprehensive backtesting system for calendar spread options strategies.
"""

from z0dte.backtest.calendar_backtest import (
    BacktestConfig,
    BacktestState,
    CalendarSpreadBacktester,
    OptionSnapshot,
    TradePosition,
    TradeResult,
    run_single_backtest,
)

from z0dte.backtest.parameter_sweep import (
    ParameterSet,
    ParameterSweepResult,
    generate_parameter_grid,
    get_best_configs,
    run_parameter_sweep,
)

from z0dte.backtest.performance_metrics import (
    PerformanceMetrics,
    calculate_performance_metrics,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
)

from z0dte.backtest.results_analyzer import (
    AnalysisConfig,
    AnalysisReport,
    ResultsAnalyzer,
    run_analysis,
    load_sweep_results,
    print_top_configs,
    print_sensitivity_analysis,
)

from z0dte.backtest.csv_loader import (
    BacktestDataLoader,
    OptionSnapshot as CSVOptionSnapshot,
    SchwabCSVLoader,
)

__all__ = [
    "BacktestConfig",
    "BacktestState",
    "CalendarSpreadBacktester",
    "TradePosition",
    "TradeResult",
    "run_single_backtest",
    "ParameterSet",
    "ParameterSweepResult",
    "generate_parameter_grid",
    "get_best_configs",
    "run_parameter_sweep",
    "PerformanceMetrics",
    "calculate_performance_metrics",
    "calculate_max_drawdown",
    "calculate_sharpe_ratio",
    "calculate_sortino_ratio",
    "AnalysisConfig",
    "AnalysisReport",
    "ResultsAnalyzer",
    "run_analysis",
    "load_sweep_results",
    "print_top_configs",
    "print_sensitivity_analysis",
    "BacktestDataLoader",
    "SchwabCSVLoader",
]
