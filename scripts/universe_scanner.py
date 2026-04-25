#!/usr/bin/env python3
"""
Universe Scanner — discovers and ranks stocks for options scraping.

Two-tier pipeline:
  1. Pre-market scan: fetch quotes for entire watchlist + movers, score each name
  2. Output top N names to feed into the options scraper

Usage:
  python scripts/universe_scanner.py --scan          # run full scan
  python scripts/universe_scanner.py --scan --top 5   # only top 5
  python scripts/universe_scanner.py --schedule        # run on cron
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from schwab.api import get_quotes, get_top_movers
from schwab.client import SchwabConfigError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────

def load_config() -> dict:
    """Load watchlist.yaml config."""
    import yaml
    config_path = project_root / "config" / "watchlist.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    # Defaults if no config file
    return {
        "indexes": ["$SPX", "SPY", "QQQ"],
        "tier1": ["AAPL", "TSLA", "NVDA", "META", "AMZN", "GOOG", "MSFT", "AMD",
                   "NFLX", "CRM", "UBER", "PLTR", "COIN", "MSTR"],
        "tier2": [],
        "movers_sources": [
            {"symbol": "$SPX", "sort": "volume", "limit": 15},
        ],
        "scoring": {
            "rel_volume_weight": 3.0,
            "abs_volume_weight": 2.0,
            "range_position_weight": 2.0,
            "daily_move_weight": 2.0,
            "mover_bonus": 1.0,
        },
        "thresholds": {
            "min_score": 4.0,
            "max_names": 8,
            "min_avg_volume": 1000000,
            "require_optionable": True,
        },
    }


# ── Data fetching ─────────────────────────────────────────────────

def fetch_movers(config: dict) -> tuple[list[str], set[str]]:
    """Fetch top movers from all configured sources. Returns (all_symbols, mover_set)."""
    mover_symbols: set[str] = set()
    all_mover_data: list[dict] = []

    for source in config.get("movers_sources", []):
        sym = source["symbol"]
        sort = source.get("sort", "volume")
        limit = source.get("limit", 10)
        try:
            movers = get_top_movers(sym, sort, frequency=0, limit=limit)
            for m in movers:
                if isinstance(m, dict) and m.get("symbol"):
                    mover_symbols.add(m["symbol"])
                    all_mover_data.append(m)
            logger.info(f"Movers ({sym}, {sort}): {len(movers)} names")
        except Exception as e:
            logger.warning(f"Movers fetch failed for {sym}: {e}")

    return all_mover_data, mover_symbols


def fetch_quotes(symbols: list[str]) -> dict[str, dict]:
    """Batch-fetch quotes. Handles large lists by chunking."""
    all_quotes: dict[str, dict] = {}
    chunk_size = 100  # Schwab handles up to ~500 but let's be safe

    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i + chunk_size]
        try:
            quotes = get_quotes(chunk)
            all_quotes.update(quotes)
            logger.info(f"Fetched {len(quotes)} quotes ({i+1}-{i+len(chunk)} of {len(symbols)})")
        except Exception as e:
            logger.error(f"Quote fetch failed for chunk: {e}")

    return all_quotes


# ── Scoring ───────────────────────────────────────────────────────

def score_stock(
    quote: dict[str, Any],
    is_mover: bool,
    weights: dict[str, float],
    thresholds: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Score a single stock based on quote data.
    Returns a score dict or None if it doesn't pass filters.
    """
    ref = quote.get("reference", {})
    fundamental = quote.get("fundamental", {})
    q = quote.get("quote", {})
    symbol = quote.get("symbol", ref.get("symbol", "?"))

    # ── Hard filters ──
    if thresholds.get("require_optionable") and not ref.get("optionable"):
        return None

    avg_volume = fundamental.get("avg10DaysVolume", 0) or 0
    if avg_volume < thresholds.get("min_avg_volume", 1000000):
        return None

    # ── Score components ──
    scores: dict[str, float] = {}

    # 1. Relative volume (today vs 10-day avg)
    today_vol = q.get("totalVolume", 0) or 0
    if avg_volume > 0:
        rel_vol = today_vol / avg_volume
        # Scale: 0-0.5x = 0, 0.5-1x = 1, 1-2x = 2, 2x+ = 3
        if rel_vol < 0.5:
            scores["rel_volume"] = 0
        elif rel_vol < 1.0:
            scores["rel_volume"] = 1
        elif rel_vol < 2.0:
            scores["rel_volume"] = 2
        else:
            scores["rel_volume"] = 3
    else:
        scores["rel_volume"] = 0

    # 2. Absolute volume (millions)
    vol_m = today_vol / 1e6
    if vol_m >= 50:
        scores["abs_volume"] = 2
    elif vol_m >= 10:
        scores["abs_volume"] = 1.5
    elif vol_m >= 5:
        scores["abs_volume"] = 1
    else:
        scores["abs_volume"] = 0.5

    # 3. Range position (where is price relative to 52w range?)
    low_52 = q.get("52WeekLow") or 0
    high_52 = q.get("52WeekHigh") or 0
    last_price = q.get("lastPrice") or q.get("mark") or 0
    if high_52 > low_52 and last_price > 0:
        range_pos = (last_price - low_52) / (high_52 - low_52)
        # Near extremes = more IV opportunity
        # 0-10% or 90-100% = 2 points, 10-25% or 75-90% = 1.5, middle = 0.5
        if range_pos < 0.10 or range_pos > 0.90:
            scores["range_position"] = 2
        elif range_pos < 0.25 or range_pos > 0.75:
            scores["range_position"] = 1.5
        else:
            scores["range_position"] = 0.5
    else:
        scores["range_position"] = 0

    # 4. Daily move magnitude
    pct_change = abs(q.get("netPercentChange", 0) or 0)
    if pct_change >= 5:
        scores["daily_move"] = 2
    elif pct_change >= 3:
        scores["daily_move"] = 1.5
    elif pct_change >= 1.5:
        scores["daily_move"] = 1
    else:
        scores["daily_move"] = 0.5

    # 5. Mover bonus
    scores["mover_bonus"] = weights.get("mover_bonus", 1.0) if is_mover else 0

    # ── Weighted total ──
    total = sum(
        scores.get(k, 0) * weights.get(f"{k}_weight", 1.0)
        for k in ["rel_volume", "abs_volume", "range_position", "daily_move"]
    )
    total += scores["mover_bonus"]

    return {
        "symbol": symbol,
        "description": ref.get("description", ""),
        "last_price": last_price,
        "pct_change": q.get("netPercentChange", 0),
        "total_volume": today_vol,
        "avg10d_volume": avg_volume,
        "rel_volume": rel_vol if avg_volume > 0 else 0,
        "optionable": ref.get("optionable", False),
        "pe_ratio": fundamental.get("peRatio"),
        "range_52w": f"${low_52:.0f}-${high_52:.0f}" if low_52 and high_52 else "N/A",
        "range_position": range_pos if high_52 > low_52 else 0,
        "is_mover": is_mover,
        "scores": scores,
        "total_score": round(total, 2),
    }


