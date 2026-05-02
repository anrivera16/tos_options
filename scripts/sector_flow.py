"""
Sector Flow Tracker — Phase 2 of Sector Scanner
=================================================
Computes sector-level positioning and flow signals from DB data.
Zero new API calls — reads what the scraper already collects.

Metrics:
- Volume surge vs historical average
- Put/Call ratio by sector (volume + OI)
- Premium flow (volume × mark price)
- OTM vs ITM volume preference
- Open Interest change estimate (intraday proxy)

Usage:
    python scripts/sector_flow.py --once           # single scan
    python scripts/sector_flow.py --once --discord # with Discord alert
    # Or integrate into sector_scanner.py scheduler
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from scripts.shared import ET, is_market_hours, get_db_url, is_postgres

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


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
class SectorFlow:
    """Flow metrics for one sector."""
    sector: str
    call_volume: int = 0
    put_volume: int = 0
    call_oi: int = 0
    put_oi: int = 0
    otm_volume: int = 0
    total_volume: int = 0
    premium_flow: float = 0.0  # sum(volume * mark)
    avg_premium_per_contract: float = 0.0
    # Ratios
    pcr_volume: float | None = None  # put volume / call volume
    pcr_oi: float | None = None      # put OI / call OI
    otm_ratio: float | None = None   # OTM volume / total volume
    # Signals
    volume_vs_avg: float | None = None  # current vol / avg vol
    flow_direction: str = "neutral"     # bullish, bearish, neutral
    signal_strength: str = ""           # weak, moderate, strong

    @property
    def emoji(self) -> str:
        if self.flow_direction == "bullish":
            return "\U0001f7e2"  # green
        elif self.flow_direction == "bearish":
            return "\U0001f534"  # red
        return "\U0001f7e1"  # yellow


@dataclass
class FlowSnapshot:
    """Complete flow snapshot across all sectors."""
    timestamp: str
    sectors: list[SectorFlow] = field(default_factory=list)
    total_volume: int = 0
    total_premium: float = 0.0
    overall_pcr: float | None = None


# ---------------------------------------------------------------------------
# Flow calculation
# ---------------------------------------------------------------------------

def fetch_sector_flow(conn, core_tickers: list[dict]) -> FlowSnapshot:
    """
    Compute flow metrics per sector from the latest snapshot.
    """
    symbol_list = [t["symbol"] for t in core_tickers]
    sector_map = {t["symbol"]: t.get("sector", "unknown") for t in core_tickers}

    if not symbol_list:
        return FlowSnapshot(timestamp=datetime.now(ET).isoformat())

    pg = is_postgres(get_db_url())
    placeholders = ", ".join(["%s"] * len(symbol_list)) if pg else ", ".join(["?"] * len(symbol_list))

    # Get latest snapshot ID per symbol
    if pg:
        latest_snaps = conn.execute(f"""
            SELECT DISTINCT ON (symbol) id, symbol, captured_at, underlying_price
            FROM snapshots
            WHERE symbol IN ({placeholders})
            ORDER BY symbol, captured_at DESC
        """, symbol_list).fetchall()
    else:
        latest_snaps = []
        for sym in symbol_list:
            row = conn.execute(f"""
                SELECT id, symbol, captured_at, underlying_price
                FROM snapshots
                WHERE symbol = ?
                ORDER BY captured_at DESC
                LIMIT 1
            """, (sym,)).fetchone()
            if row:
                latest_snaps.append(row)

    if not latest_snaps:
        return FlowSnapshot(timestamp=datetime.now(ET).isoformat())

    snap_ids = [r[0] for r in latest_snaps]
    id_placeholders = ", ".join(["%s"] * len(snap_ids)) if pg else ", ".join(["?"] * len(snap_ids))

    # Fetch all contracts for these snapshots
    query = f"""
        SELECT
            s.symbol,
            oc.put_call,
            oc.strike,
            oc.dte,
            oc.total_volume,
            oc.open_interest,
            oc.mark,
            s.underlying_price,
            oc.in_the_money
        FROM option_contracts oc
        JOIN snapshots s ON oc.snapshot_id = s.id
        WHERE s.id IN ({id_placeholders})
    """

    if pg:
        rows = conn.execute(query, snap_ids).fetchall()
    else:
        rows = conn.execute(query, snap_ids).fetchall()

    # Aggregate by sector
    sector_data: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol, pc, strike, dte, vol, oi, mark, spot, itm = row
        sector = sector_map.get(symbol, "unknown")
        if sector not in sector_data:
            sector_data[sector] = {
                "call_volume": 0, "put_volume": 0,
                "call_oi": 0, "put_oi": 0,
                "otm_volume": 0, "total_volume": 0,
                "premium_flow": 0.0, "contract_count": 0,
                "total_mark_sum": 0.0,
            }

        vol = int(vol or 0)
        oi = int(oi or 0)
        mark_f = float(mark or 0)
        spot_f = float(spot or 0)

        if pc == "CALL":
            sector_data[sector]["call_volume"] += vol
            sector_data[sector]["call_oi"] += oi
        elif pc == "PUT":
            sector_data[sector]["put_volume"] += vol
            sector_data[sector]["put_oi"] += oi

        # OTM check
        is_otm = False
        if pc == "CALL" and spot_f > 0:
            is_otm = strike > spot_f
        elif pc == "PUT" and spot_f > 0:
            is_otm = strike < spot_f

        if is_otm:
            sector_data[sector]["otm_volume"] += vol

        sector_data[sector]["total_volume"] += vol
        sector_data[sector]["premium_flow"] += vol * mark_f
        sector_data[sector]["total_mark_sum"] += mark_f
        sector_data[sector]["contract_count"] += 1

    # Build SectorFlow objects
    sectors: list[SectorFlow] = []
    for sector_name, data in sorted(sector_data.items()):
        sf = SectorFlow(
            sector=sector_name,
            call_volume=data["call_volume"],
            put_volume=data["put_volume"],
            call_oi=data["call_oi"],
            put_oi=data["put_oi"],
            otm_volume=data["otm_volume"],
            total_volume=data["total_volume"],
            premium_flow=round(data["premium_flow"], 2),
        )

        # Compute ratios
        if sf.call_volume > 0:
            sf.pcr_volume = round(sf.put_volume / sf.call_volume, 2)
        if sf.call_oi > 0:
            sf.pcr_oi = round(sf.put_oi / sf.call_oi, 2)
        if sf.total_volume > 0:
            sf.otm_ratio = round(sf.otm_volume / sf.total_volume, 2)
        if sf.total_volume > 0:
            sf.avg_premium_per_contract = round(data["total_mark_sum"] / sf.total_volume, 2) if sf.total_volume > 0 else 0

        # Determine flow direction
        if sf.pcr_volume is not None:
            if sf.pcr_volume < 0.7:
                sf.flow_direction = "bullish"
            elif sf.pcr_volume > 1.3:
                sf.flow_direction = "bearish"
            else:
                sf.flow_direction = "neutral"

        # Signal strength based on volume
        if sf.total_volume > 500000:
            sf.signal_strength = "strong"
        elif sf.total_volume > 100000:
            sf.signal_strength = "moderate"
        else:
            sf.signal_strength = "weak"

        sectors.append(sf)

    # Overall stats
    total_vol = sum(s.total_volume for s in sectors)
    total_prem = sum(s.premium_flow for s in sectors)
    total_puts = sum(s.put_volume for s in sectors)
    total_calls = sum(s.call_volume for s in sectors)
    overall_pcr = round(total_puts / total_calls, 2) if total_calls > 0 else None

    return FlowSnapshot(
        timestamp=datetime.now(ET).isoformat(),
        sectors=sectors,
        total_volume=total_vol,
        total_premium=round(total_prem, 2),
        overall_pcr=overall_pcr,
    )


def fetch_volume_baselines(conn, core_tickers: list[dict], days: int = 5) -> dict[str, float]:
    """
    Compute average daily volume per sector from historical snapshots.
    Used to detect volume surges.
    """
    symbol_list = [t["symbol"] for t in core_tickers]
    sector_map = {t["symbol"]: t.get("sector", "unknown") for t in core_tickers}

    if not symbol_list:
        return {}

    pg = is_postgres(get_db_url())
    placeholders = ", ".join(["%s"] * len(symbol_list)) if pg else ", ".join(["?"] * len(symbol_list))
    interval = f"INTERVAL '{days} days'" if pg else f"'-{days} days'"

    query = f"""
        SELECT
            s.symbol,
            DATE(s.captured_at) as day,
            SUM(oc.total_volume) as day_volume
        FROM snapshots s
        JOIN option_contracts oc ON s.id = oc.snapshot_id
        WHERE s.symbol IN ({placeholders})
          AND s.captured_at >= NOW() - {interval}
        GROUP BY s.symbol, DATE(s.captured_at)
    """

    if pg:
        rows = conn.execute(query, symbol_list).fetchall()
    else:
        rows = conn.execute(query, symbol_list).fetchall()

    # Aggregate by sector per day, then average
    sector_daily: dict[str, list[int]] = {}
    for symbol, day, vol in rows:
        sector = sector_map.get(symbol, "unknown")
        if sector not in sector_daily:
            sector_daily[sector] = []
        sector_daily[sector].append(int(vol or 0))

    baselines = {}
    for sector, volumes in sector_daily.items():
        if volumes:
            baselines[sector] = sum(volumes) / len(volumes)

    return baselines


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_flow_discord(flow: FlowSnapshot, baselines: dict[str, float]) -> str:
    """Format sector flow for Discord."""
    lines: list[str] = []
    now_str = datetime.now(ET).strftime("%H:%M ET")

    # Header
    pcr_emoji = "\U0001f534" if (flow.overall_pcr and flow.overall_pcr > 1.0) else "\U0001f7e2"
    lines.append(f"{pcr_emoji} **Sector Flow** {now_str}")
    lines.append(f"Total vol: **{flow.total_volume:,}** | Premium: **${flow.total_premium/1e6:.2f}M** | PCR: **{flow.overall_pcr or 'N/A'}**")

    if not flow.sectors:
        lines.append("No data available yet.")
        return "\n".join(lines)

    lines.append("```")

    # Sort by volume descending
    sorted_sectors = sorted(flow.sectors, key=lambda s: s.total_volume, reverse=True)

    for sf in sorted_sectors:
        if sf.total_volume < 1000:
            continue  # skip tiny sectors

        # Volume vs baseline
        baseline = baselines.get(sf.sector, 0)
        vol_change = ""
        if baseline > 0:
            ratio = sf.total_volume / baseline
            if ratio > 2.0:
                vol_change = f" \U0001f6a8 +{(ratio-1)*100:.0f}% vol surge"
            elif ratio > 1.5:
                vol_change = f" \u2b06 +{(ratio-1)*100:.0f}% vol"

        # Premium flow
        prem_str = f"${sf.premium_flow/1e6:.1f}M" if sf.premium_flow >= 1e6 else f"${sf.premium_flow/1e3:.0f}K"

        # PCR with emoji
        pcr_str = f"{sf.pcr_volume:.2f}" if sf.pcr_volume else "N/A"

        # OTM ratio
        otm_str = f"{sf.otm_ratio:.2f}" if sf.otm_ratio else "N/A"

        lines.append(
            f"[{sf.emoji} {sf.sector.upper()}] Vol: {sf.total_volume:,} | PCR: {pcr_str} "
            f"| OTM: {otm_str} | Premium: {prem_str}{vol_change}"
        )

        # Top tickers in this sector (if we have detail)
        # For now just show the sector-level summary

    lines.append("```")
    lines.append("_PCR < 0.7 = bullish | > 1.3 = bearish | OTM = speculative flow_")

    msg = "\n".join(lines)
    if len(msg) > 1900:
        msg = msg[:1890] + "\n...truncated```"
    return msg


def format_flow_terminal(flow: FlowSnapshot, baselines: dict[str, float]):
    """Print sector flow to terminal."""
    print(f"\n{'=' * 90}")
    print(f"  SECTOR FLOW — {datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}")
    print(f"{'=' * 90}")

    if not flow.sectors:
        print("  No data available.")
        return

    print(f"\n  Overall: Vol {flow.total_volume:,} | Premium ${flow.total_premium:,.0f} | PCR {flow.overall_pcr}")
    print(f"\n  {'Sector':<20} {'Vol':>8} {'PCR':>5} {'OTM':>5} {'Premium':>10} {'vs Avg':>8} {'Direction':<10} {'Strength':<10}")
    print(f"  {'-' * 90}")

    for sf in sorted(flow.sectors, key=lambda s: s.total_volume, reverse=True):
        if sf.total_volume < 1000:
            continue

        baseline = baselines.get(sf.sector, 0)
        vs_avg = ""
        if baseline > 0:
            ratio = sf.total_volume / baseline
            vs_avg = f"{ratio:.1f}x"

        pcr_str = f"{sf.pcr_volume:.2f}" if sf.pcr_volume else "   -"
        otm_str = f"{sf.otm_ratio:.2f}" if sf.otm_ratio else "   -"
        prem_str = f"${sf.premium_flow:,.0f}"

        print(f"  {sf.sector:<20} {sf.total_volume:>8,} {pcr_str:>5} {otm_str:>5} {prem_str:>10} {vs_avg:>8} "
              f"{sf.flow_direction:<10} {sf.signal_strength:<10}")


# ---------------------------------------------------------------------------
# Watchlist loader
# ---------------------------------------------------------------------------

def load_watchlist() -> list[dict]:
    """Load core watchlist from config."""
    import yaml
    config_path = os.path.join(project_root, "config", "watchlist.yaml")
    if not os.path.exists(config_path):
        logger.warning(f"Watchlist not found at {config_path}")
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
# Main
# ---------------------------------------------------------------------------

def run_flow_scan(discord: bool = False) -> None:
    """Run sector flow analysis."""
    db_url = get_db_url()
    if not is_postgres(db_url):
        logger.error("Sector flow requires PostgreSQL connection")
        return

    core_tickers = load_watchlist()
    if not core_tickers:
        logger.error("No core tickers found")
        return

    logger.info(f"Computing flow for {len(core_tickers)} tickers across {len(set(t.get('sector') for t in core_tickers))} sectors")

    conn = get_connection(db_url)
    try:
        flow = fetch_sector_flow(conn, core_tickers)
        baselines = fetch_volume_baselines(conn, core_tickers, days=5)

        # Attach volume vs avg to each sector
        for sf in flow.sectors:
            baseline = baselines.get(sf.sector, 0)
            if baseline > 0:
                sf.volume_vs_avg = round(sf.total_volume / baseline, 2)

        format_flow_terminal(flow, baselines)

        if discord and flow.total_volume > 0:
            msg = format_flow_discord(flow, baselines)
            try:
                from discord.webhook import send_message
                send_message(msg)
                logger.info(f"Flow alert sent ({len(flow.sectors)} sectors)")
            except Exception as exc:
                logger.warning(f"Discord alert failed: {exc}")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Sector flow tracker")
    parser.add_argument("--once", action="store_true", help="Run single scan and exit")
    parser.add_argument("--interval", type=int, default=5, help="Minutes between scans")
    parser.add_argument("--discord", action="store_true", help="Send alerts to Discord")
    parser.add_argument("--db", default=None, help="Database URL override")
    args = parser.parse_args()

    if args.db:
        os.environ["DATABASE_URL"] = args.db

    if args.once:
        run_flow_scan(discord=args.discord)
    else:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger

        logger.info(f"Starting sector flow tracker | interval={args.interval}m")
        scheduler = BlockingScheduler()

        trigger = CronTrigger(
            day_of_week="mon-fri",
            hour="4-19",
            minute=f"*/{args.interval}",
            timezone=ET,
        )

        scheduler.add_job(
            run_flow_scan,
            trigger,
            args=[args.discord],
            id="sector_flow",
            max_instances=1,
            misfire_grace_time=120,
        )

        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()


if __name__ == "__main__":
    main()
