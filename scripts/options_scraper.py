from __future__ import annotations

import json
import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from cli import _persist_snapshot, _resolve_dates
from gex.storage import DEFAULT_DB_PATH, get_connection, init_db
from schwab.api import get_option_chain, get_option_chain_rows
from schwab.client import SchwabConfigError
from scripts.shared import ET, is_market_hours, send_heartbeat_alert, send_token_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


DEFAULT_TICKERS = ["SPY", "QQQ"]

RATE_LIMIT_MARKET_DATA_PER_MIN = 60
RATE_LIMIT_TOTAL_PER_MIN = 120
RATE_LIMIT_BACKOFF_SECONDS = 60
INTER_TICKER_DELAY_SECONDS = 1.5

TICKER_CONFIGS = {
    "$SPX": {"strike_count": 50, "days": 14},
    "SPX": {"strike_count": 50, "days": 14},
    "NDX": {"strike_count": 50, "days": 14},
    "$NDX": {"strike_count": 50, "days": 14},
    "RUT": {"strike_count": 50, "days": 14},
    "$RUT": {"strike_count": 50, "days": 14},
    "VIX": {"strike_count": 40, "days": 14},
}

# Default config for individual stocks (smaller chains, tighter DTE)
INDIVIDUAL_STOCK_DEFAULTS = {"strike_count": 25, "days": 14}

DYNAMIC_TICKERS_PATH = project_root / "config" / "dynamic_tickers.json"


def load_dynamic_tickers() -> list[str]:
    """Read tickers from universe scanner output. Returns empty list on failure."""
    try:
        if not DYNAMIC_TICKERS_PATH.exists():
            return []
        data = json.loads(DYNAMIC_TICKERS_PATH.read_text())
        tickers = data.get("tickers", [])
        if tickers:
            logger.info(f"Loaded {len(tickers)} dynamic tickers: {', '.join(tickers)}")
        return tickers
    except Exception as exc:
        logger.warning(f"Failed to load dynamic tickers: {exc}")
        return []


class RateLimitBudget:
    def __init__(self, max_per_min: int = RATE_LIMIT_MARKET_DATA_PER_MIN):
        self._max = max_per_min
        self._timestamps: list[float] = []

    def record(self) -> None:
        self._timestamps.append(time.monotonic())
        self._timestamps = self._timestamps[-self._max * 2 :]

    def remaining(self) -> int:
        cutoff = time.monotonic() - 60.0
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        return max(0, self._max - len(self._timestamps))

    def wait_if_needed(self, min_remaining: int = 5) -> None:
        if self.remaining() < min_remaining:
            wait = max(1.0, 60.0 - (time.monotonic() - self._timestamps[0]))
            logger.warning(
                f"Rate limit budget low ({self.remaining()} remaining), waiting {wait:.0f}s"
            )
            time.sleep(wait)


budget = RateLimitBudget()