# ── Main scan ─────────────────────────────────────────────────────

def run_scan(config: dict, top_n: int | None = None) -> list[dict]:
    """Run full universe scan and return ranked results."""
    thresholds = config.get("thresholds", {})
    weights = config.get("scoring", {})
    max_names = top_n or thresholds.get("max_names", 8)

    # 1. Gather all symbols
    indexes = config.get("indexes", [])
    tier1 = config.get("tier1", [])
    tier2 = config.get("tier2", [])

    # 2. Fetch movers for auto-discovery
    logger.info("Fetching movers...")
    mover_data, mover_set = fetch_movers(config)
    logger.info(f"Discovered {len(mover_set)} unique movers")

    # 3. Build full symbol list (dedup)
    # Filter out index symbols that don't work with get_quotes ($-prefixed)
    all_raw = indexes + tier1 + tier2 + list(mover_set)
    quoteable_symbols = [s for s in set(all_raw)
                         if isinstance(s, str) and not s.startswith("$")]

    # 4. Batch fetch quotes
    logger.info(f"Fetching quotes for {len(quoteable_symbols)} symbols...")
    quotes = fetch_quotes(quoteable_symbols)

    if not quotes:
        logger.error("No quotes returned")
        return [], []

    # 5. Score each stock
    results = []
    for symbol, quote in quotes.items():
        is_mover = symbol in mover_set
        scored = score_stock(quote, is_mover, weights, thresholds)
        if scored is not None:
            results.append(scored)

    # 6. Sort by score descending
    results.sort(key=lambda r: r["total_score"], reverse=True)

    # 7. Mark indexes separately
    index_set = set(indexes)
    individual = [r for r in results if r["symbol"] not in index_set]

    return results, individual


