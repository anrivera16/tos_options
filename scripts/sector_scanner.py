"""
Sector Scanner — Bidirectional Options Signal Generator
========================================================
Reads the latest option chain snapshot from Postgres, computes per-ticker
IV baselines, detects mispricing, and posts actionable signals to Discord.

Runs every 5 minutes during market hours (alongside scraper + live_scanner).

Usage:
    python scripts/sector_scanner.py --once           # single scan
    python scripts/sector_scanner.py --interval 5     # continuous
    python scripts/sector_scanner.py --once --discord # with Discord alert
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import signal
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from scripts.shared import ET, is_market_hours, get_db_url, is_postgres

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def get_connection(url: str):
    if is_postgres(url):
        import psycopg
        return psycopg.connect(url)
    import sqlite3
    return sqlite3.connect(url)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TickerBaseline:
    """Rolling IV baseline for one ticker."""
    symbol: str
    sector: str
    iv_tier: str  # buy, sell, neutral
    spot: float
    avg_iv_10d: float | None
    avg_iv_1d: float | None
    current_iv: float | None
    iv_rank: float | None  # where current IV sits in 10-day range
    avg_mark_vs_theo: float | None  # avg(mark - theoretical) over snapshots
    current_mark: float | None
    current_theo: float | None
    mark_vs_theo_pct: float | None  # (mark - theo) / theo * 100
    snapshots_count: int = 0
    # Derived signals
    signal: str = "neutral"  # buy, sell, strong_buy, strong_sell, neutral
    signal_reason: str = ""


@dataclass
class SectorSignal:
    """Aggregated signal for one sector."""
    sector: str
    tickers_with_signals: list[TickerBaseline] = field(default_factory=list)
    avg_iv: float | None = None
    avg_iv_rank: float | None = None
    regime_bias: str = "neutral"  # buy_premium, sell_premium, neutral


# ---------------------------------------------------------------------------
# IV Baseline Tracking
# ---------------------------------------------------------------------------

def fetch_ticker_baselines(conn, core_tickers: list[dict], days: int = 10) -> list[TickerBaseline]:
    """
    Fetch IV data for all core tickers over the last N days.
    Computes per-ticker baselines: avg IV, IV rank, mark vs theoretical.
    """
    pg = is_postgres(get_db_url())
    symbol_list = [t["symbol"] for t in core_tickers]
    symbol_map = {t["symbol"]: t for t in core_tickers}

    if not symbol_list:
        return []

    if pg:
        placeholders = ", ".join(["%s"] * len(symbol_list))
        interval = f"INTERVAL '{days} days'"
    else:
        placeholders = ", ".join(["?"] * len(symbol_list))
        interval = f"'-{days} days'"

    # Per-ticker stats: latest snapshot + rolling averages
    query = f"""
        WITH ranked AS (
            SELECT
                s.symbol,
                s.captured_at,
                s.underlying_price,
                oc.put_call,
                oc.strike,
                oc.dte,
                oc.volatility,
                oc.mark,
                oc.theoretical_option_value,
                oc.open_interest,
                oc.total_volume,
                ROW_NUMBER() OVER (
                    PARTITION BY s.symbol, oc.put_call, oc.strike
                    ORDER BY s.captured_at DESC
                ) as rn
            FROM snapshots s
            JOIN option_contracts oc ON s.id = oc.snapshot_id
            WHERE s.symbol IN ({placeholders})
              AND oc.delta IS NOT NULL
              AND oc.volatility > 0
              AND oc.volatility < 200
              AND oc.dte = 7
              AND s.captured_at >= NOW() - {interval}
        )
        SELECT
            symbol,
            ROUND(AVG(volatility)::numeric, 2) as avg_iv,
            ROUND(AVG(mark)::numeric, 4) as avg_mark,
            ROUND(AVG(theoretical_option_value)::numeric, 4) as avg_theo,
            MIN(volatility) as min_iv,
            MAX(volatility) as max_iv,
            COUNT(*) as snapshot_count,
            AVG(underlying_price) as avg_spot
        FROM ranked
        WHERE rn = 1
        GROUP BY symbol
    """
    if pg:
        rows = conn.execute(query, symbol_list).fetchall()
    else:
        rows = conn.execute(query, symbol_list).fetchall()

    baselines: list[TickerBaseline] = []
    for row in rows:
        sym = row[0]
        avg_iv = float(row[1]) if row[1] else None
        avg_mark = float(row[2]) if row[2] else None
        avg_theo = float(row[3]) if row[3] else None
        min_iv = float(row[4]) if row[4] else None
        max_iv = float(row[5]) if row[5] else None
        count = int(row[6]) if row[6] else 0
        spot = float(row[7]) if row[7] else None

        cfg = symbol_map.get(sym, {})
        iv_tier = cfg.get("iv_tier", "neutral")
        sector = cfg.get("sector", "unknown")

        # IV rank within the baseline period (0-100)
        if min_iv and max_iv and avg_iv:
            iv_range = max_iv - min_iv
            iv_rank = ((avg_iv - min_iv) / iv_range * 100) if iv_range > 0 else 50
        else:
            iv_rank = None

        # Mark vs theoretical deviation
        mark_vs_theo_pct = None
        if avg_mark and avg_theo and avg_theo > 0:
            mark_vs_theo_pct = ((avg_mark - avg_theo) / avg_theo) * 100

        # Get latest snapshot's mark and theo for ATM options
        latest_query = f"""
            SELECT
                oc.mark,
                oc.theoretical_option_value,
                oc.volatility,
                s.underlying_price
            FROM option_contracts oc
            JOIN snapshots s ON s.id = oc.snapshot_id
            WHERE s.symbol = %s
              AND oc.dte = 7
              AND ABS(oc.delta) BETWEEN 0.45 AND 0.55
              AND oc.put_call = 'PUT'
              AND oc.volatility > 0
            ORDER BY s.captured_at DESC
            LIMIT 1
        """ if pg else """
            SELECT
                oc.mark,
                oc.theoretical_option_value,
                oc.volatility,
                s.underlying_price
            FROM option_contracts oc
            JOIN snapshots s ON s.id = oc.snapshot_id
            WHERE s.symbol = ?
              AND oc.dte = 7
              AND ABS(oc.delta) BETWEEN 0.45 AND 0.55
              AND oc.put_call = 'PUT'
              AND oc.volatility > 0
            ORDER BY s.captured_at DESC
            LIMIT 1
        """

        if pg:
            latest = conn.execute(latest_query, (sym,)).fetchone()
        else:
            latest = conn.execute(latest_query, (sym,)).fetchone()

        current_iv = float(latest[2]) if latest and latest[2] else None
        current_mark = float(latest[0]) if latest and latest[0] else None
        current_theo = float(latest[1]) if latest and latest[1] else None
        current_spot = float(latest[3]) if latest and latest[3] else spot

        # Compute signal
        signal, reason = compute_signal(avg_iv, iv_rank, mark_vs_theo_pct, iv_tier, count)

        baselines.append(TickerBaseline(
            symbol=sym,
            sector=sector,
            iv_tier=iv_tier,
            spot=current_spot or 0,
            avg_iv_10d=avg_iv,
            avg_iv_1d=avg_iv,  # same for now, will differentiate later
            current_iv=current_iv,
            iv_rank=round(iv_rank, 1) if iv_rank else None,
            avg_mark_vs_theo=mark_vs_theo_pct,
            current_mark=current_mark,
            current_theo=current_theo,
            mark_vs_theo_pct=round(mark_vs_theo_pct, 1) if mark_vs_theo_pct else None,
            snapshots_count=count,
            signal=signal,
            signal_reason=reason,
        ))

    return baselines


def compute_signal(avg_iv, iv_rank, mark_vs_theo_pct, iv_tier, count) -> tuple[str, str]:
    """
    Determine if a ticker is a buy, sell, or neutral signal.

    Rules:
    - Need at least 5 snapshots for a reliable signal
    - Strong sell: IV rank > 75 AND mark > theoretical by > 5%
    - Sell: IV rank > 60 AND mark >= theoretical
    - Strong buy: IV rank < 25 AND mark < theoretical by > 5%
    - Buy: IV rank < 30 AND mark <= theoretical
    - Neutral: otherwise
    """
    if count < 5:
        return "neutral", f"Need more data ({count}/5 snapshots)"

    if iv_rank is None or mark_vs_theo_pct is None:
        return "neutral", "Insufficient data"

    # Strong sell
    if iv_rank > 75 and mark_vs_theo_pct > 5:
        return "strong_sell", f"IV rank {iv_rank:.0f}, mark {mark_vs_theo_pct:+.1f}% vs theo"

    # Sell
    if iv_rank > 60 and mark_vs_theo_pct > 0:
        return "sell", f"IV rank {iv_rank:.0f}, mark {mark_vs_theo_pct:+.1f}% vs theo"

    # Strong buy
    if iv_rank < 25 and mark_vs_theo_pct < -5:
        return "strong_buy", f"IV rank {iv_rank:.0f}, mark {mark_vs_theo_pct:+.1f}% vs theo"

    # Buy
    if iv_rank < 30 and mark_vs_theo_pct < 0:
        return "buy", f"IV rank {iv_rank:.0f}, mark {mark_vs_theo_pct:+.1f}% vs theo"

    return "neutral", f"IV rank {iv_rank:.0f}, mark {mark_vs_theo_pct:+.1f}% vs theo"


def compute_sector_signals(baselines: list[TickerBaseline]) -> list[SectorSignal]:
    """Aggregate per-ticker baselines into sector-level signals."""
    sectors: dict[str, SectorSignal] = {}
    for b in baselines:
        if b.sector not in sectors:
            sectors[b.sector] = SectorSignal(sector=b.sector)
        if b.signal != "neutral":
            sectors[b.sector].tickers_with_signals.append(b)

    # Compute sector-level stats
    for sector, sig in sectors.items():
        sector_baselines = [b for b in baselines if b.sector == sector]
        ivs = [b.avg_iv_10d for b in sector_baselines if b.avg_iv_10d is not None]
        ranks = [b.iv_rank for b in sector_baselines if b.iv_rank is not None]
        sig.avg_iv = round(sum(ivs) / len(ivs), 1) if ivs else None
        sig.avg_iv_rank = round(sum(ranks) / len(ranks), 1) if ranks else None

        # Sector regime bias
        if sig.avg_iv_rank and sig.avg_iv_rank > 70:
            sig.regime_bias = "sell_premium"
        elif sig.avg_iv_rank and sig.avg_iv_rank < 30:
            sig.regime_bias = "buy_premium"

    return list(sectors.values())


# ---------------------------------------------------------------------------
# Output Formatting
# ---------------------------------------------------------------------------

def format_discord_message(baselines: list[TickerBaseline], sectors: list[SectorSignal]) -> str:
    """Format signals for Discord (compact, 2000 char limit)."""
    lines: list[str] = []

    # Filter to only tickers with signals
    signal_tickers = [b for b in baselines if b.signal != "neutral"]

    if not signal_tickers:
        lines.append("**Sector Scanner** — all neutral (building baselines)")
        # Show baseline progress
        building = [b for b in baselines if b.snapshots_count < 10]
        if building:
            lines.append(f"Baselines: {len(building)} tickers need more data")
            for b in building[:5]:
                lines.append(f"  {b.symbol}: {b.snapshots_count}/10 snapshots")
        return "\n".join(lines)

    # Determine overall regime
    sell_count = sum(1 for b in signal_tickers if "sell" in b.signal)
    buy_count = sum(1 for b in signal_tickers if "buy" in b.signal)

    if sell_count > buy_count:
        regime = "SELL PREMIUM"
        emoji = "\U0001f534"  # red circle
    elif buy_count > sell_count:
        regime = "BUY PREMIUM"
        emoji = "\U0001f7e2"  # green circle
    else:
        regime = "NEUTRAL"
        emoji = "\U0001f7e1"  # yellow circle

    now_str = datetime.now(ET).strftime("%H:%M ET")
    lines.append(f"{emoji} **Sector Scanner** {now_str} | Regime: **{regime}**")
    lines.append(f"{sell_count} sell | {buy_count} buy signals```\n")

    # Group by sector
    by_sector: dict[str, list[TickerBaseline]] = {}
    for b in signal_tickers:
        if b.sector not in by_sector:
            by_sector[b.sector] = []
        by_sector[b.sector].append(b)

    for sector_name in sorted(by_sector.keys()):
        tickers = by_sector[sector_name]
        lines.append(f"[{sector_name}]")

        for b in tickers[:3]:  # max 3 per sector to fit 2000 chars
            action = b.signal.replace("_", " ").upper()
            # Signal arrow
            if "buy" in b.signal:
                arrow = "\u2b07"  # down (cheap)
            else:
                arrow = "\u2b06"  # up (expensive)

            iv_str = f"{b.avg_iv_10d:.1f}%" if b.avg_iv_10d else "?"
            rank_str = f"{b.iv_rank:.0f}" if b.iv_rank else "?"
            misp_str = f"{b.mark_vs_theo_pct:+.1f}%" if b.mark_vs_theo_pct is not None else "?"

            lines.append(f"  {arrow} {b.symbol:<5} {action:<12} IV {iv_str:>5} "
                        f"rank {rank_str:>3}  mispricing {misp_str}")

        lines.append("")

    lines.append("```")
    lines.append("_IV rank = position in 10d range | mispricing = mark vs theoretical_")

    msg = "\n".join(lines)
    if len(msg) > 1900:
        msg = msg[:1890] + "\n...truncated```"
    return msg


def format_terminal(baselines: list[TickerBaseline], sectors: list[SectorSignal]):
    """Print to terminal for local review."""
    print(f"\n{'=' * 90}")
    print(f"  SECTOR SCANNER — {datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}")
    print(f"{'=' * 90}")

    signal_tickers = [b for b in baselines if b.signal != "neutral"]
    neutral_tickers = [b for b in baselines if b.signal == "neutral"]

    print(f"\n  Signals: {len(signal_tickers)} | Neutral: {len(neutral_tickers)} | Total: {len(baselines)}")

    if signal_tickers:
        print(f"\n  {'Symbol':<6} {'Sector':<20} {'Signal':<14} {'IV':>5} {'Rank':>5} "
              f"{'MisP%':>6} {'Spot':>8} {'Reason'}")
        print(f"  {'-' * 90}")
        for b in sorted(signal_tickers, key=lambda x: x.signal):
            iv_str = f"{b.avg_iv_10d:.1f}" if b.avg_iv_10d else "   -"
            rank_str = f"{b.iv_rank:.0f}" if b.iv_rank else "   -"
            misp_str = f"{b.mark_vs_theo_pct:+.1f}" if b.mark_vs_theo_pct is not None else "    -"
            spot_str = f"{b.spot:.1f}" if b.spot else "     -"
            print(f"  {b.symbol:<6} {b.sector:<20} {b.signal:<14} {iv_str:>5} "
                  f"{rank_str:>5} {misp_str:>6} {spot_str:>8} {b.signal_reason}")

    # Baseline progress
    building = [b for b in baselines if b.snapshots_count < 10]
    if building:
        print(f"\n  Building baselines ({len(building)} tickers):")
        for b in sorted(building, key=lambda x: x.snapshots_count):
            bar = "#" * b.snapshots_count + "-" * (10 - b.snapshots_count)
            print(f"    {b.symbol:<6} [{bar}] {b.snapshots_count}/10")


# ---------------------------------------------------------------------------
# Watchlist loader
# ---------------------------------------------------------------------------

def load_watchlist() -> list[dict]:
    """Load core watchlist from config/watchlist.yaml."""
    import yaml
    config_path = Path(project_root) / "config" / "watchlist.yaml"
    if not config_path.exists():
        logger.warning(f"Watchlist config not found at {config_path}")
        return []

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    core = cfg.get("core", {})
    tickers = []
    for sector_name, tickers_list in core.items():
        if not isinstance(tickers_list, list):
            continue
        for t in tickers_list:
            if isinstance(t, dict):
                tickers.append(t)
            elif isinstance(t, str):
                tickers.append({"symbol": t, "sector": sector_name, "iv_tier": "neutral"})

    return tickers


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def run_scan(discord: bool = False) -> None:
    """Run sector scanner (IV signals + flow) against latest snapshots."""
    db_url = get_db_url()
    if not is_postgres(db_url):
        logger.error("Sector scanner requires PostgreSQL connection")
        return

    core_tickers = load_watchlist()
    if not core_tickers:
        logger.error("No core tickers found in watchlist config")
        return

    logger.info(f"Scanning {len(core_tickers)} core tickers across {len(set(t['sector'] for t in core_tickers))} sectors")

    conn = get_connection(db_url)
    try:
        # Phase 1: IV signals
        baselines = fetch_ticker_baselines(conn, core_tickers, days=10)
        if baselines:
            sectors = compute_sector_signals(baselines)
            format_terminal(baselines, sectors)

            # Phase 2: Sector flow
            from scripts.sector_flow import fetch_sector_flow, fetch_volume_baselines
            from scripts.sector_flow import format_flow_terminal, format_flow_discord

            flow = fetch_sector_flow(conn, core_tickers)
            flow_baselines = fetch_volume_baselines(conn, core_tickers, days=5)

            # Attach volume vs avg
            for sf in flow.sectors:
                baseline = flow_baselines.get(sf.sector, 0)
                if baseline > 0:
                    sf.volume_vs_avg = round(sf.total_volume / baseline, 2)

            format_flow_terminal(flow, flow_baselines)

            if discord:
                # Combine IV signals + flow into one message
                signal_lines = format_discord_message(baselines, sectors)
                flow_lines = format_flow_discord(flow, flow_baselines)

                # Split into 2 messages if combined > 1900 chars
                combined = signal_lines + "\n\n" + flow_lines
                if len(combined) > 1900:
                    # Send IV signals first
                    try:
                        from discord.webhook import send_message
                        send_message(signal_lines)
                        logger.info(f"IV signal alert sent")
                    except Exception as exc:
                        logger.warning(f"Discord alert failed: {exc}")

                    # Send flow second
                    try:
                        from discord.webhook import send_message
                        send_message(flow_lines)
                        logger.info(f"Flow alert sent")
                    except Exception as exc:
                        logger.warning(f"Discord alert failed: {exc}")
                else:
                    try:
                        from discord.webhook import send_message
                        send_message(combined)
                        logger.info("Combined IV+flow alert sent")
                    except Exception as exc:
                        logger.warning(f"Discord alert failed: {exc}")
        else:
            logger.info("No data found yet — baselines will build as scraper runs")

    finally:
        conn.close()


def run_scan_cycle(discord: bool) -> None:
    if not is_market_hours():
        logger.debug("Outside market hours, skipping scan")
        return
    run_scan(discord=discord)


def start_scheduler(interval_minutes: int = 5, discord: bool = False) -> None:
    logger.info(f"Starting sector scanner | interval={interval_minutes}m | discord={discord}")

    scheduler = BlockingScheduler()

    trigger = CronTrigger(
        day_of_week="mon-fri",
        hour="4-19",
        minute=f"*/{interval_minutes}",
        timezone=ET,
    )

    scheduler.add_job(
        run_scan_cycle,
        trigger,
        args=[discord],
        id="sector_scanner",
        max_instances=1,
        misfire_grace_time=120,
    )

    from scripts.shared import send_heartbeat_alert, send_token_alert

    # Heartbeat check
    heartbeat_trigger = CronTrigger(
        day_of_week="mon-fri",
        hour="4-19",
        minute="*/5",
        timezone=ET,
    )
    scheduler.add_job(
        send_heartbeat_alert,
        heartbeat_trigger,
        args=[get_db_url()],
        id="sector_heartbeat",
        max_instances=1,
        misfire_grace_time=300,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down sector scanner...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scanner stopped")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sector scanner for bidirectional options signals")
    parser.add_argument("--once", action="store_true", help="Run single scan and exit")
    parser.add_argument("--interval", type=int, default=5, help="Minutes between scans (default: 5)")
    parser.add_argument("--discord", action="store_true", help="Send alerts to Discord")
    parser.add_argument("--db", default=None, help="Database URL override")
    args = parser.parse_args()

    if args.db:
        os.environ["DATABASE_URL"] = args.db

    if args.once:
        run_scan(discord=args.discord)
    else:
        start_scheduler(interval_minutes=args.interval, discord=args.discord)


if __name__ == "__main__":
    main()
