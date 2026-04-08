"""
Live 0DTE Premium Flow Runner

Fetches live option chain data from Schwab API and computes premium flow signals.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from z0dte.db.connection import get_connection
from signals.net_premium_flow import NetPremiumFlow
from z0dte.sources.live import LiveDataSource
from z0dte.ingestion.pipeline import IngestionPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run live 0DTE premium flow monitoring from Schwab API"
    )
    parser.add_argument(
        "--symbol",
        default="SPY",
        help="Underlying symbol (default: SPY)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Minutes between API calls (default: 15)"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Number of iterations to run (default: run forever)"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live mode (Schwab API, default for this script)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse data but skip database writes"
    )
    return parser.parse_args()


class LiveRunner:
    def __init__(
        self,
        symbol: str,
        interval_minutes: int,
        dry_run: bool = False,
    ):
        self.symbol = symbol.upper()
        self.interval_seconds = interval_minutes * 60
        self.dry_run = dry_run
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.source = LiveDataSource()
        
        if not dry_run:
            self.conn = get_connection()
            self.pipeline = IngestionPipeline(
                self.source,
                self.conn,
                [NetPremiumFlow()]
            )
        
        self.iteration = 0
        self.errors = 0
    
    def _signal_handler(self, signum, frame):
        print("\n\nShutting down gracefully...")
        self.running = False
    
    def run_once(self) -> dict | None:
        self.iteration += 1
        timestamp = datetime.now(ZoneInfo("US/Eastern"))
        
        try:
            if self.dry_run:
                snapshot = self.source.fetch_snapshot(self.symbol)
                from backtest.pm1_backtest import compute_premium_flow, PM1Snapshot, PM1Contract
                from datetime import date
                
                def parse_exp_date(exp_str: str | None) -> date:
                    """Parse expiration date from various formats."""
                    if not exp_str:
                        return date.today()
                    # Try parsing ISO format with timezone: 2026-04-10T20:00:00.000+00:00
                    try:
                        dt = datetime.fromisoformat(exp_str.replace('Z', '+00:00'))
                        return dt.date()
                    except ValueError:
                        pass
                    # Try simple date format: 2026-04-10
                    try:
                        return date.fromisoformat(exp_str)
                    except ValueError:
                        return date.today()
                
                # Convert to compatible format
                contracts = []
                for c in snapshot.contracts:
                    contracts.append(PM1Contract(
                        strike=c.strike or 0,
                        put_call=c.put_call or "CALL",
                        expiration_date=parse_exp_date(c.expiration_date),
                        dte=c.dte or 0,
                        bid=c.bid,
                        ask=c.ask,
                        last=c.last,
                        volume=c.total_volume or 0,
                        open_interest=c.open_interest or 0,
                        underlying_price=c.underlying_price or 0,
                    ))
                
                mock_snapshot = PM1Snapshot(
                    symbol=snapshot.symbol,
                    captured_at=snapshot.captured_at,
                    underlying_price=snapshot.underlying_price,
                    contracts=contracts,
                )
                flow = compute_premium_flow(mock_snapshot)
            else:
                snapshot_id = self.pipeline.run_one(self.symbol)
                
                result = self.conn.execute("""
                    SELECT * FROM signal_premium_flow 
                    WHERE snapshot_id = %s
                """, (snapshot_id,)).fetchone()
                flow = dict(result) if result else None
            
            return flow
            
        except Exception as e:
            self.errors += 1
            print(f"  ERROR: {e}")
            return None
    
    def print_header(self):
        print("=" * 70)
        print(f"  0DTE LIVE PREMIUM FLOW MONITOR")
        print(f"  Symbol: {self.symbol}  |  Interval: {self.interval_seconds // 60} min")
        print("=" * 70)
        print()
    
    def print_result(self, flow: dict, timestamp: datetime):
        direction = "🟢 BULLISH" if flow["net_premium_flow"] > 0 else "🔴 BEARISH"
        price = flow.get("price_at_bar") or flow.get("underlying_price") or 0
        
        print(f"[{timestamp.strftime('%H:%M:%S')}] #{self.iteration}")
        print(f"  SPY: ${price:.2f}")
        print(f"  Direction: {direction}")
        print(f"  Net Flow:  ${flow['net_premium_flow']:+,.0f}")
        print(f"  Call Flow: ${(flow['call_premium_at_ask'] - flow['call_premium_at_bid']):+,.0f}")
        print(f"  Put Flow:  ${(flow['put_premium_at_ask'] - flow['put_premium_at_bid']):+,.0f}")
        print()
    
    def run_loop(self, max_iterations: int | None = None):
        self.print_header()
        
        print(f"Starting at {datetime.now(ZoneInfo('US/Eastern')).strftime('%Y-%m-%d %H:%M:%S ET')}")
        print(f"Press Ctrl+C to stop\n")
        
        while self.running:
            timestamp = datetime.now(ZoneInfo("US/Eastern"))
            
            print(f"Fetching {self.symbol} data...")
            flow = self.run_once()
            
            if flow:
                self.print_result(flow, timestamp)
            else:
                print(f"[{timestamp.strftime('%H:%M:%S')}] Iteration #{self.iteration} - No data (errors: {self.errors})")
                print()
            
            if max_iterations and self.iteration >= max_iterations:
                print(f"Reached max iterations ({max_iterations}). Stopping.")
                break
            
            if self.running:
                print(f"Sleeping for {self.interval_seconds // 60} minutes...")
                print("-" * 70)
                
                # Use shorter sleep intervals to check for signals more frequently
                remaining = self.interval_seconds
                while remaining > 0 and self.running:
                    sleep_time = min(remaining, 10)  # Check every 10 seconds
                    time.sleep(sleep_time)
                    remaining -= sleep_time
        
        print(f"\nTotal iterations: {self.iteration}")
        print(f"Total errors: {self.errors}")
        print("Done!")


def main():
    args = parse_args()
    
    runner = LiveRunner(
        symbol=args.symbol,
        interval_minutes=args.interval,
        dry_run=args.dry_run,
    )
    
    runner.run_loop(max_iterations=args.count)


if __name__ == "__main__":
    main()