def format_discord_message(selected: list[dict], now_str: str) -> str:
    """Format top picks for Discord (compact, fits 2000 chars)."""
    if not selected:
        return ""
    lines = [
        f"**Universe Scanner** {now_str}",
        "```",
        f"{'#':>2} {'Sym':>6} {'Price':>8} {'Chg%':>7} {'RelVol':>6} {'Score':>5}",
    ]
    for i, r in enumerate(selected, 1):
        chg = r.get("pct_change", 0) or 0
        rel = r.get("rel_volume", 0) or 0
        lines.append(
            f"{i:>2} {r['symbol']:>6} ${r['last_price']:>7.2f} {chg:>+6.1f}% "
            f"{rel:>5.1f}x {r['total_score']:>5.1f}"
        )
    lines.append("```")
    msg = "\n".join(lines)
    if len(msg) > 1900:
        msg = msg[:1890] + "\n...truncated```"
    return msg


def print_results(results: list[dict], individual: list[dict],
                  config: dict, top_n: int | None = None):
    """Pretty-print the scan results."""
    thresholds = config.get("thresholds", {})
    min_score = thresholds.get("min_score", 4.0)
    max_names = top_n or thresholds.get("max_names", 8)
    indexes = set(config.get("indexes", []))

    now = datetime.now().strftime("%Y-%m-%d %I:%M %p ET")
    print(f"\nUniverse Scan Results  ({now})")
    print("=" * 90)

    # Index tickers (always scraped)
    print(f"\nIndex Tickers (always scraped):")
    for r in results:
        if r["symbol"] in indexes:
            chg = r.get("pct_change", 0) or 0
            print(f"  {r['symbol']:>6}  ${r['last_price']:>10.2f}  {chg:+.2f}%")

    # Top ranked individual names
    print(f"\nTop {max_names} Individual Names (min score: {min_score}):")
    print(f"{'Rank':>4}  {'Symbol':>6}  {'Price':>9}  {'Chg%':>7}  {'RelVol':>7}  "
          f"{'Score':>6}  {'Mover':>5}  Description")
    print("-" * 90)

    selected = []
    for i, r in enumerate(individual[:max_names], 1):
        if r["total_score"] < min_score:
            break
        selected.append(r)
        chg = r.get("pct_change", 0) or 0
        mover = "YES" if r["is_mover"] else ""
        desc = (r.get("description") or "")[:25]
        print(f"{i:>4}  {r['symbol']:>6}  ${r['last_price']:>9.2f}  {chg:>+6.1f}%  "
              f"{r['rel_volume']:>6.1f}x  {r['total_score']:>6.1f}  {mover:>5}  {desc}")

    # All evaluated names (brief)
    print(f"\nAll Evaluated Names ({len(individual)} total):")
    for r in individual[:30]:
        chg = r.get("pct_change", 0) or 0
        marker = " <-- SELECTED" if r in selected else ""
        print(f"  {r['symbol']:>6}  score={r['total_score']:>5.1f}  "
              f"${r['last_price']:>8.2f}  {chg:>+6.1f}%  "
              f"relVol={r['rel_volume']:.1f}x{marker}")
    if len(individual) > 30:
        print(f"  ... and {len(individual) - 30} more")

    # Output selected tickers as a scrapeable list
    if selected:
        symbols = [r["symbol"] for r in selected]
        print(f"\nSelected tickers for scraper:")
        print(f"  {' '.join(symbols)}")
        return symbols, selected
    else:
        print("\nNo names above threshold today.")
        return [], []


