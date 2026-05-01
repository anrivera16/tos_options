"""
Live 0DTE/1DTE Options Scanner
==============================
Reads the latest option chain snapshot from Postgres, runs scanner filters,
and alerts to Discord when setups are found.

Runs every 5 minutes during market hours (Mon-Fri 9:35 AM - 3:30 PM ET).

Usage:
    # One-shot scan
    python scripts/live_scanner.py --once

    # Continuous (5 min intervals)
    python scripts/live_scanner.py --interval 5

    # Continuous + Discord alerts
    python scripts/live_scanner.py --interval 5 --discord

    # Specific tickers only
    python scripts/live_scanner.py --once --tickers SPY QQQ
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime
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
# Scanner filters
# ---------------------------------------------------------------------------

@dataclass
class ScannerHit:
    """One contract that passed a scanner filter."""
    scanner_name: str
    symbol: str
    underlying_price: float
    strike: float
    put_call: str
    dte: int
    delta: float
    theta: float | None
    vega: float | None
    iv: float | None
    bid: float | None
    ask: float | None
    mark: float | None
    volume: int | None
    open_interest: int | None
    dist_otm: float
    credit_est: float
    score: float
    # Tier 1: new features
    percent_change: float | None
    theoretical_value: float | None
    time_value: float | None
    intrinsic_value: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanner": self.scanner_name,
            "symbol": self.symbol,
            "underlying": self.underlying_price,
            "strike": self.strike,
            "put_call": self.put_call,
            "dte": self.dte,
            "delta": self.delta,
            "theta": self.theta,
            "vega": self.vega,
            "iv": self.iv,
            "bid": self.bid,
            "ask": self.ask,
            "mark": self.mark,
            "volume": self.volume,
            "oi": self.open_interest,
            "dist_otm": self.dist_otm,
            "credit_est": self.credit_est,
            "score": self.score,
            "percent_change": self.percent_change,
            "theoretical_value": self.theoretical_value,
            "time_value": self.time_value,
            "intrinsic_value": self.intrinsic_value,
        }


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# SCANNER DEFINITIONS
# Each returns list of hits from a set of contract rows.

SCANNERS = {
    "0DTE_PUT_CREDIT": {
        "description": "0DTE Put Credit Spread candidates",
        "dte": [0],
        "put_call": "PUT",
        "delta_min": 0.08,
        "delta_max": 0.25,
        "iv_min": 15,
        "volume_min": 300,
        "oi_min": 500,
        "otm": True,
    },
    "0DTE_CALL_CREDIT": {
        "description": "0DTE Call Credit Spread candidates",
        "dte": [0],
        "put_call": "CALL",
        "delta_min": 0.08,
        "delta_max": 0.25,
        "iv_min": 15,
        "volume_min": 300,
        "oi_min": 500,
        "otm": True,
    },
    "0DTE_IRON_CONDOR": {
        "description": "0DTE Iron Condor (both sides)",
        "dte": [0],
        "put_call": "BOTH",
        "delta_min": 0.08,
        "delta_max": 0.20,
        "iv_min": 15,
        "volume_min": 200,
        "oi_min": 500,
        "otm": True,
    },
    "1DTE_MOMENTUM_CALL": {
        "description": "1DTE directional call breakout",
        "dte": [1],
        "put_call": "CALL",
        "delta_min": 0.30,
        "delta_max": 0.55,
        "iv_min": 20,
        "volume_min": 500,
        "oi_min": 1000,
        "otm": True,
    },
    "1DTE_MOMENTUM_PUT": {
        "description": "1DTE directional put breakout",
        "dte": [1],
        "put_call": "PUT",
        "delta_min": 0.30,
        "delta_max": 0.55,
        "iv_min": 20,
        "volume_min": 500,
        "oi_min": 1000,
        "otm": True,
    },
    "HIGH_IV_SELL": {
        "description": "High IV credit sellers dream (0-1 DTE)",
        "dte": [0, 1],
        "put_call": "BOTH",
        "delta_min": 0.08,
        "delta_max": 0.20,
        "iv_min": 30,
        "volume_min": 200,
        "oi_min": 500,
        "otm": True,
    },
}


def run_scanner(conn, scanner_name: str, config: dict, tickers: list[str] | None = None) -> list[ScannerHit]:
    """Run one scanner filter against the latest snapshot."""
    pg = is_postgres(get_db_url())
    placeholder = "%s" if pg else "?"

    dte_list = config["dte"]
    dte_placeholders = ", ".join(placeholder for _ in dte_list)

    ticker_clause = ""
    ticker_params: list = []
    if tickers:
        ticker_placeholders = ", ".join(placeholder for _ in tickers)
        ticker_clause = f"AND oc.underlying_symbol IN ({ticker_placeholders})"
        ticker_params = list(tickers)

    # Build put_call filter
    pc_clause = ""
    pc_params: list = []
    if config["put_call"] == "BOTH":
        pc_clause = f"AND oc.put_call IN ({placeholder}, {placeholder})"
        pc_params = ["CALL", "PUT"]
    else:
        pc_clause = f"AND oc.put_call = {placeholder}"
        pc_params = [config["put_call"]]

    # Get the latest snapshot PER TICKER (not just the single latest overall)
    # This way if $SPX was scraped at 10:30 and SPY at 10:31, both are included
    if pg:
        subq = """
            SELECT id FROM snapshots s1
            WHERE captured_at >= NOW() - INTERVAL '20 minutes'
            AND captured_at = (
                SELECT MAX(s2.captured_at) 
                FROM snapshots s2 
                WHERE s2.symbol = s1.symbol
            )
        """
    else:
        subq = """
            SELECT id FROM snapshots s1
            WHERE captured_at >= datetime('now', '-20 minutes')
            AND captured_at = (
                SELECT MAX(s2.captured_at) 
                FROM snapshots s2 
                WHERE s2.symbol = s1.symbol
            )
        """

    query = f"""
        SELECT 
            oc.underlying_symbol,
            s.underlying_price,
            oc.strike,
            oc.put_call,
            oc.dte,
            oc.delta,
            oc.theta,
            oc.vega,
            oc.volatility,
            oc.bid,
            oc.ask,
            oc.mark,
            oc.total_volume,
            oc.open_interest,
            oc.percent_change,
            oc.theoretical_option_value,
            oc.time_value,
            oc.intrinsic_value
        FROM option_contracts oc
        JOIN snapshots s ON oc.snapshot_id = s.id
        WHERE s.id IN ({subq})
        AND oc.dte IN ({dte_placeholders})
        {pc_clause}
        AND oc.delta IS NOT NULL
        AND ABS(oc.delta) BETWEEN {config['delta_min']} AND {config['delta_max']}
        AND oc.volatility >= {config['iv_min']}
        AND oc.total_volume >= {config['volume_min']}
        AND oc.open_interest >= {config['oi_min']}
        {ticker_clause}
        ORDER BY ABS(oc.delta) ASC
    """

    params = list(dte_list) + pc_params + ticker_params

    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()

    hits: list[ScannerHit] = []
    for row in rows:
        sym, underlying, strike, pc, dte, delta, theta, vega, iv, bid, ask, mark, vol, oi, pct_chg, theo_val, t_val, i_val = row
        underlying = float(underlying) if underlying else 0
        strike = float(strike) if strike else 0
        delta = float(delta) if delta else 0
        abs_delta = abs(delta)

        # OTM check
        if config.get("otm"):
            if pc == "PUT" and strike >= underlying:
                continue
            if pc == "CALL" and strike <= underlying:
                continue

        dist_otm = abs(underlying - strike)

        # Credit estimate: ~65% of mark for a 5pt spread
        mark_f = _safe_float(mark) or 0
        credit_est = round(mark_f * 0.65, 2)

        # Score: higher delta = more premium but more risk
        # Score = premium richness * liquidity
        oi_i = _safe_int(oi) or 0
        vol_i = _safe_int(vol) or 0
        oi_norm = min(max((math.log10(max(oi_i, 1)) - 2) / 2, 0), 1)
        delta_norm = abs_delta / 0.25  # 0.25 delta = 1.0
        score = round(credit_est * (1 + oi_norm) * (1 + delta_norm), 2)

        hits.append(ScannerHit(
            scanner_name=scanner_name,
            symbol=sym or "???",
            underlying_price=round(underlying, 2),
            strike=round(strike, 1),
            put_call=pc,
            dte=int(dte) if dte is not None else 0,
            delta=round(abs_delta, 3),
            theta=_safe_float(theta),
            vega=_safe_float(vega),
            iv=_safe_float(iv),
            bid=_safe_float(bid),
            ask=_safe_float(ask),
            mark=_safe_float(mark),
            volume=vol_i,
            open_interest=oi_i,
            dist_otm=round(dist_otm, 1),
            credit_est=credit_est,
            score=score,
            # Tier 1
            percent_change=_safe_float(pct_chg),
            theoretical_value=_safe_float(theo_val),
            time_value=_safe_float(t_val),
            intrinsic_value=_safe_float(i_val),
        ))

    return hits


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def format_hits(hits: list[ScannerHit], scanner_name: str) -> str:
    """Format hits as ASCII table for terminal."""
    if not hits:
        return f"  {scanner_name}: no hits"

    lines = []
    lines.append(f"")
    lines.append(f"  {scanner_name} — {len(hits)} hits")
    lines.append(f"  {'=' * 85}")
    lines.append(
        f"  {'Sym':<5} {'PC':<4} {'Strike':>7} {'Spot':>7} {'DTE':>3} "
        f"{'Delta':>5} {'Theta':>6} {'IV':>5} {'Mark':>6} "
        f"{'Vol':>7} {'OI':>7} {'Dist':>6} {'Cred':>5} {'Score':>5}"
    )
    lines.append(f"  {'-' * 85}")

    for h in hits[:10]:
        theta_str = f"{h.theta:.3f}" if h.theta is not None else "   n/a"
        iv_str = f"{h.iv:.1f}" if h.iv is not None else "  n/a"
        lines.append(
            f"  {h.symbol:<5} {h.put_call:<4} {h.strike:>7.1f} {h.underlying_price:>7.1f} {h.dte:>3} "
            f"{h.delta:>5.3f} {theta_str:>6} {iv_str:>5} {h.mark or 0:>6.2f} "
            f"{h.volume or 0:>7,} {h.open_interest or 0:>7,} {h.dist_otm:>6.1f} {h.credit_est:>5.2f} {h.score:>5.2f}"
        )

    lines.append(f"  {'-' * 85}")
    return "\n".join(lines)


def format_discord_message(all_hits: dict[str, list[ScannerHit]], now_str: str) -> str:
    """Format hits for Discord (compact, fits 2000 chars)."""
    lines = []
    total = sum(len(h) for h in all_hits.values())
    scanners_with_hits = sum(1 for h in all_hits.values() if h)
    lines.append(f"**Scanner** {now_str} | **{total}** hits across **{scanners_with_hits}** filters")
    lines.append("```")

    for scanner_name, hits in all_hits.items():
        if not hits:
            continue
        # Shorten scanner names for display
        short_name = scanner_name.replace("0DTE_", "0d_").replace("1DTE_", "1d_")
        lines.append(f"[{short_name}] {len(hits)} hit{'s' if len(hits) > 1 else ''}")
        lines.append(
            f"{'Sym':<5} {'P/C':<3} {'Strk':>6} {'DTE':>3} {'Δ':>4} "
            f"{'IV':>4} {'$':>5} {'Δ%':>5} {'MisP':>4} {'OI':>6}"
        )

        for h in hits[:5]:
            iv_str = f"{h.iv:.0f}" if h.iv is not None else " - "
            # Premium momentum: show % change direction
            if h.percent_change is not None:
                pct = h.percent_change
                if pct > 0:
                    pct_str = f"+{pct:.0f}"
                else:
                    pct_str = f"{pct:.0f}"
            else:
                pct_str = "  - "
            # Mispricing: how far mark deviates from theoretical
            if h.theoretical_value is not None and h.mark is not None and h.theoretical_value > 0:
                mispct = ((h.mark - h.theoretical_value) / h.theoretical_value) * 100
                if mispct > 5:
                    misp_str = "EXP "
                elif mispct < -5:
                    misp_str = "CHP "
                else:
                    misp_str = "  = "
            else:
                misp_str = "  - "

            lines.append(
                f"{h.symbol:<5} {h.put_call[:1]:<3} {h.strike:>6.0f} {h.dte:>3} "
                f"{h.delta:>4.2f} {iv_str:>4} {h.mark or 0:>5.2f} {pct_str:>5} "
                f"{misp_str} {h.open_interest or 0:>6,}"
            )
        lines.append("")

    lines.append("```")
    lines.append("_Δ%=premium change | MisP: EXP=expensive CHP=cheap =fair_")

    msg = "\n".join(lines)
    if len(msg) > 1900:
        msg = msg[:1890] + "\n...truncated```"
    return msg


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_scan(
    tickers: list[str] | None = None,
    discord: bool = False,
) -> None:
    """Run all scanners against the latest snapshot. Returns hits keyed by scanner name."""
    db_url = get_db_url()
    conn = get_connection(db_url)

    try:
        all_hits: dict[str, list[ScannerHit]] = {}
        for scanner_name, config in SCANNERS.items():
            hits = run_scanner(conn, scanner_name, config, tickers=tickers)
            all_hits[scanner_name] = hits

        now_str = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
        total = sum(len(h) for h in all_hits.values())

        print(f"\n{'#' * 70}")
        print(f"  SCANNER RESULTS — {now_str}")
        print(f"  Total hits: {total}")
        print(f"{'#' * 70}")

        for scanner_name, hits in all_hits.items():
            print(format_hits(hits, scanner_name))

        print()

        if discord and total > 0:
            try:
                from discord.webhook import send_message
                msg = format_discord_message(all_hits, now_str)
                send_message(msg)
                logger.info(f"Discord alert sent ({total} hits)")
            except Exception as exc:
                logger.warning(f"Discord alert failed: {exc}")

        return all_hits

    finally:
        conn.close()


def run_scan_cycle(tickers: list[str] | None, discord: bool) -> None:
    if not is_market_hours():
        logger.debug("Outside market hours, skipping scan")
        return
    run_scan(tickers=tickers, discord=discord)


def start_scheduler(interval_minutes: int = 5, tickers: list[str] | None = None, discord: bool = False) -> None:
    logger.info(
        f"Starting live scanner | interval={interval_minutes}m | "
        f"tickers={tickers or 'all'} | discord={discord}"
    )

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
        args=[tickers, discord],
        id="live_scanner",
        max_instances=1,
        misfire_grace_time=120,
    )

    # Heartbeat zombie detector
    from scripts.shared import send_heartbeat_alert, send_token_alert
    heartbeat_trigger = CronTrigger(
        day_of_week="mon-fri",
        hour="4-19",
        minute="*/5",
        timezone=ET,
    )
    scheduler.add_job(
        send_heartbeat_alert,
        heartbeat_trigger,
        id="heartbeat_check",
        max_instances=1,
        misfire_grace_time=300,
    )

    # Token expiry alert — twice daily
    token_trigger = CronTrigger(
        day_of_week="mon-fri",
        hour="8,14",
        minute="0",
        timezone=ET,
    )
    scheduler.add_job(
        send_token_alert,
        token_trigger,
        id="token_expiry_check",
        max_instances=1,
        misfire_grace_time=3600,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down scanner...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scanner stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live 0DTE/1DTE options scanner")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    parser.add_argument("--interval", type=int, default=5, help="Minutes between scans (default: 5)")
    parser.add_argument("--tickers", nargs="+", default=None, help="Filter to specific tickers")
    parser.add_argument("--discord", action="store_true", help="Send alerts to Discord")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.once:
        hits = run_scan(tickers=args.tickers, discord=args.discord)
        if args.json:
            import json
            out = {}
            for name, h_list in hits.items():
                out[name] = [h.to_dict() for h in h_list]
            print(json.dumps(out, indent=2))
    else:
        start_scheduler(interval_minutes=args.interval, tickers=args.tickers, discord=args.discord)