def scrape_ticker(
    symbol: str,
    days: int = 30,
    db_path: str = DEFAULT_DB_PATH,
    option_range: str = "ALL",
    contract_type: str = "ALL",
    dry_run: bool = False,
    verbose: bool = False,
    skip_raw_json: bool = True,
    max_retries: int = 3,
) -> int | None:
    budget.wait_if_needed()

    ticker_cfg = TICKER_CONFIGS.get(symbol.upper(), INDIVIDUAL_STOCK_DEFAULTS)
    effective_days = ticker_cfg.get("days", days)
    strike_count = ticker_cfg.get("strike_count")

    for attempt in range(max_retries):
        try:
            chain = get_option_chain(
                symbol=symbol,
                days=effective_days,
                contract_type=contract_type,
                option_range=option_range,
                strike_count=strike_count,
            )
            rows = get_option_chain_rows(
                symbol=symbol,
                days=effective_days,
                contract_type=contract_type,
                option_range=option_range,
                strike_count=strike_count,
            )
            budget.record()
            budget.record()
            break
        except SchwabConfigError as exc:
            logger.error(f"[{symbol}] auth error: {exc}")
            return None
        except Exception as exc:
            err_str = str(exc).lower()
            retryable = (
                "429" in err_str
                or "502" in err_str
                or "too_big_body" in err_str
                or "buffer overflow" in err_str
            )
            if retryable and attempt < max_retries - 1:
                if (
                    "502" in err_str
                    or "buffer overflow" in err_str
                    or "too_big_body" in err_str
                ):
                    logger.warning(
                        f"[{symbol}] 502 body overflow — reducing strike_count and retrying"
                    )
                    if strike_count is None or strike_count > 25:
                        strike_count = 25
                    elif strike_count > 10:
                        strike_count = 10
                    else:
                        logger.error(
                            f"[{symbol}] already at minimum strike_count={strike_count}, cannot reduce further"
                        )
                        return None
                else:
                    logger.warning(
                        f"[{symbol}] 429 rate limited, backing off {RATE_LIMIT_BACKOFF_SECONDS}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
                continue
            logger.error(f"[{symbol}] API error: {exc}")
            return None
    else:
        logger.error(f"[{symbol}] exhausted retries")
        return None

    if not rows:
        logger.warning(f"[{symbol}] no option rows returned")
        return None

    spot = chain.get("underlying", {}).get("last")
    contract_count = len(rows)
    has_oi = sum(1 for r in rows if (r.get("open_interest") or 0) > 0)
    has_greeks = sum(1 for r in rows if r.get("delta") is not None)

    if verbose:
        logger.info(
            f"[{symbol}] {contract_count} contracts | "
            f"spot={spot} | with_oi={has_oi} | with_greeks={has_greeks}"
        )

    if dry_run:
        logger.info(f"[{symbol}] dry run — skipping DB write")
        return 0

    try:
        snapshot_id = _persist_snapshot(
            db_path, "scraper", chain, rows, skip_raw_json=skip_raw_json
        )

        strikes = sorted(set(r.get("strike", 0) for r in rows))
        expirations = sorted(set(r.get("expiration_date", "") for r in rows))
        dte_range = sorted(set(r.get("dte", 0) for r in rows))
        total_oi = sum(r.get("open_interest") or 0 for r in rows)
        total_vol = sum(r.get("total_volume") or 0 for r in rows)
        calls = sum(1 for r in rows if r.get("put_call") == "CALL")
        puts = sum(1 for r in rows if r.get("put_call") == "PUT")

        print(
            f"\n{'=' * 60}\n"
            f"  {symbol} | snapshot #{snapshot_id}\n"
            f"  {datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S ET')}\n"
            f"{'-' * 60}\n"
            f"  Spot:          {spot}\n"
            f"  Contracts:     {contract_count} ({calls}C / {puts}P)\n"
            f"  Strikes:       {len(strikes)} ({strikes[0]:.1f} - {strikes[-1]:.1f})\n"
            f"  Expirations:   {len(expirations)} ({dte_range[0]} - {dte_range[-1]} DTE)\n"
            f"  Total OI:      {total_oi:,}\n"
            f"  Total Volume:  {total_vol:,}\n"
            f"  With Greeks:   {has_greeks}/{contract_count}\n"
            f"  Strike Count:  {strike_count or 'unlimited'}\n"
            f"  DTE Window:    {effective_days}d\n"
            f"  Raw JSON:      {'saved' if not skip_raw_json else 'skipped'}\n"
            f"{'=' * 60}"
        )

        return snapshot_id
    except Exception as exc:
        logger.error(f"[{symbol}] DB write error: {exc}")
        return None


def run_cycle(
    tickers: list[str],
    days: int = 30,
    db_path: str = DEFAULT_DB_PATH,
    option_range: str = "ALL",
    dry_run: bool = False,
    verbose: bool = False,
    skip_raw_json: bool = True,
) -> None:
    if not is_market_hours():
        logger.debug("Outside market hours, skipping cycle")
        return

    # Merge base tickers with dynamic tickers from universe scanner
    dynamic = load_dynamic_tickers()
    base_set = set(tickers)
    merged = list(tickers) + [t for t in dynamic if t not in base_set]

    now_str = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S ET")
    if merged != tickers:
        logger.info(f"--- Scraping cycle at {now_str} | base={tickers} + dynamic={[t for t in dynamic if t not in base_set]} ---")
    else:
        logger.info(f"--- Scraping cycle at {now_str} | {len(merged)} tickers ---")

    connection = get_connection(db_path)
    try:
        init_db(connection)
    finally:
        connection.close()

    results: dict[str, int | None] = {}
    for i, symbol in enumerate(merged):
        sid = scrape_ticker(
            symbol=symbol,
            days=days,
            db_path=db_path,
            option_range=option_range,
            dry_run=dry_run,
            verbose=verbose,
            skip_raw_json=skip_raw_json,
        )
        results[symbol] = sid
        if i < len(merged) - 1:
            time.sleep(INTER_TICKER_DELAY_SECONDS)

    ok = sum(1 for v in results.values() if v is not None and v > 0)
    logger.info(f"--- Cycle complete: {ok}/{len(merged)} tickers scraped ---")


def start_scheduler(
    tickers: list[str],
    interval_minutes: int = 15,
    days: int = 30,
    db_path: str = DEFAULT_DB_PATH,
    option_range: str = "ALL",
    dry_run: bool = False,
    verbose: bool = False,
    skip_raw_json: bool = True,
) -> None:
    logger.info(
        f"Starting options scraper | tickers={tickers} | "
        f"interval={interval_minutes}m | days={days} | db={db_path} | "
        f"raw_json={'OFF' if skip_raw_json else 'ON'}"
    )
    if dry_run:
        logger.info("DRY RUN mode — no data will be written")

    scheduler = BlockingScheduler()

    trigger = CronTrigger(
        day_of_week="mon-fri",
        hour="4-19",
        minute=f"*/{interval_minutes}",
        timezone=ET,
    )

    scheduler.add_job(
        run_cycle,
        trigger,
        args=[tickers, days, db_path, option_range, dry_run, verbose, skip_raw_json],
        id="options_scraper",
        max_instances=1,
        misfire_grace_time=120,
    )

    # Heartbeat zombie detector — every 5 min during market hours
    heartbeat_trigger = CronTrigger(
        day_of_week="mon-fri",
        hour="4-19",
        minute="*/5",
        timezone=ET,
    )
    scheduler.add_job(
        send_heartbeat_alert,
        heartbeat_trigger,
        args=[db_path],
        id="heartbeat_check",
        max_instances=1,
        misfire_grace_time=300,
    )

    # Token expiry alert — twice daily at 8:00 and 14:00 ET
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
    import argparse

    parser = argparse.ArgumentParser(description="Continuous options data scraper")
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=DEFAULT_TICKERS,
        help=f"Tickers to scrape (default: {' '.join(DEFAULT_TICKERS)})",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Minutes between scrapes (default: 15)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Option chain DTE window (default: 30)",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--option-range",
        default="ALL",
        choices=["ITM", "NTM", "OTM", "ALL"],
        help="Strike range filter (default: ALL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print but do not write to DB",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-ticker contract counts",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scrape cycle and exit (no scheduler)",
    )
    parser.add_argument(
        "--raw-json",
        action="store_true",
        help="Store full API chain_json and raw_json (default: skipped for storage savings)",
    )

    args = parser.parse_args()
    skip_raw = not args.raw_json

    if args.once:
        run_cycle(
            tickers=args.tickers,
            days=args.days,
            db_path=args.db,
            option_range=args.option_range,
            dry_run=args.dry_run,
            verbose=args.verbose,
            skip_raw_json=skip_raw,
        )
    else:
        start_scheduler(
            tickers=args.tickers,
            interval_minutes=args.interval,
            days=args.days,
            db_path=args.db,
            option_range=args.option_range,
            dry_run=args.dry_run,
            verbose=args.verbose,
            skip_raw_json=skip_raw,
        )
