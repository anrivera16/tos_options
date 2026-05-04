"""
Sector Flow Tracker — Phase 2 of Sector Scanner
=================================================
Computes sector-level positioning and flow signals from DB data.
Zero new API calls — reads what the scraper already collects.

Metrics:
- Volume surge vs historical average
- Put/Call ratio by sector (volume + OI)
- Premium flow (volume × mark price)
- Call vs Put premium split
- IV level and IV skew by sector
- Bid/ask spread (liquidity quality)
- Vol/OI ratio (churn vs new positions)
- ATM vs OTM volume split
- OTM call vs put volume (bullish vs bearish speculation)
- Strike concentration (top 5 strikes by volume)
- DTE distribution (near/mid/far term positioning)

Usage:
    python scripts/sector_flow.py --once           # single scan
    python scripts/sector_flow.py --once --discord # with Discord alert
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import defaultdict
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
    """Comprehensive flow metrics for one sector."""
    sector: str
    # Volume & positioning
    call_volume: int = 0
    put_volume: int = 0
    call_oi: int = 0
    put_oi: int = 0
    otm_call_volume: int = 0
    otm_put_volume: int = 0
    atm_volume: int = 0
    # Premium
    call_premium: float = 0.0
    put_premium: float = 0.0
    total_premium: float = 0.0
    # IV
    avg_call_iv: float | None = None
    avg_put_iv: float | None = None
    iv_skew: float | None = None  # put IV - call IV
    # Liquidity
    avg_bid_ask: float | None = None
    vol_oi_ratio: float | None = None
    # Mispricing
    avg_misprice_pct: float | None = None
    # DTE distribution
    near_term_vol: int = 0
    mid_term_vol: int = 0
    far_term_vol: int = 0
    # Strike concentration
    strike_volumes: dict[float, int] = field(default_factory=dict)
    top5_strikes: list[tuple[float, int]] = field(default_factory=list)
    top5_volume_pct: float = 0.0
    # Signals
    pcr_volume: float | None = None
    pcr_oi: float | None = None
    otm_ratio: float | None = None
    flow_direction: str = "neutral"
    signal_strength: str = "weak"
    volume_vs_avg: float | None = None

    @property
    def total_volume(self) -> int:
        return self.call_volume + self.put_volume

    @property
    def emoji(self) -> str:
        if self.flow_direction == "bullish":
            return "\U0001f7e2"
        elif self.flow_direction == "bearish":
            return "\U0001f534"
        return "\U0001f7e1"


@dataclass
class FlowSnapshot:
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
    Compute comprehensive flow metrics per sector from the latest snapshot.
    """
    symbol_list = [t["symbol"] for t in core_tickers]
    sector_map = {t["symbol"]: t.get("sector", "unknown") for t in core_tickers}

    if not symbol_list:
        return FlowSnapshot(timestamp=datetime.now(ET).isoformat())

    pg = is_postgres(get_db_url())
    sym_placeholders = ", ".join(["%s"] * len(symbol_list)) if pg else ", ".join(["?"] * len(symbol_list))

    # Get latest snapshot ID per symbol
    if pg:
        latest_snaps = conn.execute(f"""
            SELECT DISTINCT ON (symbol) id, symbol, captured_at, underlying_price
            FROM snapshots
            WHERE symbol IN ({sym_placeholders})
            ORDER BY symbol, captured_at DESC
        """, symbol_list).fetchall()
    else:
        latest_snaps = []
        for sym in symbol_list:
            row = conn.execute(f"""
                SELECT id, symbol, captured_at, underlying_price
                FROM snapshots WHERE symbol = ?
                ORDER BY captured_at DESC LIMIT 1
            """, (sym,)).fetchone()
            if row:
                latest_snaps.append(row)

    if not latest_snaps:
        return FlowSnapshot(timestamp=datetime.now(ET).isoformat())

    snap_ids = [r[0] for r in latest_snaps]
    snap_id_placeholders = ", ".join(["%s"] * len(snap_ids)) if pg else ", ".join(["?"] * len(snap_ids))

    # Fetch all contracts with full detail
    query = f"""
        SELECT
            s.symbol,
            oc.put_call,
            oc.strike,
            oc.total_volume,
            oc.open_interest,
            oc.mark,
            oc.bid,
            oc.ask,
            s.underlying_price,
            oc.volatility,
            oc.theoretical_option_value,
            oc.delta,
            oc.dte
        FROM option_contracts oc
        JOIN snapshots s ON oc.snapshot_id = s.id
        WHERE s.id IN ({snap_id_placeholders})
        AND oc.delta IS NOT NULL
    """

    if pg:
        rows = conn.execute(query, snap_ids).fetchall()
    else:
        rows = conn.execute(query, snap_ids).fetchall()

    # Aggregate per sector
    sector_raw: dict[str, dict[str, Any]] = {}

    for row in rows:
        (symbol, pc, strike, vol, oi, mark, bid, ask,
         spot, iv, theo, delta, dte) = row
        sector = sector_map.get(symbol, "unknown")
        if sector not in sector_raw:
            sector_raw[sector] = {
                "call_vol": 0, "put_vol": 0,
                "call_oi": 0, "put_oi": 0,
                "otm_call_vol": 0, "otm_put_vol": 0, "atm_vol": 0,
                "call_prem": 0.0, "put_prem": 0.0,
                "call_iv_sum": 0.0, "call_iv_n": 0,
                "put_iv_sum": 0.0, "put_iv_n": 0,
                "spread_sum": 0.0, "spread_n": 0,
                "misprice_sum": 0.0, "misprice_n": 0,
                "near_vol": 0, "mid_vol": 0, "far_vol": 0,
                "strike_vols": defaultdict(int),
            }

        d = sector_raw[sector]
        vol_i = int(vol or 0)
        oi_i = int(oi or 0)
        mark_f = float(mark or 0)
        bid_f = float(bid or 0)
        ask_f = float(ask or 0)
        spot_f = float(spot or 0)
        iv_f = float(iv or 0)
        theo_f = float(theo or 0) if theo else None
        delta_f = float(delta or 0)
        dte_i = int(dte or 0)

        # Volume
        if pc == "CALL":
            d["call_vol"] += vol_i
            d["call_oi"] += oi_i
            d["call_prem"] += vol_i * mark_f
            if iv_f > 0:
                d["call_iv_sum"] += iv_f
                d["call_iv_n"] += 1
        else:
            d["put_vol"] += vol_i
            d["put_oi"] += oi_i
            d["put_prem"] += vol_i * mark_f
            if iv_f > 0:
                d["put_iv_sum"] += iv_f
                d["put_iv_n"] += 1

        # ATM vs OTM
        if spot_f > 0:
            dist_pct = abs(strike - spot_f) / spot_f * 100
            if dist_pct < 1.0:
                d["atm_vol"] += vol_i
            else:
                if pc == "CALL" and strike > spot_f:
                    d["otm_call_vol"] += vol_i
                elif pc == "PUT" and strike < spot_f:
                    d["otm_put_vol"] += vol_i

        # Bid/ask spread
        if ask_f > 0 and bid_f > 0:
            d["spread_sum"] += (ask_f - bid_f)
            d["spread_n"] += 1

        # Mispricing
        if theo_f and theo_f > 0 and mark_f > 0:
            mispct = ((mark_f - theo_f) / theo_f) * 100
            d["misprice_sum"] += mispct
            d["misprice_n"] += 1

        # DTE split
        if dte_i <= 7:
            d["near_vol"] += vol_i
        elif dte_i <= 30:
            d["mid_vol"] += vol_i
        else:
            d["far_vol"] += vol_i

        # Strike concentration
        strike_rounded = round(strike / 5.0) * 5.0  # round to nearest $5
        d["strike_vols"][strike_rounded] += vol_i

    # Build SectorFlow objects
    sectors: list[SectorFlow] = []
    for sector_name, d in sorted(sector_raw.items()):
        sf = SectorFlow(sector=sector_name)
        sf.call_volume = d["call_vol"]
        sf.put_volume = d["put_vol"]
        sf.call_oi = d["call_oi"]
        sf.put_oi = d["put_oi"]
        sf.otm_call_volume = d["otm_call_vol"]
        sf.otm_put_volume = d["otm_put_vol"]
        sf.atm_volume = d["atm_vol"]
        sf.call_premium = round(d["call_prem"], 2)
        sf.put_premium = round(d["put_prem"], 2)
        sf.total_premium = round(d["call_prem"] + d["put_prem"], 2)
        sf.near_term_vol = d["near_vol"]
        sf.mid_term_vol = d["mid_vol"]
        sf.far_term_vol = d["far_vol"]

        # Ratios
        if sf.call_volume > 0:
            sf.pcr_volume = round(sf.put_volume / sf.call_volume, 2)
        if sf.call_oi > 0:
            sf.pcr_oi = round(sf.put_oi / sf.call_oi, 2)
        if sf.total_volume > 0:
            sf.otm_ratio = round((sf.otm_call_volume + sf.otm_put_volume) / sf.total_volume, 2)
            total_oi = sf.call_oi + sf.put_oi
            if total_oi > 0:
                sf.vol_oi_ratio = round(sf.total_volume / total_oi, 2)

        # IV
        if d["call_iv_n"] > 0:
            sf.avg_call_iv = round(d["call_iv_sum"] / d["call_iv_n"], 1)
        if d["put_iv_n"] > 0:
            sf.avg_put_iv = round(d["put_iv_sum"] / d["put_iv_n"], 1)
        if sf.avg_call_iv is not None and sf.avg_put_iv is not None:
            sf.iv_skew = round(sf.avg_put_iv - sf.avg_call_iv, 1)

        # Liquidity
        if d["spread_n"] > 0:
            sf.avg_bid_ask = round(d["spread_sum"] / d["spread_n"], 4)

        # Mispricing
        if d["misprice_n"] > 0:
            sf.avg_misprice_pct = round(d["misprice_sum"] / d["misprice_n"], 2)

        # Strike concentration
        sorted_strikes = sorted(d["strike_vols"].items(), key=lambda x: x[1], reverse=True)[:5]
        sf.top5_strikes = sorted_strikes
        top5_vol = sum(v for _, v in sorted_strikes)
        sf.top5_volume_pct = round(top5_vol / sf.total_volume * 100, 1) if sf.total_volume > 0 else 0

        # Direction
        if sf.pcr_volume is not None:
            if sf.pcr_volume < 0.7:
                sf.flow_direction = "bullish"
            elif sf.pcr_volume > 1.3:
                sf.flow_direction = "bearish"

        # Strength
        if sf.total_volume > 500000:
            sf.signal_strength = "strong"
        elif sf.total_volume > 100000:
            sf.signal_strength = "moderate"
        else:
            sf.signal_strength = "weak"

        sectors.append(sf)

    # Overall stats
    total_vol = sum(s.total_volume for s in sectors)
    total_prem = sum(s.total_premium for s in sectors)
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
    """Compute average daily volume per sector from historical snapshots."""
    symbol_list = [t["symbol"] for t in core_tickers]
    sector_map = {t["symbol"]: t.get("sector", "unknown") for t in core_tickers}

    if not symbol_list:
        return {}

    pg = is_postgres(get_db_url())
    sym_placeholders = ", ".join(["%s"] * len(symbol_list)) if pg else ", ".join(["?"] * len(symbol_list))
    interval = f"INTERVAL '{days} days'" if pg else f"'-{days} days'"

    query = f"""
        SELECT s.symbol, DATE(s.captured_at) as day, SUM(oc.total_volume) as day_vol
        FROM snapshots s
        JOIN option_contracts oc ON s.id = oc.snapshot_id
        WHERE s.symbol IN ({sym_placeholders})
          AND s.captured_at >= NOW() - {interval}
        GROUP BY s.symbol, DATE(s.captured_at)
    """

    if pg:
        rows = conn.execute(query, symbol_list).fetchall()
    else:
        rows = conn.execute(query, symbol_list).fetchall()

    sector_daily: dict[str, list[int]] = {}
    for symbol, day, vol in rows:
        sector = sector_map.get(symbol, "unknown")
        if sector not in sector_daily:
            sector_daily[sector] = []
        sector_daily[sector].append(int(vol or 0))

    return {sec: sum(vols)/len(vols) for sec, vols in sector_daily.items() if vols}


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _format_prem(p: float) -> str:
    if p >= 1e6:
        return f"${p/1e6:.1f}M"
    elif p >= 1e3:
        return f"${p/1e3:.0f}K"
    return f"${p:.0f}"