# ── Output file ───────────────────────────────────────────────────

def save_ticker_file(symbols: list[str]):
    """Write selected tickers to a file the scraper can read."""
    out_path = project_root / "config" / "dynamic_tickers.json"
    payload = {
        "updated_at": datetime.now().isoformat(),
        "tickers": symbols,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Saved {len(symbols)} tickers to {out_path}")


def load_dynamic_tickers() -> list[str]:
    """Load the last scan's ticker list."""
    path = project_root / "config" / "dynamic_tickers.json"
    if path.exists():
        with open(path) as f:
            data = json.load(f)
        return data.get("tickers", [])
    return []


# ── CLI ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Universe scanner for options scraping")
    parser.add_argument("--scan", action="store_true", help="Run a full scan now")
    parser.add_argument("--top", type=int, default=None,
                        help="Override max names to select (default: from config)")
    parser.add_argument("--schedule", action="store_true",
                        help="Run on schedule (pre-market + every 30 min)")
    parser.add_argument("--interval", type=int, default=30,
                        help="Scan interval in minutes (default: 30)")
    parser.add_argument("--save", action="store_true",
                        help="Save selected tickers to config/dynamic_tickers.json")
    parser.add_argument("--show-config", action="store_true",
                        help="Print loaded config and exit")
    args = parser.parse_args()

    config = load_config()

    if args.show_config:
        import yaml
        print(yaml.dump(config, default_flow_style=False))
        return

    if not args.scan and not args.schedule:
        parser.print_help()
        return

    if args.scan:
        try:
            results, individual = run_scan(config, args.top)
            symbols, selected = print_results(results, individual, config, args.top)
            if args.save and symbols:
                save_ticker_file(symbols)
            if selected:
                try:
                    from discord.webhook import send_message
                    now_str = datetime.now().strftime("%I:%M %p ET")
                    msg = format_discord_message(selected, now_str)
                    send_message(msg)
                    logger.info("Discord alert sent (%d picks)", len(selected))
                except Exception as exc:
                    logger.warning("Discord alert failed: %s", exc)
        except SchwabConfigError as e:
            logger.error(f"Auth error: {e}")
            logger.error("Run: docker compose run --rm cli auth")
            sys.exit(1)

    elif args.schedule:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
        from zoneinfo import ZoneInfo

        ET = ZoneInfo("US/Eastern")
        scheduler = BlockingScheduler(timezone=ET)

        def scheduled_scan():
            try:
                results, individual = run_scan(config, args.top)
                symbols, selected = print_results(results, individual, config, args.top)
                if symbols:
                    save_ticker_file(symbols)
                if selected:
                    try:
                        from discord.webhook import send_message
                        now_str = datetime.now().strftime("%I:%M %p ET")
                        msg = format_discord_message(selected, now_str)
                        send_message(msg)
                        logger.info("Discord alert sent (%d picks)", len(selected))
                    except Exception as exc:
                        logger.warning("Discord alert failed: %s", exc)
            except Exception as e:
                logger.error(f"Scan failed: {e}")

        # Pre-market scan at 9:15 AM ET
        scheduler.add_job(
            scheduled_scan,
            CronTrigger(day_of_week="mon-fri", hour=9, minute=15, timezone=ET),
            id="premarket_scan",
            name="Pre-market universe scan",
        )

        # Re-scan every N minutes during market hours
        scheduler.add_job(
            scheduled_scan,
            CronTrigger(
                day_of_week="mon-fri",
                hour=f"10-15",
                minute=f"*/{args.interval}",
                timezone=ET,
            ),
            id="intraday_scan",
            name=f"Intraday scan (every {args.interval} min)",
        )

        logger.info("Universe scanner scheduled: pre-market 9:15 + every %d min", args.interval)
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()


if __name__ == "__main__":
    main()
