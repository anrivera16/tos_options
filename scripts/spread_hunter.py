"""
Spread Hunter — multi-ticker spread opportunity scanner.

Scans option chain data already in the DB and constructs ranked spread
candidates: bull put credit, bear call credit, iron condor, iron fly,
and calendar spreads.

Usage:
    # One-shot scan
    python scripts/spread_hunter.py --once

    # Continuous every 15 min + Discord alerts
    python scripts/spread_hunter.py --interval 15 --discord

    # Specific tickers only
    python scripts/spread_hunter.py --once --tickers SPY QQQ

    # Only credit spreads
    python scripts/spread_hunter.py --once --type credit

    # Custom filters
    python scripts/spread_hunter.py --once --min-roi 25 --min-dte 7 --max-dte 30
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from gex.storage import get_connection
from spread_hunter.spread_builder import SpreadHunterConfig, build_filtered_spreads
from spread_hunter.spread_scoring import score_all
from spread_hunter.spread_display import format_all_results, format_discord_message
from spread_hunter.spread_types import SignalFilter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ET = ZoneInfo("US/Eastern")

# Type filters mapping
TYPE_GROUPS = {
    "credit": ["bull_put_credit", "bear_call_credit"],
    "iron_condor": ["iron_condor"],
    "iron_fly": ["iron_fly"],
    "calendar": ["calendar"],
    "all": ["bull_put_credit", "bear_call_credit", "iron_condor", "iron_fly", "calendar"],
}


def get_db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    return os.environ.get("SQLITE_PATH", "out/options_history.sqlite3")


def is_postgres(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgres://")


def is_market_hours() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    if now.hour < 9 or now.hour >= 16:
        return False
    if now.hour == 9 and now.minute < 30:
        return False
    return True


def build_config(args: argparse.Namespace) -> SpreadHunterConfig:
    """Build config from CLI args."""
    return SpreadHunterConfig(
        min_oi=args.min_oi,
        min_volume=args.min_volume,
        max_bid_ask_spread_pct=args.max_spread,
        min_dte=args.min_dte,
        max_dte=args.max_dte,
        min_strike_width=args.min_width,
        max_strike_width=args.max_width,
        min_roi_pct=args.min_roi,
        max_per_type=args.max_per_type,
    )


def run_scan(args: argparse.Namespace) -> dict:
    """Run one scan cycle. Returns results dict."""
    db_url = get_db_url()
    conn = get_connection(db_url)
    pg = is_postgres(db_url)

    try:
        sf = args._signal_filter  # built in __main__

        results = build_filtered_spreads(
            conn,
            tickers=args.tickers,
            signal_filter=sf,
            is_pg=pg,
        )

        # Filter by type
        requested_types = TYPE_GROUPS.get(args.spread_type, TYPE_GROUPS["all"])
        filtered = {k: v for k, v in results.items() if k in requested_types}

        # Score
        scored = score_all(filtered)

        # Display
        now_str = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
        print(format_all_results(scored, now_str))

        # Discord
        if args.discord:
            total = sum(len(v) for v in scored.values())
            if total > 0:
                try:
                    from discord.webhook import send_message
                    msg = format_discord_message(scored, now_str)
                    send_message(msg)
                    logger.info(f"Discord alert sent ({total} candidates)")
                except Exception as exc:
                    logger.warning(f"Discord alert failed: {exc}")

        return scored

    finally:
        conn.close()


def run_scan_cycle(args: argparse.Namespace) -> None:
    if not is_market_hours():
        logger.debug("Outside market hours, skipping scan")
        return
    run_scan(args)


def start_scheduler(args: argparse.Namespace) -> None:
    logger.info(
        f"Starting spread hunter | interval={args.interval}m | "
        f"tickers={args.tickers or 'all'} | type={args.spread_type} | "
        f"discord={args.discord}"
    )

    scheduler = BlockingScheduler()

    trigger = CronTrigger(
        day_of_week="mon-fri",
        hour="9-16",
        minute=f"*/{args.interval}",
        timezone=ET,
    )

    scheduler.add_job(
        run_scan_cycle,
        trigger,
        args=[args],
        id="spread_hunter",
        max_instances=1,
        misfire_grace_time=120,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spread Hunter — multi-ticker spread scanner")

    parser.add_argument("--once", action="store_true", help="Single scan and exit")
    parser.add_argument("--interval", type=int, default=15, help="Minutes between scans (default: 15)")
    parser.add_argument("--tickers", nargs="+", default=None, help="Filter to specific tickers")
    parser.add_argument("--type", dest="spread_type", default="all",
                        choices=["credit", "iron_condor", "iron_fly", "calendar", "all"],
                        help="Spread types to scan (default: all)")
    parser.add_argument("--discord", action="store_true", help="Send alerts to Discord")
    parser.add_argument("--min-roi", type=float, default=10.0, help="Minimum ROI%% (default: 10)")
    parser.add_argument("--min-dte", type=int, default=1, help="Minimum DTE (default: 1)")
    parser.add_argument("--max-dte", type=int, default=45, help="Maximum DTE (default: 45)")
    parser.add_argument("--min-oi", type=int, default=50, help="Minimum open interest per leg (default: 50)")
    parser.add_argument("--min-volume", type=int, default=10, help="Minimum volume per leg (default: 10)")
    parser.add_argument("--max-spread", type=float, default=25.0, help="Max bid-ask spread%% per leg (default: 25)")
    parser.add_argument("--min-width", type=float, default=None, help="Min strike width (default: auto)")
    parser.add_argument("--max-width", type=float, default=None, help="Max strike width (default: auto)")
    parser.add_argument("--max-per-type", type=int, default=20, help="Max results per type per ticker (default: 20)")
    parser.add_argument("--dry-run", action="store_true", help="Scan but skip Discord")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed filter config and debug output")

    # Signal filters
    filter_group = parser.add_argument_group("Signal Filters (tunable trade gates)")
    filter_group.add_argument("--delta-min", type=float, default=0.10,
        help="Min abs(delta) for short leg (default: 0.10)")
    filter_group.add_argument("--delta-max", type=float, default=0.25,
        help="Max abs(delta) for short leg (default: 0.25)")
    filter_group.add_argument("--iv-rank-min", type=float, default=30.0,
        help="Min IV percentile rank to trade (default: 30)")
    filter_group.add_argument("--iv-rank-max", type=float, default=95.0,
        help="Max IV percentile rank (skip extreme IV) (default: 95)")
    filter_group.add_argument("--sig-min-oi", type=int, default=100,
        help="Min open interest per leg for signal filter (default: 100)")
    filter_group.add_argument("--sig-min-volume", type=int, default=50,
        help="Min daily volume per leg for signal filter (default: 50)")
    filter_group.add_argument("--sma-periods", type=int, default=20,
        help="Periods for SMA trend filter (default: 20)")
    filter_group.add_argument("--no-trend-filter", action="store_true",
        help="Disable trend (SMA) filter")
    filter_group.add_argument("--support-threshold", type=float, default=3.0,
        help="OI multiplier for support detection (default: 3.0)")
    filter_group.add_argument("--support-buffer", type=float, default=1.0,
        help="Don't sell within this %% of support (default: 1.0)")
    filter_group.add_argument("--sig-dte-min", type=int, default=5,
        help="Min days to expiration for signal filter (default: 5)")
    filter_group.add_argument("--sig-dte-max", type=int, default=9,
        help="Max days to expiration for signal filter (default: 9)")

    args = parser.parse_args()
    if args.dry_run:
        args.discord = False

    signal_filter = SignalFilter(
        delta_min=args.delta_min,
        delta_max=args.delta_max,
        iv_rank_min=args.iv_rank_min,
        iv_rank_max=args.iv_rank_max,
        min_oi=args.sig_min_oi,
        min_volume=args.sig_min_volume,
        trend_sma_periods=args.sma_periods,
        trend_require_above_sma=not args.no_trend_filter,
        support_oi_threshold=args.support_threshold,
        support_buffer_pct=args.support_buffer,
        min_dte=args.sig_dte_min,
        max_dte=args.sig_dte_max,
    )

    if args.verbose:
        print(f"SignalFilter: delta={args.delta_min}-{args.delta_max}, "
              f"iv_rank={args.iv_rank_min}-{args.iv_rank_max}, "
              f"oi>={args.sig_min_oi}, vol>={args.sig_min_volume}, "
              f"sma={args.sma_periods}, dte={args.sig_dte_min}-{args.sig_dte_max}")

    args._signal_filter = signal_filter

    if args.once:
        run_scan(args)
    else:
        start_scheduler(args)
