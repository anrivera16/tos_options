#!/usr/bin/env python3
"""
Run Calendar Spread Backtest

Usage:
    python -m z0dte.backtest.run_backtest [--data-dir PATH] [--output-dir PATH]
    python -m z0dte.backtest.run_backtest --source db [--from-date YYYY-MM-DD] [--to-date YYYY-MM-DD]

Options:
    --data-dir      Path to backtest data directory (default: z0dte/backtest_files)
    --output-dir    Path to output directory (default: results)
    --source        Data source: csv or db (default: csv)
    --from-date     Start date for DB source (YYYY-MM-DD)
    --to-date       End date for DB source (YYYY-MM-DD)
    --symbols       Comma-separated symbols for DB source (default: SPY)
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from z0dte.backtest import (
    BacktestConfig,
    CalendarSpreadBacktester,
    BacktestDataLoader,
    generate_parameter_grid,
    run_parameter_sweep,
)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run Calendar Spread Backtest with Parameter Sweep"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="z0dte/backtest_files",
        help="Path to backtest data directory",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="Path to output directory",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run with limited parameter combinations",
    )
    parser.add_argument(
        "--single-config",
        action="store_true",
        help="Run single configuration instead of sweep",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel workers",
    )
    parser.add_argument(
        "--source",
        type=str,
        choices=["csv", "db"],
        default="csv",
        help="Data source: csv or db (default: csv)",
    )
    parser.add_argument(
        "--from-date",
        type=str,
        default=None,
        help="Start date for DB source (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to-date",
        type=str,
        default=None,
        help="End date for DB source (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="SPY",
        help="Comma-separated symbols for DB source (default: SPY)",
    )
    
    return parser.parse_args()


def run_single_backtest(snapshots, output_dir: Path) -> None:
    """Run a single backtest with default parameters."""
    print("Running single backtest with default parameters...")
    
    config = BacktestConfig(
        opportunity_threshold=0.60,
        confidence_threshold=0.55,
        profit_target_pct=0.35,
        stop_loss_pct=0.15,
        max_hold_days=25,
        min_front_dte=5,
        min_back_dte=14,
    )
    
    backtester = CalendarSpreadBacktester(snapshots, config)
    results = backtester.run()
    
    print(f"\nBacktest completed with {len(results)} trades")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if results:
        total_pnl = sum(r.pnl for r in results)
        winning = sum(1 for r in results if r.pnl > 0)
        
        print(f"\nResults Summary:")
        print(f"  Total P&L: ${total_pnl:.2f}")
        print(f"  Win Rate: {winning}/{len(results)} ({winning/len(results):.1%})")
        print(f"  Average P&L: ${total_pnl/len(results):.2f}")
        
        trades_path = output_dir / "trades.csv"
        with open(trades_path, "w") as f:
            f.write("trade_id,entry_timestamp,exit_timestamp,entry_price,exit_price,pnl,pnl_pct,hold_days,exit_reason\n")
            for r in results:
                f.write(f"{r.trade_id},{r.entry_timestamp},{r.exit_timestamp},{r.entry_price:.4f},{r.exit_price:.4f},{r.pnl:.4f},{r.pnl_pct:.4f},{r.hold_days:.2f},{r.exit_reason}\n")
        
        print(f"\nTrades saved to {trades_path}")
    else:
        print("\nNo trades generated. Possible reasons:")
        print("  - Data does not contain inverted term structure (required for calendar spreads)")
        print("  - No expiration pairs meet the minimum DTE requirements")
        print("  - Opportunity/confidence thresholds not met")


def run_full_sweep(snapshots, output_dir: Path, n_workers: int | None = None, quick: bool = False) -> None:
    """Run full parameter sweep."""
    print("Running parameter sweep...")
    print(f"  Snapshots: {len(snapshots)}")
    
    if quick:
        print("  Mode: QUICK (limited parameters)")
        from z0dte.backtest.parameter_sweep import ParameterSet
        param_sets = [
            ParameterSet(0.60, 0.55, 0.35, 0.15, 25),
            ParameterSet(0.70, 0.55, 0.35, 0.15, 25),
            ParameterSet(0.60, 0.55, 0.50, 0.10, 20),
            ParameterSet(0.50, 0.50, 0.25, 0.20, 30),
        ]
    else:
        print("  Mode: FULL GRID")
        param_sets = generate_parameter_grid()
    
    print(f"  Parameter combinations: {len(param_sets)}")
    
    results = run_parameter_sweep(
        snapshots=snapshots,
        param_sets=param_sets,
        n_workers=n_workers,
        save_intermediate=True,
        output_dir=output_dir,
    )
    
    print(f"\nParameter sweep completed!")
    print(f"  Results analyzed: {len(results)}")
    
    if results:
        results.sort(key=lambda r: r.total_pnl, reverse=True)
        best = results[0]
        
        print(f"\nBest Configuration:")
        print(f"  Opportunity Threshold: {best.params.opportunity_threshold}")
        print(f"  Confidence Threshold: {best.params.confidence_threshold}")
        print(f"  Profit Target: {best.params.profit_target_pct:.0%}")
        print(f"  Stop Loss: {best.params.stop_loss_pct:.0%}")
        print(f"  Max Hold Days: {best.params.max_hold_days}")
        print(f"  Total P&L: ${best.total_pnl:.2f}")
        print(f"  Win Rate: {best.win_rate:.1%}")
        print(f"  Sharpe Ratio: {best.sharpe_ratio:.2f}")


def main():
    """Main entry point."""
    args = parse_args()
    
    output_dir = Path(args.output_dir)
    
    print("=" * 60)
    print("CALENDAR SPREAD BACKTEST")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        if args.source == "db":
            snapshots = _load_from_db(args)
        else:
            snapshots = _load_from_csv(args)
        
        print(f"  Loaded {len(snapshots)} snapshots")
        
        if not snapshots:
            print("Error: No snapshots found")
            sys.exit(1)
        
        print(f"  Date range: {snapshots[0].timestamp} to {snapshots[-1].timestamp}")
        
        valid_snapshots = [s for s in snapshots if s.get_atm_strike() is not None]
        print(f"  Valid snapshots (with ATM data): {len(valid_snapshots)}")
        
    except Exception as e:
        print(f"Error loading data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print()
    
    if args.single_config:
        run_single_backtest(valid_snapshots, output_dir)
    else:
        run_full_sweep(valid_snapshots, output_dir, args.workers, args.quick)
    
    print("\n" + "=" * 60)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


def _load_from_db(args) -> list:
    """Load snapshots from database."""
    from datetime import datetime as dt
    from z0dte.db.connection import get_connection
    from z0dte.sources.db_loader import DBMultiSymbolLoader
    
    symbols = [s.strip() for s in args.symbols.split(",")]
    from_date = None
    to_date = None
    
    if args.from_date:
        from_date = dt.strptime(args.from_date, "%Y-%m-%d")
    if args.to_date:
        to_date = dt.strptime(args.to_date, "%Y-%m-%d")
    
    print(f"\nLoading data from database...")
    print(f"  Symbols: {symbols}")
    if from_date:
        print(f"  From: {from_date.date()}")
    if to_date:
        print(f"  To: {to_date.date()}")
    
    conn = get_connection()
    loader = DBMultiSymbolLoader(
        db_conn=conn,
        symbols=symbols,
        from_date=from_date,
        to_date=to_date,
        source="massive_api",
    )
    
    return loader.load_all()


def _load_from_csv(args) -> list:
    """Load snapshots from CSV files."""
    data_dir = Path(args.data_dir)
    
    if not data_dir.exists():
        print(f"Error: Data directory not found: {data_dir}")
        sys.exit(1)
    
    print(f"\nLoading data from {data_dir}...")
    
    loader = BacktestDataLoader(data_dir, "SPY")
    return loader.get_snapshots()


if __name__ == "__main__":
    main()