def format_flow_discord(flow: FlowSnapshot, baselines: dict[str, float]) -> str:
    """Format sector flow for Discord (compact but data-rich)."""
    lines: list[str] = []
    now_str = datetime.now(ET).strftime("%H:%M ET")

    pcr_emoji = "\U0001f534" if (flow.overall_pcr and flow.overall_pcr > 1.0) else "\U0001f7e2"
    lines.append(f"{pcr_emoji} **Sector Flow** {now_str}")
    lines.append(f"Vol: **{flow.total_volume:,}** | Prem: **{_format_prem(flow.total_premium)}** | PCR: **{flow.overall_pcr or 'N/A'}**")

    if not flow.sectors:
        lines.append("No data available yet.")
        return "\n".join(lines)

    lines.append("```")
    sorted_sectors = sorted(flow.sectors, key=lambda s: s.total_volume, reverse=True)

    for sf in sorted_sectors:
        if sf.total_volume < 1000:
            continue

        baseline = baselines.get(sf.sector, 0)
        vol_change = ""
        if baseline > 0:
            ratio = sf.total_volume / baseline
            if ratio > 2.0:
                vol_change = f" \U0001f6a8 +{(ratio-1)*100:.0f}%"
            elif ratio > 1.5:
                vol_change = f" \u2b06 +{(ratio-1)*100:.0f}%"

        pcr_str = f"{sf.pcr_volume:.2f}" if sf.pcr_volume else "N/A"
        otm_str = f"{sf.otm_ratio:.2f}" if sf.otm_ratio else "N/A"
        iv_str = f"{sf.avg_call_iv:.0f}" if sf.avg_call_iv else "-"
        skew_str = f"{sf.iv_skew:+.1f}" if sf.iv_skew is not None else "-"
        spread_str = f"${sf.avg_bid_ask:.3f}" if sf.avg_bid_ask else "-"
        prem_split = f"{_format_prem(sf.call_premium)}C / {_format_prem(sf.put_premium)}P"

        lines.append(
            f"[{sf.emoji} {sf.sector.upper()}] Vol: {sf.total_volume:,}{vol_change} | "
            f"PCR: {pcr_str} | OTM: {otm_str} | IV: {iv_str} | Skew: {skew_str} | "
            f"Spread: {spread_str}"
        )
        lines.append(f"  Prem: {prem_split} | Top: {sf.top5_volume_pct:.0f}% in top 5 strikes")

    lines.append("```")
    lines.append("_PCR<0.7=bullish >1.3=bearish | Skew=putIV-callIV (>0=fear) | Prem=C/P split_")

    msg = "\n".join(lines)
    if len(msg) > 1900:
        msg = msg[:1890] + "\n...truncated```"
    return msg


