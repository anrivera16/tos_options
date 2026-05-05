"""
Nightly Scan — End-of-Day Options Scanner & Gameplan Generator
===============================================================
Runs after market close. Queries the LAST EOD snapshot (not the 20-min
live window), builds spread candidates, enriches with IV rank + trend,
gets VIX context, and writes a gameplan file.

Usage:
    conda run python scripts/nightly_scan.py              # full scan + gameplan
    conda run python scripts/nightly_scan.py --top 3       # compact view
    conda run python scripts/nightly_scan.py --tickers SPY QQQ  # specific symbols
    conda run python scripts/nightly_scan.py --no-gameplan  # skip gameplan file
    conda run python scripts/nightly_scan.py --gex          # include GEX walls (Phase 3)
    conda run python scripts/nightly_scan.py --discord       # post to Discord
"""

from __future__ import annotations

import argparse
import os
import sys
import csv
import io
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()

ET = ZoneInfo("US/Eastern")
CT = ZoneInfo("America/Chicago")

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    return os.environ.get("SQLITE_PATH", "out/options_history.sqlite3")


def is_postgres(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgres://")


def get_connection(url: str):
    if is_postgres(url):
        import psycopg
        return psycopg.connect(url)
    import sqlite3
    return sqlite3.connect(url)


def ph(url: str) -> str:
    return "%s" if is_postgres(url) else "?"


# ---------------------------------------------------------------------------
# Health check — verify EOD data exists
# ---------------------------------------------------------------------------

def check_eod_data(conn) -> dict:
    """Check that we have today's EOD snapshots. Returns status dict."""
    pg = is_postgres(get_db_url())
    cur = conn.cursor()

    if pg:
        cur.execute("""
            SELECT symbol, COUNT(*), MAX(captured_at),
                   MIN(captured_at),
                   (SELECT MAX(captured_at) FROM snapshots) as global_max
            FROM snapshots
            GROUP BY symbol
            ORDER BY symbol
        """)
    else:
        cur.execute("""
            SELECT symbol, COUNT(*), MAX(captured_at),
                   MIN(captured_at),
                   (SELECT MAX(captured_at) FROM snapshots)
            FROM snapshots
            GROUP BY symbol
            ORDER BY symbol
        """)

    rows = cur.fetchall()
    symbols = {}
    for row in rows:
        sym, cnt, latest, earliest, global_max = row
        symbols[sym] = {
            "count": cnt,
            "latest": str(latest)[:19] if latest else "?",
            "earliest": str(earliest)[:19] if earliest else "?",
        }

    # Total contracts
    cur.execute("SELECT COUNT(*) FROM option_contracts")
    total_contracts = cur.fetchone()[0]

    # Global latest snapshot
    cur.execute("SELECT MAX(captured_at) FROM snapshots")
    global_max = cur.fetchone()[0]
    if global_max:
        if isinstance(global_max, str):
            global_max = datetime.fromisoformat(global_max)
        if global_max.tzinfo is None:
            global_max = global_max.replace(tzinfo=ET)
        age_hours = (datetime.now(ET) - global_max).total_seconds() / 3600
    else:
        age_hours = 999

    return {
        "symbols": symbols,
        "total_contracts": total_contracts,
        "latest_snapshot_age_hours": round(age_hours, 1),
        "latest_snapshot_time": str(global_max)[:19] if global_max else "none",
    }


# ---------------------------------------------------------------------------
# Get latest snapshot IDs for given symbols (EOD, not 20-min)
# ---------------------------------------------------------------------------

def get_latest_snapshots(conn, tickers: list[str] | None = None) -> list[tuple]:
    """Get the most recent snapshot per symbol. Returns list of (id, symbol, price, captured_at)."""
    pg = is_postgres(get_db_url())
    cur = conn.cursor()

    if pg:
        query = """
            SELECT DISTINCT ON (symbol) id, symbol, underlying_price, captured_at
            FROM snapshots
            WHERE symbol IN ('SPY', 'QQQ', '$SPX')
            ORDER BY symbol, captured_at DESC
        """
        if tickers:
            # Use WHERE with any clause
            placeholders = ", ".join(["%s"] * len(tickers))
            query = f"""
                SELECT DISTINCT ON (symbol) id, symbol, underlying_price, captured_at
                FROM snapshots
                WHERE symbol IN ({placeholders})
                ORDER BY symbol, captured_at DESC
            """
            cur.execute(query, tickers)
        else:
            cur.execute(query)
    else:
        # SQLite: no DISTINCT ON, use subquery
        base = """
            SELECT s.id, s.symbol, s.underlying_price, s.captured_at
            FROM snapshots s
            INNER JOIN (
                SELECT symbol, MAX(captured_at) as max_ts
                FROM snapshots
                WHERE symbol IN ('SPY', 'QQQ', '$SPX')
                GROUP BY symbol
            ) latest ON s.symbol = latest.symbol AND s.captured_at = latest.max_ts
            ORDER BY s.symbol
        """
        if tickers:
            placeholders = ", ".join(["?"] * len(tickers))
            query = f"""
                SELECT s.id, s.symbol, s.underlying_price, s.captured_at
                FROM snapshots s
                INNER JOIN (
                    SELECT symbol, MAX(captured_at) as max_ts
                    FROM snapshots
                    WHERE symbol IN ({placeholders})
                    GROUP BY symbol
                ) latest ON s.symbol = latest.symbol AND s.captured_at = latest.max_ts
                ORDER BY s.symbol
            """
            cur.execute(query, tickers)
        else:
            cur.execute(base)

    return cur.fetchall()


# ---------------------------------------------------------------------------
# Fetch contracts from a snapshot and build spreads
# ---------------------------------------------------------------------------

@dataclass
class TradeIdea:
    symbol: str
    spread_type: str  # "bull_put", "bear_call"
    expiration: str
    dte: int
    short_strike: float
    short_oco: str
    short_bid: float
    short_ask: float
    short_delta: float
    long_strike: float
    long_oco: str
    long_bid: float
    long_ask: float
    long_delta: float
    net_credit: float
    max_loss: float
    roi_pct: float
    breakeven: float
    score: float
    iv_rank: float
    trend: str
    spot_price: float
    reason: str


def make_occ_symbol(symbol: str, exp_date: str, put_call: str, strike: float) -> str:
    """Generate OCC symbol for TOS entry."""
    if len(exp_date) >= 10:
        mm = exp_date[5:7]
        dd = exp_date[8:10]
        yy = exp_date[2:4]
        date_part = f"{mm}{dd}{yy}"
    else:
        date_part = exp_date.replace("-", "")[:6]
    strike_int = int(strike * 1000)
    strike_part = f"{strike_int:08d}"
    pc = "C" if put_call.upper() == "CALL" else "P"
    return f"{symbol.upper()}_{date_part}{pc}{strike_part}"


def build_spreads_from_snapshot(conn, snap_id: int, symbol: str, spot: float,
                                 dte_min: int = 5, dte_max: int = 14) -> list[TradeIdea]:
    """Build bull put + bear call spreads from a single snapshot."""
    pg = is_postgres(get_db_url())
    p = ph(get_db_url())
    cur = conn.cursor()

    # Check if theoretical_option_value column exists
    try:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'option_contracts' AND column_name = 'theoretical_option_value'
        """)
        has_theo = cur.fetchone() is not None
    except Exception:
        has_theo = False

    theo_col = "theoretical_option_value" if has_theo else "0 AS theo"

    # Fetch all contracts with greeks from this snapshot
    cur.execute(f"""
        SELECT strike, put_call, dte, expiration_date,
               delta, theta, bid, ask, mark,
               total_volume, open_interest, {theo_col}
        FROM option_contracts
        WHERE snapshot_id = {p}
        AND delta IS NOT NULL
        AND dte BETWEEN {p} AND {p}
        AND total_volume >= 50
        AND open_interest >= 100
        ORDER BY strike
    """, (snap_id, dte_min, dte_max))

    rows = cur.fetchall()
    puts = []
    calls = []

    for row in rows:
        contract = {
            "strike": float(row[0]), "dte": int(row[2]), "exp": row[3] or "",
            "delta": float(row[4]) if row[4] else 0,
            "theta": float(row[5]) if row[5] else 0,
            "bid": float(row[6]) if row[6] else 0,
            "ask": float(row[7]) if row[7] else 0,
            "mark": float(row[8]) if row[8] else 0,
            "vol": int(row[9]) if row[9] else 0,
            "oi": int(row[10]) if row[10] else 0,
        }
        if row[1] == "PUT":
            puts.append(contract)
        else:
            calls.append(contract)

    trades = []

    # Bull put spreads: short put OTM (strike < spot), delta 0.08-0.25
    otm_puts = [p for p in puts if p["strike"] < spot and 0.08 <= abs(p["delta"]) <= 0.25]

    for short_put in otm_puts:
        # Long leg: closest strike below
        longs = [p for p in otm_puts if p["strike"] < short_put["strike"]]
        if not longs:
            continue
        # Pick the long leg that gives us ~$2-$10 width
        best_long = None
        best_width = 0
        for lng in longs:
            w = short_put["strike"] - lng["strike"]
            if 2 <= w <= 10:
                if best_long is None or w < best_width:
                    best_long = lng
                    best_width = w
        if not best_long:
            continue

        width = short_put["strike"] - best_long["strike"]
        credit = short_put["ask"] - best_long["bid"]
        if credit <= 0.05:
            continue

        max_loss = width - credit
        if max_loss <= 0:
            continue

        roi = (credit / max_loss) * 100
        be = short_put["strike"] - credit

        exp = best_long["exp"][:10] if len(best_long["exp"]) >= 10 else best_long["exp"]
        occ_short = make_occ_symbol(symbol, exp, "PUT", short_put["strike"])
        occ_long = make_occ_symbol(symbol, exp, "PUT", best_long["strike"])

        trades.append(TradeIdea(
            symbol=symbol, spread_type="bull_put", expiration=exp,
            dte=short_put["dte"],
            short_strike=short_put["strike"], short_oco=occ_short,
            short_bid=short_put["bid"], short_ask=short_put["ask"],
            short_delta=short_put["delta"],
            long_strike=best_long["strike"], long_oco=occ_long,
            long_bid=best_long["bid"], long_ask=best_long["ask"],
            long_delta=best_long["delta"],
            net_credit=round(credit, 2), max_loss=round(max_loss, 2),
            roi_pct=round(roi, 1), breakeven=round(be, 2),
            score=round(roi * abs(short_put["delta"]) * 10, 2),
            spot_price=spot, iv_rank=0, trend="NEUTRAL",
            reason=f"OTM put credit, {width:.0f} wide, delta {abs(short_put['delta']):.2f}",
        ))

    # Bear call spreads: short call OTM (strike > spot), delta 0.08-0.25
    otm_calls = [c for c in calls if c["strike"] > spot and 0.08 <= abs(c["delta"]) <= 0.25]

    for short_call in otm_calls:
        longs = [c for c in otm_calls if c["strike"] > short_call["strike"]]
        if not longs:
            continue
        best_long = None
        best_width = 0
        for lng in longs:
            w = lng["strike"] - short_call["strike"]
            if 2 <= w <= 10:
                if best_long is None or w < best_width:
                    best_long = lng
                    best_width = w
        if not best_long:
            continue

        width = best_long["strike"] - short_call["strike"]
        credit = short_call["ask"] - best_long["bid"]
        if credit <= 0.05:
            continue

        max_loss = width - credit
        if max_loss <= 0:
            continue

        roi = (credit / max_loss) * 100
        be = short_call["strike"] + credit

        exp = best_long["exp"][:10] if len(best_long["exp"]) >= 10 else best_long["exp"]
        occ_short = make_occ_symbol(symbol, exp, "CALL", short_call["strike"])
        occ_long = make_occ_symbol(symbol, exp, "CALL", best_long["strike"])

        trades.append(TradeIdea(
            symbol=symbol, spread_type="bear_call", expiration=exp,
            dte=short_call["dte"],
            short_strike=short_call["strike"], short_oco=occ_short,
            short_bid=short_call["bid"], short_ask=short_call["ask"],
            short_delta=short_call["delta"],
            long_strike=best_long["strike"], long_oco=occ_long,
            long_bid=best_long["bid"], long_ask=best_long["ask"],
            long_delta=best_long["delta"],
            net_credit=round(credit, 2), max_loss=round(max_loss, 2),
            roi_pct=round(roi, 1), breakeven=round(be, 2),
            score=round(roi * abs(short_call["delta"]) * 10, 2),
            spot_price=spot, iv_rank=0, trend="NEUTRAL",
            reason=f"OTM call credit, {width:.0f} wide, delta {abs(short_call['delta']):.2f}",
        ))

    return trades


# ---------------------------------------------------------------------------
# IV Rank
# ---------------------------------------------------------------------------

def fetch_iv_rank(conn, symbol: str) -> tuple[float, int]:
    """Compute IV rank from stored history. Returns (rank_pct, days_of_history)."""
    pg = is_postgres(get_db_url())
    p = ph(get_db_url())
    cur = conn.cursor()

    if pg:
        query = """
            SELECT day, iv FROM (
                SELECT DATE(s.captured_at) as day,
                       oc.volatility as iv,
                       ROW_NUMBER() OVER (
                           PARTITION BY DATE(s.captured_at)
                           ORDER BY s.captured_at DESC,
                                    ABS(oc.strike - s.underlying_price)
                       ) as rn
                FROM option_contracts oc
                JOIN snapshots s ON oc.snapshot_id = s.id
                WHERE s.symbol = %s
                AND oc.put_call = 'PUT'
                AND oc.dte = 14
                AND ABS(oc.strike - s.underlying_price) < 1
                AND oc.volatility > 0 AND oc.volatility < 200
                AND s.underlying_price IS NOT NULL
            ) sub WHERE rn = 1 ORDER BY day
        """
    else:
        query = """
            SELECT day, iv FROM (
                SELECT DATE(s.captured_at) as day,
                       oc.volatility as iv,
                       ROW_NUMBER() OVER (
                           PARTITION BY DATE(s.captured_at)
                           ORDER BY s.captured_at DESC,
                                    ABS(oc.strike - s.underlying_price)
                       ) as rn
                FROM option_contracts oc
                JOIN snapshots s ON oc.snapshot_id = s.id
                WHERE s.symbol = ?
                AND oc.put_call = 'PUT'
                AND oc.dte = 14
                AND ABS(oc.strike - s.underlying_price) < 1
                AND oc.volatility > 0 AND oc.volatility < 200
                AND s.underlying_price IS NOT NULL
            ) sub WHERE rn = 1 ORDER BY day
        """

    cur.execute(query, (symbol,))
    rows = cur.fetchall()

    if len(rows) < 5:
        return 0.0, len(rows)

    ivs = [float(r[1]) for r in rows]
    current = ivs[-1]
    iv_min = min(ivs)
    iv_max = max(ivs)

    if iv_max - iv_min == 0:
        rank = 50.0
    else:
        rank = ((current - iv_min) / (iv_max - iv_min)) * 100

    return round(rank, 1), len(rows)


# ---------------------------------------------------------------------------
# Trend (SMA 20)
# ---------------------------------------------------------------------------

def fetch_trend(conn, symbol: str) -> str:
    """SMA(20) trend direction."""
    pg = is_postgres(get_db_url())
    p = ph(get_db_url())
    cur = conn.cursor()

    if pg:
        query = """
            SELECT DATE(s.captured_at) as day, s.underlying_price
            FROM snapshots s
            WHERE s.symbol = %s
            AND s.underlying_price IS NOT NULL
            GROUP BY DATE(s.captured_at), s.underlying_price
            ORDER BY day DESC
            LIMIT 25
        """
    else:
        query = """
            SELECT DATE(s.captured_at) as day, s.underlying_price
            FROM snapshots s
            WHERE s.symbol = ?
            AND s.underlying_price IS NOT NULL
            GROUP BY DATE(s.captured_at), s.underlying_price
            ORDER BY day DESC
            LIMIT 25
        """

    cur.execute(query, (symbol,))
    rows = cur.fetchall()

    if len(rows) < 20:
        return "NEUTRAL"

    prices = [float(r[1]) for r in rows]
    current = prices[0]
    sma = sum(prices[:20]) / 20

    if current > sma * 1.002:
        return "BULLISH"
    elif current < sma * 0.998:
        return "BEARISH"
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# VIX (live from Schwab, with fallback)
# ---------------------------------------------------------------------------

def get_vix() -> float | None:
    """Get current VIX from Schwab API. Returns None on failure."""
    try:
        # Use the same pattern as generate_nightly_report.py
        script_path = "/tmp/_fetch_vix.py"
        if not os.path.exists(script_path):
            # Create the script if it doesn't exist
            with open(script_path, "w") as f:
                f.write("""
import sys, os, json
sys.path.insert(0, os.path.expanduser("~/projects/tos_options"))
os.chdir(os.path.expanduser("~/projects/tos_options"))
from dotenv import load_dotenv
load_dotenv()

try:
    from schwab.api import SchwabClient
    client = SchwabClient()
    result = client.get_quote("$VIX")
    price = result.get("$VIX", {}).get("quote", {}).get("lastPrice")
    if price:
        print(float(price))
        sys.exit(0)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)

