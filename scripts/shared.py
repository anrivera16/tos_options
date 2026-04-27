"""
Shared utilities for tos_options scheduled scripts.

Centralizes market hours, DB helpers, heartbeat monitoring,
and token expiry alerts to avoid duplication across
options_scraper, live_scanner, and spread_hunter.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ET = ZoneInfo("US/Eastern")

# Trading window — inclusive open, exclusive close.
# Covers pre-market (4:00 AM ET) through after-hours (8:00 PM ET).
MARKET_OPEN_HOUR = 4
MARKET_CLOSE_HOUR = 20

# Heartbeat stale threshold in minutes
HEARTBEAT_STALE_MINUTES = 15

# Token warning threshold in days
TOKEN_EXPIRY_WARNING_DAYS = 2


# ---------------------------------------------------------------------------
# Market hours
# ---------------------------------------------------------------------------

def is_market_hours() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    if now.hour < MARKET_OPEN_HOUR or now.hour >= MARKET_CLOSE_HOUR:
        return False
    return True


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


# ---------------------------------------------------------------------------
# Heartbeat / zombie detector
# ---------------------------------------------------------------------------

def check_scraper_heartbeat(db_url: str | None = None, stale_minutes: int = HEARTBEAT_STALE_MINUTES) -> str | None:
    """
    Check the DB for the latest snapshot timestamp.  Returns a warning
    message string if the heartbeat is stale, or None if everything is OK.
    """
    url = db_url or get_db_url()
    if not is_postgres(url):
        return None  # only works with postgres

    try:
        import psycopg
        conn = psycopg.connect(url)
        try:
            row = conn.execute(
                "SELECT MAX(captured_at) FROM snapshots"
            ).fetchone()
            if not row or not row[0]:
                return "No snapshots found in DB at all"
            # captured_at is stored as ISO text
            last_ts = datetime.fromisoformat(row[0])
            now_utc = datetime.now(ZoneInfo("UTC"))
            # captured_at may or may not have tzinfo — treat as UTC
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=ZoneInfo("UTC"))
            age_minutes = (now_utc - last_ts).total_seconds() / 60
            if age_minutes > stale_minutes:
                return (
                    f"Scraper heartbeat stale: last snapshot was "
                    f"{age_minutes:.0f} min ago (threshold {stale_minutes} min). "
                    f"Last: {row[0]}"
                )
        finally:
            conn.close()
    except Exception as exc:
        return f"Heartbeat check failed (DB error): {exc}"
    return None


def send_heartbeat_alert(db_url: str | None = None) -> None:
    """
    Run heartbeat check and post to Discord if stale.
    Call this from a scheduled job — it won't raise on failure.
    """
    if not is_market_hours():
        return
    warning = check_scraper_heartbeat(db_url)
    if warning:
        try:
            from discord.webhook import send_message
            send_message(f"HEARTBEAT WARNING: {warning}")
            logger.warning(f"Discord heartbeat alert sent: {warning}")
        except Exception as exc:
            logger.error(f"Failed to send heartbeat Discord alert: {exc}")


# ---------------------------------------------------------------------------
# Token expiry checker
# ---------------------------------------------------------------------------

def check_token_expiry(token_dir: str | Path | None = None) -> str | None:
    """
    Check Schwab token file modification time as a proxy for refresh
    token age.  Returns a warning message if token is nearing expiry,
    or None if OK.
    """
    token_path = Path(token_dir or os.environ.get("SCHWAB_TOKEN_DIR", "/root/.schwabdev"))
    # schwabdev stores tokens as JSON — use the newest file's mtime
    if not token_path.exists():
        return f"Token directory not found: {token_path}"

    token_files = list(token_path.glob("*.json"))
    if not token_files:
        return f"No token files found in {token_path}"

    newest = max(token_files, key=lambda p: p.stat().st_mtime)
    mtime = datetime.fromtimestamp(newest.stat().st_mtime)
    now = datetime.now()
    age_days = (now - mtime).days

    if age_days >= 5:  # Schwab tokens expire in ~7 days
        remaining = 7 - age_days
        if remaining <= TOKEN_EXPIRY_WARNING_DAYS:
            return (
                f"Schwab token nearing expiry: token file is {age_days} days old "
                f"(~{remaining} days remaining). Refresh with: "
                f"docker compose run --rm -it cli auth --prompt"
            )
    return None


def send_token_alert(token_dir: str | Path | None = None) -> None:
    """
    Check token expiry and post to Discord if nearing expiry.
    Idempotent — call once per day from any scheduler.
    """
    warning = check_token_expiry(token_dir)
    if warning:
        try:
            from discord.webhook import send_message
            send_message(f"TOKEN WARNING: {warning}")
            logger.warning(f"Discord token alert sent: {warning}")
        except Exception as exc:
            logger.error(f"Failed to send token Discord alert: {exc}")