def format_flow_terminal(flow: FlowSnapshot, baselines: dict[str, float]):
    """Print detailed sector flow to terminal."""
    print(f"\n{'='*130}")
    print(f"  SECTOR FLOW — {datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}")
    print(f"  Overall: Vol {flow.total_volume:,} | Premium {_format_prem(flow.total_premium)} | PCR {flow.overall_pcr}")
    print(f"{'='*130}")

    for sf in sorted(flow.sectors, key=lambda s: s.total_volume, reverse=True):
        if sf.total_volume < 1000:
            continue

        baseline = baselines.get(sf.sector, 0)
        vol_change = ""
        if baseline > 0:
            ratio = sf.total_volume / baseline
            vol_change = f" ({ratio:.1f}x avg)"

        print(f"\n  {sf.emoji} {sf.sector.upper()}{vol_change}")
        print(f"  {'─'*80}")

        # Volume & positioning
        cp_pct = round(sf.call_volume/sf.total_volume*100, 1) if sf.total_volume > 0 else 0
        pp_pct = round(sf.put_volume/sf.total_volume*100, 1) if sf.total_volume > 0 else 0
        print(f"  Volume:   Calls {sf.call_volume:>10,} ({cp_pct:.0f}%)  |  Puts {sf.put_volume:>10,} ({pp_pct:.0f}%)")
        print(f"  Open OI:  Calls {sf.call_oi:>10,}  |  Puts {sf.put_oi:>10,}")
        print(f"  PCR:      {sf.pcr_volume} (vol)  |  {sf.pcr_oi} (OI)")
        print(f"  Direction: {sf.flow_direction.upper()}  |  Strength: {sf.signal_strength}")

        # Premium split
        print(f"  Premium:  Calls {_format_prem(sf.call_premium):>10}  |  Puts {_format_prem(sf.put_premium):>10}  |  Total {_format_prem(sf.total_premium):>10}")

        # IV & skew
        iv_call = f"{sf.avg_call_iv:.1f}" if sf.avg_call_iv else "N/A"
        iv_put = f"{sf.avg_put_iv:.1f}" if sf.avg_put_iv else "N/A"
        iv_skew = f"{sf.iv_skew:+.1f}" if sf.iv_skew is not None else "N/A"
        misprice = f"{sf.avg_misprice_pct:+.1f}%" if sf.avg_misprice_pct is not None else "N/A"
        print(f"  IV:       Calls {iv_call:>6}%  |  Puts {iv_put:>6}%  |  Skew {iv_skew}  |  Misprice {misprice}")

        # Liquidity & flow structure
        spread = f"${sf.avg_bid_ask:.4f}" if sf.avg_bid_ask else "N/A"
        vol_oi = f"{sf.vol_oi_ratio:.2f}" if sf.vol_oi_ratio else "N/A"
        print(f"  Spread:   {spread}  |  Vol/OI {vol_oi}")

        # ATM vs OTM
        atm_pct = round(sf.atm_volume/sf.total_volume*100, 1) if sf.total_volume > 0 else 0
        otm_pct = round((sf.otm_call_volume+sf.otm_put_volume)/sf.total_volume*100, 1) if sf.total_volume > 0 else 0
        otm_c = sf.otm_call_volume
        otm_p = sf.otm_put_volume
        print(f"  ATM/OTM:  ATM {sf.atm_volume:>10,} ({atm_pct:.0f}%)  |  OTM {sf.otm_call_volume+sf.otm_put_volume:>10,} ({otm_pct:.0f}%)")
        print(f"            OTM Calls: {otm_c:>8,}  |  OTM Puts: {otm_p:>8,}")

        # Strike concentration
        top5 = ", ".join([f"${s:.0f}({v/1000:.0f}K)" for s, v in sf.top5_strikes[:5]])
        print(f"  Top 5:    {sf.top5_volume_pct:.0f}% of volume → {top5}")

        # DTE distribution
        near_pct = round(sf.near_term_vol/sf.total_volume*100, 1) if sf.total_volume > 0 else 0
        mid_pct = round(sf.mid_term_vol/sf.total_volume*100, 1) if sf.total_volume > 0 else 0
        far_pct = round(sf.far_term_vol/sf.total_volume*100, 1) if sf.total_volume > 0 else 0
        print(f"  DTE:      Near(0-7d) {sf.near_term_vol:>8,} ({near_pct:.0f}%)  |  Mid(8-30d) {sf.mid_term_vol:>8,} ({mid_pct:.0f}%)  |  Far(30d+) {sf.far_term_vol:>8,} ({far_pct:.0f}%)")


# ---------------------------------------------------------------------------
# Watchlist loader
# ---------------------------------------------------------------------------

def load_watchlist() -> list[dict]:
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