# Fallback: Google Finance
import urllib.request
try:
    html = urllib.request.urlopen("https://www.google.com/finance/quote/VIX:INDEXCBOE").read().decode()
    import re
    m = re.search(r'data-last-price="([^"]+)"', html)
    if m:
        print(float(m.group(1)))
        sys.exit(0)
except Exception as e:
    print(f"Google fallback failed: {e}", file=sys.stderr)

sys.exit(1)
""")
        import subprocess
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# GEX walls (optional Phase 3)
# ---------------------------------------------------------------------------

def get_gex_summary(conn, snap_id: int, spot: float) -> list[dict]:
    """Get top 5 GEX walls and gamma flip level."""
    pg = is_postgres(get_db_url())
    p = ph(get_db_url())
    cur = conn.cursor()

    # Top GEX walls by magnitude
    cur.execute(f"""
        SELECT strike,
               ROUND(CAST(net_gex / 1e9 AS numeric), 2) as net_gex_B,
               ROUND(CAST(call_gex / 1e9 AS numeric), 2) as call_gex_B,
               ROUND(CAST(ABS(put_gex) / 1e9 AS numeric), 2) as put_gex_B,
               open_interest_total
        FROM aggregates_by_strike
        WHERE snapshot_id = {p}
        ORDER BY ABS(net_gex) DESC
        LIMIT 5
    """, (snap_id,))

    walls = []
    for row in cur.fetchall():
        walls.append({
            "strike": row[0],
            "net_gex_b": row[1],
            "call_gex_b": row[2],
            "put_gex_b": row[3],
            "oi": row[4],
        })

    # Gamma flip: find where net_gex crosses zero near spot
    cur.execute(f"""
        WITH ordered AS (
            SELECT strike, net_gex,
                LAG(net_gex) OVER (ORDER BY strike) as prev_gex
            FROM aggregates_by_strike
            WHERE snapshot_id = {p}
        )
        SELECT strike,
               ROUND(CAST(net_gex AS numeric), 0) as net_gex,
               CASE
                   WHEN prev_gex < 0 AND net_gex > 0 THEN 'CALL WALL'
                   WHEN prev_gex > 0 AND net_gex < 0 THEN 'PUT WALL'
                   ELSE 'SHORT GAMMA'
               END as note
        FROM ordered
        WHERE (prev_gex < 0 AND net_gex > 0) OR (prev_gex > 0 AND net_gex < 0)
        ORDER BY ABS(strike - (SELECT underlying_price FROM snapshots WHERE id = {p}))
        LIMIT 3
    """, (snap_id, snap_id))

    flips = []
    for row in cur.fetchall():
        flips.append({"strike": row[0], "net_gex": row[1], "note": row[2]})

    return {"walls": walls, "flips": flips}


# ---------------------------------------------------------------------------
# Sector flow (simplified for EOD)
# ---------------------------------------------------------------------------

def fetch_sector_flow_eod(conn) -> list[dict]:
    """Sector flow from the latest EOD snapshot per symbol."""
    import yaml

    watchlist_path = os.path.join(project_root, "config", "watchlist.yaml")
    if not os.path.exists(watchlist_path):
        return []

    with open(watchlist_path) as f:
        wl = yaml.safe_load(f)

    core = wl.get("core", {})
    sector_tickers: dict[str, list[str]] = {}
    if isinstance(core, dict):
        for sector_name, entries in core.items():
            if isinstance(entries, list):
                tickers = []
                for entry in entries:
                    if isinstance(entry, dict) and "symbol" in entry:
                        tickers.append(str(entry["symbol"]))
                    elif isinstance(entry, str):
                        tickers.append(entry)
                if tickers:
                    sector_tickers[sector_name] = tickers

    if not sector_tickers:
        return []

    pg = is_postgres(get_db_url())

    # Get latest snapshot per symbol
    if pg:
        snap_q = """
            SELECT DISTINCT ON (s.symbol) s.id, s.symbol
            FROM snapshots s
            ORDER BY s.symbol, s.captured_at DESC
        """
    else:
        snap_q = """
            SELECT s.id, s.symbol FROM snapshots s
            INNER JOIN (
                SELECT symbol, MAX(captured_at) as max_ts
                FROM snapshots GROUP BY symbol
            ) latest ON s.symbol = latest.symbol
            AND s.captured_at = latest.max_ts
        """

    cur = conn.cursor()
    cur.execute(snap_q)
    snap_rows = cur.fetchall()
    if not snap_rows:
        return []

    snap_ids = [r[0] for r in snap_rows]
    p_holder = ", ".join(["%s" if pg else "?"] * len(snap_ids))

    cur.execute(f"""
        SELECT s.symbol, oc.put_call,
               SUM(oc.total_volume) as vol,
               SUM(oc.total_volume * oc.mark) as premium
        FROM option_contracts oc
        JOIN snapshots s ON oc.snapshot_id = s.id
        WHERE s.id IN ({p_holder})
        AND oc.total_volume > 0
        GROUP BY s.symbol, oc.put_call
    """, snap_ids)

    ticker_data: dict[str, dict] = {}
    for symbol, pc, vol, premium in cur.fetchall():
        sym = symbol.strip()
        if sym not in ticker_data:
            ticker_data[sym] = {"call_vol": 0, "put_vol": 0, "call_prem": 0, "put_prem": 0}
        vol = float(vol) if vol else 0
        prem = float(premium) if premium else 0
        if pc == "CALL":
            ticker_data[sym]["call_vol"] += vol
            ticker_data[sym]["call_prem"] += prem
        else:
            ticker_data[sym]["put_vol"] += vol
            ticker_data[sym]["put_prem"] += prem

    flows = []
    for sector, tickers in sector_tickers.items():
        tv = tc = tp = tcp = tpp = 0
        for t in tickers:
            t = t.strip()
            if t in ticker_data:
                d = ticker_data[t]
                tc += d["call_vol"]
                tp += d["put_vol"]
                tcp += d["call_prem"]
                tpp += d["put_prem"]
        tv = tc + tp
        pcr = tp / tc if tc > 0 else 0
        signal = "bullish" if pcr < 0.7 else ("bearish" if pcr > 1.3 else "neutral")
        strength = "strong" if tv > 500000 else ("moderate" if tv > 100000 else "weak")

        flows.append({
            "sector": sector, "volume": int(tv), "pcr": round(pcr, 2),
            "call_prem": round(tcp, 0), "put_prem": round(tpp, 0),
            "signal": signal, "strength": strength,
        })

    flows.sort(key=lambda f: f["volume"], reverse=True)
    return flows


# ---------------------------------------------------------------------------
# Display formatting
# ---------------------------------------------------------------------------

def iv_confidence(days: int) -> str:
    if days < 20:
        return "LOW"
    elif days < 252:
        return "MED"
    return "FULL"


def format_header(health: dict, vix: float | None) -> str:
    lines = []
    now_str = datetime.now(CT).strftime("%Y-%m-%d %H:%M CT")
    lines.append("=" * 70)
    lines.append(f"  NIGHTLY SCAN — {now_str}")
    lines.append("=" * 70)
    lines.append("")
    lines.append("  DATA STATUS")
    lines.append(f"  Latest snapshot: {health['latest_snapshot_time']} (age: {health['latest_snapshot_age_hours']:.1f}h)")
    lines.append(f"  Total contracts: {health['total_contracts']:,}")
    lines.append(f"  Symbols tracked: {', '.join(sorted(health['symbols'].keys()))}")

    if vix is not None:
        vix_regime = "LOW" if vix < 15 else ("NORMAL" if vix < 20 else ("ELEVATED" if vix < 30 else "HIGH FEAR"))
        lines.append(f"  VIX: {vix:.2f} ({vix_regime})")
    else:
        lines.append("  VIX: unavailable (auth expired?)")

    lines.append("")
    return "\n".join(lines)


def format_trade_table(trades: list[TradeIdea], top_n: int = 10) -> str:
    if not trades:
        return "  No spread candidates found.\n"

    trades = trades[:top_n]
    lines = []
    lines.append(f"  TOP {len(trades)} SPREAD CANDIDATES")
    lines.append("  " + "-" * 115)
    lines.append(
        f"  {'#':<3} {'Sym':<5} {'Type':<11} {'Strikes':>14} {'DTE':>3} "
        f"{'Credit':>6} {'Risk':>6} {'ROI%':>5} {'BE':>8} "
        f"{'Score':>6} {'Trend':<8} {'IV%':>4}"
    )
    lines.append("  " + "-" * 115)

    for i, t in enumerate(trades, 1):
        type_short = "BullPut" if t.spread_type == "bull_put" else "BearCall"
        strikes = f"{t.short_strike:.0f}/{t.long_strike:.0f}"
        iv_tag = f"{t.iv_rank:.0f}" if t.iv_rank > 0 else "--"

        lines.append(
            f"  {i:<3} {t.symbol:<5} {type_short:<11} {strikes:>14} {t.dte:>3} "
            f"${t.net_credit:>5.2f} ${t.max_loss:>5.2f} {t.roi_pct:>5.1f} "
            f"${t.breakeven:>7.2f} {t.score:>6.1f} {t.trend:<8} {iv_tag:>4}"
        )

    lines.append("  " + "-" * 115)
    return "\n".join(lines)


def format_trade_detail(trade: TradeIdea) -> str:
    lines = []
    type_label = "BULL PUT CREDIT" if trade.spread_type == "bull_put" else "BEAR CALL CREDIT"
    leg_type = "PUT" if trade.spread_type == "bull_put" else "CALL"
    iv_tag = f"{trade.iv_rank:.0f}%" if trade.iv_rank > 0 else "(insufficient data)"
    iv_conf = iv_confidence(trade.iv_rank) if trade.iv_rank > 0 else ""

    lines.append(f"  {type_label} -- {trade.symbol}")
    lines.append(f"  Expiration: {trade.expiration}  |  DTE: {trade.dte}  |  Spot: ${trade.spot_price:.2f}")
    lines.append("")
    lines.append(f"  SELL {trade.short_strike} {leg_type} @ ${trade.short_ask:.2f} (bid ${trade.short_bid:.2f})")
    lines.append(f"    OCC: {trade.short_oco}")
    lines.append(f"    Delta: {trade.short_delta:.3f}")
    lines.append("")
    lines.append(f"  BUY  {trade.long_strike} {leg_type} @ ${trade.long_bid:.2f} (ask ${trade.long_ask:.2f})")
    lines.append(f"    OCC: {trade.long_oco}")
    lines.append(f"    Delta: {trade.long_delta:.3f}")
    lines.append("")
    lines.append(f"  Net Credit: ${trade.net_credit:.2f}  |  Max Risk: ${trade.max_loss:.2f}")
    lines.append(f"  ROI: {trade.roi_pct:.1f}%  |  Breakeven: ${trade.breakeven:.2f}")
    sl_price = trade.net_credit * 1.5
    pt_price = trade.net_credit * 0.25
    lines.append(f"  Stop Loss (50%): exit if debit >= ${sl_price:.2f}  |  Profit Target (75%): exit at ${pt_price:.2f}")
    lines.append(f"  Trend: {trade.trend}  |  IV Rank: {iv_tag} ({iv_conf})")
    lines.append(f"  Reason: {trade.reason}")
    lines.append("")
    return "\n".join(lines)


def format_trade_log(trades: list[TradeIdea]) -> str:
    lines = []
    lines.append("TRADE LOG FOR MANUAL TOS ENTRY")
    lines.append(f"Generated: {datetime.now(CT).strftime('%Y-%m-%d %H:%M CT')}")
    lines.append("=" * 80)

    for i, t in enumerate(trades, 1):
        lines.append(f"\n--- Trade #{i} ---")
        lines.append(f"Type: {t.spread_type}")
        lines.append(f"Symbol: {t.symbol}")
        lines.append(f"Expiration: {t.expiration}")
        lines.append(f"DTE: {t.dte}")
        lines.append(f"Spot: ${t.spot_price:.2f}")
        lines.append(f"")
        lines.append(f"SELL: {t.short_oco} @ {t.short_ask:.2f}")
        lines.append(f"BUY:  {t.long_oco} @ {t.long_bid:.2f}")
        lines.append(f"Net Credit: ${t.net_credit:.2f}")
        lines.append(f"Max Risk: ${t.max_loss:.2f}")
        lines.append(f"ROI: {t.roi_pct:.1f}%")
        lines.append(f"Breakeven: ${t.breakeven:.2f}")
        lines.append(f"Score: {t.score:.1f}")
        lines.append(f"Trend: {t.trend} | IV Rank: {t.iv_rank:.0f}%")
        lines.append(f"SL(50%): ${t.net_credit * 1.5:.2f} | PT(75%): ${t.net_credit * 0.25:.2f}")

    return "\n".join(lines)


def format_sector_table(flows: list[dict]) -> str:
    if not flows:
        return "  (no sector flow data)\n"

    lines = []
    lines.append("")
    lines.append("  SECTOR FLOW (EOD)")
    lines.append("  " + "-" * 75)
    lines.append(
        f"  {'Sector':<22} {'Vol':>8} {'PCR':>5} "
        f"{'Call$':>8} {'Put$':>8} {'Signal':<9} {'Str':<8}"
    )
    lines.append("  " + "-" * 75)

    for f in flows:
        emoji = {"bullish": "+", "bearish": "-", "neutral": "="}.get(f["signal"], "?")
        lines.append(
            f"  {f['sector']:<22} {f['volume']:>8,} {f['pcr']:>5.2f} "
            f"{f['call_prem']:>8,.0f} {f['put_prem']:>8,.0f} "
            f"{emoji} {f['signal']:<8} {f['strength']:<8}"
        )

    lines.append("  " + "-" * 75)
    lines.append("  PCR<0.7=bullish >1.3=bearish")
    return "\n".join(lines)


def format_gex_section(gex_data: dict, spot: float, symbol: str) -> str:
    if not gex_data or not gex_data.get("walls"):
        return ""

    lines = []
    lines.append("")
    lines.append(f"  {symbol} GEX WALLS (optional -- Phase 3)")
    lines.append("  " + "-" * 65)

    for w in gex_data["walls"]:
        direction = "CALL" if w["net_gex_b"] > 0 else "PUT"
        lines.append(
            f"  Strike {w['strike']:.0f}: {w['net_gex_b']:+.2f}B net "
            f"(C: {w['call_gex_b']:.2f}B P: {w['put_gex_b']:.2f}B) "
            f"OI: {w['oi']:,.0f}"
        )

    if gex_data.get("flips"):
        lines.append("")
        lines.append("  Gamma flips:")
        for flip in gex_data["flips"]:
            lines.append(
                f"  Strike {flip['strike']:.0f}: {flip['net_gex']:+,.0f} {flip['note']}"
            )

    lines.append("  " + "-" * 65)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gameplan generator
# ---------------------------------------------------------------------------

def generate_gameplan(trades: list[TradeIdea], vix: float | None,
                      flows: list[dict], top_n: int = 3) -> str:
    """Generate a gameplan text for tomorrow."""
    now_ct = datetime.now(CT)
    tomorrow = now_ct.strftime("%Y-%m-%d")
    if now_ct.hour >= 16:  # after market close
        from datetime import timedelta
        tomorrow = (now_ct + timedelta(days=1)).strftime("%Y-%m-%d")
        # Skip weekends
        if (now_ct + timedelta(days=1)).weekday() >= 5:
            # Find next Monday
            days_ahead = 7 - now_ct.weekday()
            tomorrow = (now_ct + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    lines = []
    lines.append(f"# GAMEPLAN -- {tomorrow}")
    lines.append(f"# Generated: {now_ct.strftime('%Y-%m-%d %H:%M CT')}")
    lines.append("")

    # VIX context
    if vix is not None:
        lines.append(f"## Vol Regime")
        lines.append(f"VIX: {vix:.2f}")
        if vix < 15:
            lines.append("Regime: LOW -- thin credits, safe entries but low ROI")
        elif vix < 20:
            lines.append("Regime: NORMAL -- good for credit spreads")
        elif vix < 30:
            lines.append("Regime: ELEVATED -- wider spreads, reduce size")
        else:
            lines.append("Regime: HIGH FEAR -- consider sitting out or very wide OTM")
        lines.append("")

    # Trade candidates
    active_trades = trades[:top_n]
    if active_trades:
        lines.append("## Top Candidates")
        for i, t in enumerate(active_trades, 1):
            type_label = "Bull Put" if t.spread_type == "bull_put" else "Bear Call"
            lines.append(f"### #{i}: {t.symbol} {type_label}")
            lines.append(f"- Expiry: {t.expiration} (DTE {t.dte})")
            lines.append(f"- SELL {t.short_strike} {t.spread_type.split('_')[1].upper()} OCC:{t.short_oco}")
            lines.append(f"- BUY  {t.long_strike} {t.spread_type.split('_')[1].upper()} OCC:{t.long_oco}")
            lines.append(f"- Credit: ${t.net_credit:.2f} | Risk: ${t.max_loss:.2f} | ROI: {t.roi_pct:.1f}%")
            lines.append(f"- BE: ${t.breakeven:.2f}")
            lines.append(f"- SL: 50% = ${t.net_credit * 1.5:.2f} | PT: 75% = ${t.net_credit * 0.25:.2f}")
            lines.append(f"- Trend: {t.trend} | IV Rank: {t.iv_rank:.0f}%")
            lines.append(f"- Score: {t.score:.1f}")
            lines.append("")
    else:
        lines.append("## No Trade Candidates")
        lines.append("No qualifying spreads found. Consider:")
        lines.append("- Waiting for higher IV environment")
        lines.append("- Widening DTE range")
        lines.append("- Checking sector flow for rotation opportunities")
        lines.append("")

    # Skip conditions
    lines.append("## Skip Conditions")
    lines.append("- [ ] Gap > 1% against position at open")
    vix_str = f"{vix:.2f}" if vix is not None else "unknown"
    lines.append(f"- [ ] VIX > 25 (current: {vix_str})")
    lines.append("- [ ] FOMC / CPI week")
    lines.append("- [ ] Existing position still open")
    lines.append("")

    # Sector context
    if flows:
        lines.append("## Sector Flow Context")
        for f in flows[:5]:
            lines.append(f"- {f['sector']}: PCR={f['pcr']:.2f} ({f['signal']}), vol={f['volume']:,}")
        lines.append("")

    lines.append("---")
    lines.append("Sizing: 2% of bankroll risk per trade (~$1000 on $50K)")
    lines.append("Max 1-2 concurrent positions unless overlap approved")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_nightly_scan(
    tickers: list[str] | None = None,
    top_n: int = 10,
    include_gex: bool = False,
    trade_log: bool = False,
) -> str:
    """Run the full nightly scan and return formatted output."""
    db_url = get_db_url()
    conn = get_connection(db_url)

    try:
        # Step 1: Health check
        health = check_eod_data(conn)
        vix = get_vix()

        # Step 2: Get latest EOD snapshots
        snapshots = get_latest_snapshots(conn, tickers)
        if not snapshots:
            return (
                format_header(health, vix) +
                "\n  ERROR: No EOD snapshots found. Is the scraper running?\n"
            )

        # Step 3: Build spreads from each snapshot
        all_trades = []
        snap_info = {}
        for snap_id, sym, price, captured_at in snapshots:
            price = float(price) if price else 0
            trades = build_spreads_from_snapshot(conn, snap_id, sym, price)
            all_trades.extend(trades)
            snap_info[sym] = {
                "id": snap_id, "price": price,
                "time": str(captured_at)[:19] if captured_at else "?",
            }

        # Step 4: Enrich with IV rank + trend
        for t in all_trades:
            iv_rank, hist_days = fetch_iv_rank(conn, t.symbol)
            t.iv_rank = iv_rank
            t.trend = fetch_trend(conn, t.symbol)
            if hist_days < 20:
                t.reason += f" (IV rank: LOW confidence, {hist_days}d history)"

        # Sort all trades by score globally
        all_trades.sort(key=lambda t: t.score, reverse=True)

        # Step 5: Sector flow
        flows = fetch_sector_flow_eod(conn)

        # Step 6: GEX (optional)
        gex_sections = []
        if include_gex:
            for sym, info in snap_info.items():
                try:
                    gex_data = get_gex_summary(conn, info["id"], info["price"])
                    gex_sections.append(format_gex_section(gex_data, info["price"], sym))
                except Exception:
                    pass

        # Format output
        parts = []
        parts.append(format_header(health, vix))

        # Snapshot times
        parts.append("  EOD SNAPSHOTS")
        for sym, info in snap_info.items():
            parts.append(f"  {sym}: ${info['price']:.2f} at {info['time']}")
        parts.append("")

        parts.append(format_trade_table(all_trades, top_n))

        # Trade details for top 3
        if all_trades:
            parts.append("")
            parts.append("  " + "=" * 70)
            parts.append("  TRADE DETAILS")
            parts.append("  " + "=" * 70)
            for t in all_trades[:3]:
                parts.append(format_trade_detail(t))

        # Sector flow
        parts.append(format_sector_table(flows))

        # GEX sections
        for gex in gex_sections:
            parts.append(gex)

        # Trade log appendix
        if trade_log:
            parts.append("")
            parts.append(format_trade_log(all_trades))

        return "\n".join(parts)

    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nightly EOD options scan + gameplan")
    parser.add_argument("--once", action="store_true", default=True, help="Run once (default)")
    parser.add_argument("--tickers", nargs="+", default=None, help="Filter to specific tickers")
    parser.add_argument("--top", type=int, default=10, help="Show top N trades in table")
    parser.add_argument("--trade-log", action="store_true", help="Include trade log with OCC symbols")
    parser.add_argument("--no-gameplan", action="store_true", help="Skip writing gameplan file")
    parser.add_argument("--gex", action="store_true", help="Include GEX walls (Phase 3)")
    parser.add_argument("--discord", action="store_true", help="Post summary to Discord")

    args = parser.parse_args()

    output = run_nightly_scan(
        tickers=args.tickers,
        top_n=args.top,
        include_gex=args.gex,
        trade_log=args.trade_log,
    )
    print(output)

    # Write gameplan file
    if not args.no_gameplan:
        from datetime import date
        out_dir = os.path.join(project_root, "out")
        os.makedirs(out_dir, exist_ok=True)
        gp_path = os.path.join(out_dir, f"gameplan_{date.today().isoformat()}.md")

        # Rebuild gameplan from the scan data
        db_url = get_db_url()
        conn = get_connection(db_url)
        try:
            health = check_eod_data(conn)
            vix = get_vix()
            snapshots = get_latest_snapshots(conn, args.tickers)
            all_trades = []
            for snap_id, sym, price, _ in snapshots:
                price = float(price) if price else 0
                trades = build_spreads_from_snapshot(conn, snap_id, sym, price)
                all_trades.extend(trades)
            for t in all_trades:
                iv_rank, _ = fetch_iv_rank(conn, t.symbol)
                t.iv_rank = iv_rank
                t.trend = fetch_trend(conn, t.symbol)
            all_trades.sort(key=lambda t: t.score, reverse=True)
            flows = fetch_sector_flow_eod(conn)

            gp = generate_gameplan(all_trades[:args.top], vix, flows, top_n=3)
            with open(gp_path, "w") as f:
                f.write(gp)
            print(f"\n  Gameplan written to {gp_path}")
        except Exception as e:
            print(f"\n  Warning: could not write gameplan: {e}")
        finally:
            conn.close()

    # Discord
    if args.discord:
        try:
            from discord.webhook import send_message
            # Truncate for Discord 2000 char limit
            msg = output[:1900]
            send_message(f"**Nightly Scan**\n```\n{msg}\n```")
            print("  Posted to Discord")
        except Exception as e:
            print(f"  Discord send failed: {e}")
