#!/usr/bin/env python3
"""
Nightly Research Report -- Key Levels
======================================
Generates a concise levels-focused report for SPY, QQQ (+ IWM when available).
Pulls GEX/VEX/OI data from Desktop Postgres and VIX from Schwab API live.

Usage:
  python process/generate_nightly_report.py
  python process/generate_nightly_report.py -o reports/report_2026-05-02.txt
  python process/generate_nightly_report.py --json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ─── Configuration ──────────────────────────────────────────────

DESKTOP_HOST = "100.82.57.80"
DESKTOP_USER = "23and"
DESKTOP_PW = "Breeseheat1!"
DB_CONTAINER = "tos_options-db-1"
DB_USER = "trader"
DB_NAME = "options"

CT_OFFSET = timedelta(hours=-5)

TICKERS = {
    "SPY": {"label": "SPY", "strike_step": 1},
    "QQQ": {"label": "QQQ", "strike_step": 1},
    "IWM": {"label": "IWM", "strike_step": 1},
}


# ─── DB Query ───────────────────────────────────────────────────

def run_sql(sql: str) -> list[dict[str, Any]]:
    tmp = Path("/tmp/nightly_qry.sql")
    tmp.write_text(sql + "\n")
    cmd = (
        f"cat {tmp} | sshpass -p '{DESKTOP_PW}' ssh -o StrictHostKeyChecking=no "
        f"{DESKTOP_USER}@{DESKTOP_HOST} "
        f'"docker exec -i {DB_CONTAINER} psql -U {DB_USER} -d {DB_NAME} --csv"'
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    raw = result.stdout.strip()
    lines = raw.split("\n")
    lines = [l for l in lines if not l.startswith("**") and "not recognized" not in l and "operable program" not in l]
    if not lines:
        return []
    reader = csv.reader(io.StringIO("\n".join(lines)))
    rows_raw = list(reader)
    if len(rows_raw) < 2:
        return []
    header = rows_raw[0]
    return [dict(zip(header, vals)) for vals in rows_raw[1:] if len(vals) == len(header)]


# ─── Data Classes ───────────────────────────────────────────────

@dataclass
class Strike:
    strike: float
    net_gex: float = 0.0
    call_gex: float = 0.0
    put_gex: float = 0.0
    net_vex: float = 0.0
    net_dex: float = 0.0
    oi: int = 0
    volume: int = 0


# ─── Fetchers ───────────────────────────────────────────────────

def get_snapshot(symbol: str) -> dict | None:
    sym = symbol.replace("$", "\\$")
    rows = run_sql(f"""
        SELECT id, symbol, captured_at, underlying_price
        FROM snapshots WHERE symbol = '{sym}'
        ORDER BY captured_at DESC LIMIT 1;
    """)
    return rows[0] if rows else None


def get_prev_snapshot(symbol: str) -> dict | None:
    sym = symbol.replace("$", "\\$")
    rows = run_sql(f"""
        WITH today AS (
            SELECT DATE(MIN(captured_at)) AS d FROM snapshots
            WHERE symbol = '{sym}'
        )
        SELECT id, symbol, captured_at, underlying_price
        FROM snapshots WHERE symbol = '{sym}'
          AND DATE(captured_at) < (SELECT d FROM today)
        ORDER BY captured_at DESC LIMIT 1;
    """)
    return rows[0] if rows else None


def get_strikes(snapshot_id: int) -> list[Strike]:
    rows = run_sql(f"""
        SELECT strike, net_gex, call_gex, put_gex,
               net_vex, net_dex,
               open_interest_total, volume_total
        FROM aggregates_by_strike
        WHERE snapshot_id = {snapshot_id}
        ORDER BY strike;
    """)
    return [Strike(
        strike=float(r.get("strike", 0)),
        net_gex=float(r.get("net_gex", 0)),
        call_gex=float(r.get("call_gex", 0)),
        put_gex=float(r.get("put_gex", 0)),
        net_vex=float(r.get("net_vex", 0)),
        net_dex=float(r.get("net_dex", 0)),
        oi=int(float(r.get("open_interest_total", 0) or 0)),
        volume=int(float(r.get("volume_total", 0) or 0)),
    ) for r in rows]


def get_totals(snapshot_id: int) -> dict[str, float]:
    rows = run_sql(f"""
        SELECT
            ROUND(CAST(SUM(net_gex) as numeric), 0) as net_gex,
            ROUND(CAST(SUM(call_gex) as numeric), 0) as call_gex,
            ROUND(CAST(ABS(SUM(put_gex)) as numeric), 0) as put_gex,
            ROUND(CAST(SUM(net_vex) as numeric), 0) as net_vex,
            ROUND(CAST(SUM(net_dex) as numeric), 0) as net_dex,
            ROUND(CAST(SUM(open_interest_total) as numeric), 0) as total_oi
        FROM aggregates_by_strike WHERE snapshot_id = {snapshot_id};
    """)
    return {k: float(v) if v else 0.0 for k, v in rows[0].items()} if rows else {}


def get_vix() -> float | None:
    """Fetch latest VIX level from Schwab API live via a temp script file."""
    script_path = Path("/tmp/_fetch_vix.py")
    if not script_path.exists():
        script_path.write_text(
            "import sys,json\n"
            "sys.path.insert(0,'/Users/arivera/projects/tos_options')\n"
            "from schwab.client import create_client\n"
            "c=create_client()\n"
            "r=c.quote('$VIX')\n"
            "d=r.json().get('$VIX',{})\n"
            "q=d.get('quote',{})\n"
            "print(json.dumps({'last':q.get('lastPrice'),'close':q.get('closePrice'),"
            "'high':q.get('highPrice'),'low':q.get('lowPrice')}))\n"
        )
    try:
        result = subprocess.run(
            ["/Users/arivera/projects/tos_options/.venv/bin/python", str(script_path)],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            return float(data["last"]) if data.get("last") else None
    except Exception:
        pass
    return None


# ─── Formatting Helpers ─────────────────────────────────────────

def B(val: float) -> str:
    """Format as billions, e.g. +93.0B or -80.4B"""
    if abs(val) >= 1e9:
        return f"{val/1e9:+.1f}B"
    elif abs(val) >= 1e6:
        return f"{val/1e6:+.0f}M"
    return f"{val:+,.0f}"


def M(val: float) -> str:
    """Format as millions for VEX"""
    if abs(val) >= 1e6:
        return f"{val/1e6:+.1f}M"
    return f"{val:+,.0f}"


def pct(dist: float) -> str:
    if abs(dist) < 0.05:
        return "ATM"
    return f"{dist:+.1f}%"


# ─── Level Extraction ───────────────────────────────────────────

def find_levels(strikes: list[Strike], spot: float) -> dict[str, Any]:
    """Extract the key levels a trader cares about."""
    sorted_s = sorted(strikes, key=lambda s: s.strike)

    # Call walls: strikes above spot with highest call GEX (resistance)
    above = [s for s in sorted_s if s.strike >= spot]
    call_walls = sorted(above, key=lambda s: s.call_gex, reverse=True)[:5]

    # Put walls: strikes below spot with highest |put GEX| (support)
    below = [s for s in sorted_s if s.strike <= spot]
    put_walls = sorted(below, key=lambda s: abs(s.put_gex), reverse=True)[:5]

    # GEX flips (zero crossings)
    flips = []
    for i in range(1, len(sorted_s)):
        prev, curr = sorted_s[i-1], sorted_s[i]
        if (prev.net_gex < 0 and curr.net_gex >= 0):
            flips.append({"strike": prev.strike, "to": "LONG", "below": prev.net_gex, "above": curr.net_gex, "note": "support"})
        elif (prev.net_gex >= 0 and curr.net_gex < 0):
            flips.append({"strike": curr.strike, "to": "SHORT", "below": prev.net_gex, "above": curr.net_gex, "note": "accelerant"})

    # Short gamma zones (biggest negative GEX within 3% of spot)
    near = [s for s in sorted_s if abs((s.strike - spot) / spot * 100) <= 3.0]
    short_gamma = sorted([s for s in near if s.net_gex < 0], key=lambda s: s.net_gex)[:5]

    # Biggest OI strikes (pinning magnets)
    oi_top = sorted(sorted_s, key=lambda s: s.oi, reverse=True)[:5]

    return {
        "call_walls": call_walls,
        "put_walls": put_walls,
        "flips": flips,
        "short_gamma": short_gamma,
        "oi_top": oi_top,
    }


# ─── Report ─────────────────────────────────────────────────────

def generate_ticker_block(
    symbol: str, snap: dict, strikes: list[Strike],
    prev_snap: dict | None = None, prev_totals: dict | None = None,
) -> str:
    spot = float(snap.get("underlying_price", 0))
    snap_id = int(snap.get("id", 0))
    totals = get_totals(snap_id)
    levels = find_levels(strikes, spot)

    # Parse time
    try:
        dt = datetime.fromisoformat(snap["captured_at"]).replace(tzinfo=timezone.utc)
        ct = dt.astimezone(timezone(CT_OFFSET))
        time_str = ct.strftime("%a %b %d %I:%M %p CT")
    except Exception:
        time_str = snap.get("captured_at", "")

    net_gex = totals.get("net_gex", 0)
    regime = "LONG GAMMA" if net_gex > 0 else "SHORT GAMMA"

    lines = []
    lines.append(f"  {symbol}  {spot:.2f}  ({time_str})")
    lines.append(f"  Regime: {regime}  Net GEX: {B(net_gex)}  VEX: {M(totals.get('net_vex', 0))}  OI: {totals.get('total_oi', 0):,.0f}")
    lines.append("")

    # Day-over-day
    if prev_snap and prev_totals:
        prev_spot = float(prev_snap.get("underlying_price", 0))
        prev_gex = prev_totals.get("net_gex", 0)
        chg = (spot - prev_spot) / prev_spot * 100
        gex_chg = net_gex - prev_gex
        lines.append(f"  DoD:  {prev_spot:.2f} -> {spot:.2f} ({chg:+.2f}%)  GEX: {B(prev_gex)} -> {B(net_gex)} ({B(gex_chg)})")
        lines.append("")

    # Call walls (resistance above)
    lines.append("  RESISTANCE (call walls above)")
    lines.append("  " + "-" * 55)
    for w in levels["call_walls"]:
        d = (w.strike - spot) / spot * 100
        lines.append(f"    {w.strike:>7.1f}  ({pct(d):>6s})  Call GEX: {B(w.call_gex):>8s}  OI: {w.oi:>7,}")
    lines.append("")

    # Put walls (support below)
    lines.append("  SUPPORT (put walls below)")
    lines.append("  " + "-" * 55)
    for w in levels["put_walls"]:
        d = (w.strike - spot) / spot * 100
        lines.append(f"    {w.strike:>7.1f}  ({pct(d):>6s})  Put GEX:  {B(abs(w.put_gex)):>8s}  OI: {w.oi:>7,}")
    lines.append("")

    # GEX flips
    if levels["flips"]:
        lines.append("  GEX FLIPS (dealer behavior shifts)")
        lines.append("  " + "-" * 55)
        for f in levels["flips"]:
            d = (f["strike"] - spot) / spot * 100
            arrow = "-> LONG (support)" if f["to"] == "LONG" else "-> SHORT (accelerant)"
            lines.append(f"    {f['strike']:>7.1f}  ({pct(d):>6s})  {arrow}")
        lines.append("")

    # Short gamma danger zones
    if levels["short_gamma"]:
        lines.append("  SHORT GAMMA DANGER (price trades through = acceleration)")
        lines.append("  " + "-" * 55)
        for s in levels["short_gamma"]:
            d = (s.strike - spot) / spot * 100
            lines.append(f"    {s.strike:>7.1f}  ({pct(d):>6s})  Net GEX: {B(s.net_gex):>8s}  OI: {s.oi:>7,}")
        lines.append("")

    # OI magnets (pinning)
    lines.append("  OI MAGNETS (pinning risk at expiry)")
    lines.append("  " + "-" * 55)
    for o in levels["oi_top"]:
        d = (o.strike - spot) / spot * 100
        lines.append(f"    {o.strike:>7.1f}  ({pct(d):>6s})  OI: {o.oi:>7,}  Net GEX: {B(o.net_gex):>8s}")
    lines.append("")

    return "\n".join(lines)


def generate_report(symbols: list[str] | None = None, json_output: bool = False) -> str:
    target = symbols or ["SPY", "QQQ"]
    now_ct = datetime.now(timezone(timedelta(hours=-5)))

    if json_output:
        data = {"report_time": now_ct.isoformat(), "tickers": {}}
        vix = get_vix()
        if vix:
            data["vix"] = vix
        for sym in target:
            snap = get_snapshot(sym)
            if not snap:
                data["tickers"][sym] = {"error": "no data"}
                continue
            strikes = get_strikes(int(snap["id"]))
            spot = float(snap.get("underlying_price", 0))
            levels = find_levels(strikes, spot)
            data["tickers"][sym] = {
                "spot": spot,
                "snapshot": snap.get("captured_at", ""),
                "totals": get_totals(int(snap["id"])),
                "levels": {
                    "call_walls": [{"strike": s.strike, "call_gex": s.call_gex, "oi": s.oi} for s in levels["call_walls"]],
                    "put_walls": [{"strike": s.strike, "put_gex": s.put_gex, "oi": s.oi} for s in levels["put_walls"]],
                    "flips": levels["flips"],
                    "short_gamma": [{"strike": s.strike, "net_gex": s.net_gex, "oi": s.oi} for s in levels["short_gamma"]],
                    "oi_top": [{"strike": s.strike, "oi": s.oi, "net_gex": s.net_gex} for s in levels["oi_top"]],
                },
            }
        return json.dumps(data, indent=2, default=str)

    lines = []
    lines.append(f"  NIGHTLY LEVELS  {now_ct.strftime('%a %b %d %Y %I:%M %p CT')}")
    lines.append("")

    # VIX
    vix = get_vix()
    if vix:
        if vix < 15:
            regime = "LOW -- complacent, tight ranges"
        elif vix < 20:
            regime = "NORMAL -- good for premium selling"
        elif vix < 30:
            regime = "ELEVATED -- wider ranges, more risk"
        else:
            regime = "HIGH FEAR -- consider sitting out"
        lines.append(f"  VIX: {vix:.2f}  {regime}")
    else:
        lines.append("  VIX: unavailable")
    lines.append("")

    for sym in target:
        snap = get_snapshot(sym)
        if not snap:
            lines.append(f"  {sym}: no data in DB")
            lines.append("")
            continue
        strikes = get_strikes(int(snap["id"]))
        prev_snap = get_prev_snapshot(sym)
        prev_totals = get_totals(int(prev_snap["id"])) if prev_snap else None
        lines.append(generate_ticker_block(sym, snap, strikes, prev_snap, prev_totals))

    return "\n".join(lines)


# ─── CLI ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Nightly key levels report")
    parser.add_argument("--symbols", default="SPY,QQQ", help="Comma-separated (default: SPY,QQQ)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output file")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    report = generate_report(symbols=symbols, json_output=args.json)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(f"Written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
