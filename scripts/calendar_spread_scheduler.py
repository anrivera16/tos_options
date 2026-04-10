from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from psycopg.types.json import Json
from zoneinfo import ZoneInfo

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from z0dte.sources.massive_api import MassiveAPIDataSource
from z0dte.calendar_spread.signals.calendar_spread_violation import (
    CalendarSpreadViolation,
)
from z0dte.calendar_spread.signals.calendar_spread_opportunity import (
    CalendarSpreadOpportunity,
)
from z0dte.calendar_spread.strategies.calendar_spread_strategy import (
    CalendarSpreadStrategy,
)
from z0dte.db.connection import get_connection
from discord.webhook import send_message

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

ET = ZoneInfo("US/Eastern")
SYMBOLS = ["SPY", "QQQ"]


def is_market_hours() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    if now.hour < 9 or now.hour >= 16:
        return False
    if now.hour == 9 and now.minute < 30:
        return False
    return True


def _normalize_contract(contract: Any) -> dict:
    return {
        "symbol": contract.symbol,
        "underlying_symbol": contract.underlying_symbol,
        "underlying_price": contract.underlying_price,
        "expiration_date": contract.expiration_date,
        "dte": contract.dte,
        "strike": contract.strike,
        "put_call": contract.put_call,
        "bid": contract.bid,
        "ask": contract.ask,
        "last": contract.last,
        "mark": contract.mark,
        "delta": contract.delta,
        "gamma": contract.gamma,
        "theta": contract.theta,
        "vega": contract.vega,
        "volatility": contract.volatility,
        "open_interest": contract.open_interest,
        "total_volume": contract.total_volume,
        "in_the_money": contract.in_the_money,
        "raw_json": Json(contract.raw) if contract.raw else None,
    }


def _store_snapshot(conn: Any, snapshot: Any) -> int:
    now = datetime.now(ET)
    result = conn.execute(
        """
        INSERT INTO snapshots_0dte (symbol, captured_at, underlying_price, source, is_backtest)
        VALUES (%s, %s, %s, %s, FALSE)
        ON CONFLICT (symbol, captured_at, is_backtest) DO UPDATE SET id = snapshots_0dte.id
        RETURNING id
        """,
        [
            snapshot.symbol,
            snapshot.captured_at,
            snapshot.underlying_price,
            "massive_api_live",
        ],
    )
    snapshot_id = result.fetchone()["id"]

    for contract in snapshot.contracts:
        norm = _normalize_contract(contract)
        conn.execute(
            """
            INSERT INTO contracts_0dte (
                snapshot_id, symbol, underlying_symbol, underlying_price,
                expiration_date, dte, strike, put_call,
                bid, ask, last, mark,
                delta, gamma, theta, vega, volatility,
                open_interest, total_volume, in_the_money, raw_json
            )
            VALUES (
                %(snapshot_id)s, %(symbol)s, %(underlying_symbol)s, %(underlying_price)s,
                %(expiration_date)s, %(dte)s, %(strike)s, %(put_call)s,
                %(bid)s, %(ask)s, %(last)s, %(mark)s,
                %(delta)s, %(gamma)s, %(theta)s, %(vega)s, %(volatility)s,
                %(open_interest)s, %(total_volume)s, %(in_the_money)s, %(raw_json)s
            )
            ON CONFLICT DO NOTHING
            """,
            {"snapshot_id": snapshot_id, **norm},
        )

    conn.commit()
    return snapshot_id


def _compute_signals(snapshot_id: int, symbol: str, conn: Any) -> dict:
    violation_signal = CalendarSpreadViolation()
    violation_signal.compute(snapshot_id, conn)

    opp_signal = CalendarSpreadOpportunity()
    opp_signal.compute(snapshot_id, conn)

    strategy = CalendarSpreadStrategy()
    return strategy.evaluate(snapshot_id, conn)


def _format_discord_entry(
    symbol: str,
    position_data: dict,
    signal_score: float,
    confidence: float,
    trade_id: str,
) -> str:
    return (
        f"**Calendar Spread ENTRY**\n"
        f"Symbol: {symbol}\n"
        f"Strike: {position_data['strike']}\n"
        f"Front Expiry: {position_data['front_expiry']}\n"
        f"Back Expiry: {position_data['back_expiry']}\n"
        f"Entry Price: ${position_data['entry_price']:.2f}\n"
        f"Max Profit: ${position_data['max_profit']:.2f}\n"
        f"Score: {signal_score:.2f} | Confidence: {confidence:.2f}\n"
        f"Trade ID: `{trade_id}`"
    )


def _format_discord_exit(
    symbol: str,
    reason: str,
    trade_id: str,
    pnl: float,
    pnl_pct: float,
) -> str:
    return (
        f"**Calendar Spread EXIT**\n"
        f"Symbol: {symbol}\n"
        f"Reason: {reason}\n"
        f"P&L: ${pnl:+.2f} ({pnl_pct:+.1%})\n"
        f"Trade ID: `{trade_id}`"
    )


def _check_and_send_discord(
    symbol: str,
    action: str,
    trade_id: str,
    position_data: dict | None,
    reason: str | None,
    signal_score: float,
    confidence: float,
    pnl: float,
    pnl_pct: float,
    conn: Any,
) -> None:
    notification_type = "entry" if action == "OPEN" else "exit"

    existing = conn.execute(
        """
        SELECT id FROM calendar_signal_notifications
        WHERE trade_id = %s AND notification_type = %s
        """,
        [trade_id, notification_type],
    ).fetchone()

    if existing:
        logger.debug(f"Discord notification already sent for {action}: {trade_id}")
        return

    if action == "OPEN" and position_data:
        msg = _format_discord_entry(
            symbol, position_data, signal_score, confidence, trade_id
        )
    elif action == "CLOSE":
        msg = _format_discord_exit(symbol, reason or "unknown", trade_id, pnl, pnl_pct)
    else:
        return

    conn.execute(
        """
        INSERT INTO calendar_signal_notifications 
            (trade_id, notification_type, symbol, opportunity_score, confidence, message_preview)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (trade_id, notification_type) DO NOTHING
        """,
        [trade_id, notification_type, symbol, signal_score, confidence, msg[:500]],
    )
    conn.commit()

    send_message(msg)
    logger.info(f"Discord notification sent for {action}: {symbol}")


def _send_summary_to_discord(conn: Any) -> None:
    now = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")

    try:
        rows = conn.execute(
            """
            SELECT trade_id, symbol, strike, front_expiry, back_expiry,
                   entry_price, current_pnl, current_pnl_pct, entry_timestamp,
                   entry_opportunity_id
            FROM calendar_spread_trades
            WHERE status = 'open'
            ORDER BY entry_timestamp DESC
            """,
        ).fetchall()

        if not rows:
            send_message(f"**Calendar Spread Status** | {now}\nNo open positions.")
            logger.info("Discord summary sent: no open positions")
            return

        lines = [f"**Calendar Spread Status** | {now}", ""]
        for row in rows:
            pnl = row["current_pnl"] or 0.0
            pnl_pct = row["current_pnl_pct"] or 0.0
            days = (datetime.now(ET) - row["entry_timestamp"]).days

            emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(f"{emoji} **{row['symbol']}** {row['strike']:.0f}")
            lines.append(
                f"   {row['front_expiry'].strftime('%m/%d')} / {row['back_expiry'].strftime('%m/%d')} | "
                f"Entry: ${row['entry_price']:.2f} | P&L: ${pnl:+.2f} ({pnl_pct:+.1%}) | "
                f"Held: {days}d"
            )

        send_message("\n".join(lines))
        logger.info(f"Discord summary sent: {len(rows)} open positions")
    except Exception as e:
        logger.error(f"Failed to send Discord summary: {e}")


def run_cycle(send_discord: bool = False) -> None:
    if not is_market_hours():
        logger.info("Outside market hours, skipping cycle")
        return

    logger.info(
        f"Starting calendar spread cycle at {datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}"
    )

    try:
        conn = get_connection()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return

    try:
        source = MassiveAPIDataSource(symbols=SYMBOLS)

        for snapshot in source.fetch_all():
            logger.info(
                f"Processing {snapshot.symbol}: {len(snapshot.contracts)} contracts"
            )

            snapshot_id = _store_snapshot(conn, snapshot)
            logger.info(f"Stored snapshot {snapshot_id} for {snapshot.symbol}")

            result = _compute_signals(snapshot_id, snapshot.symbol, conn)
            logger.info(
                f"{snapshot.symbol}: action={result['action']}, reason={result['reason']}"
            )

            if send_discord and result["action"] in ("OPEN", "CLOSE"):
                opportunity = conn.execute(
                    """
                    SELECT opportunity_score, confidence FROM signal_calendar_opportunities
                    WHERE snapshot_id = %s
                    ORDER BY captured_at DESC LIMIT 1
                    """,
                    [snapshot_id],
                ).fetchone()

                opp_score = (
                    float(opportunity["opportunity_score"]) if opportunity else 0.0
                )
                opp_conf = float(opportunity["confidence"]) if opportunity else 0.0

                _check_and_send_discord(
                    symbol=snapshot.symbol,
                    action=result["action"],
                    trade_id=result.get("trade_id", ""),
                    position_data=result.get("position_data"),
                    reason=result.get("reason"),
                    signal_score=result.get("signal_score", opp_score),
                    confidence=opp_conf,
                    pnl=result.get("final_pnl", 0.0),
                    pnl_pct=result.get("final_pnl_pct", 0.0),
                    conn=conn,
                )

        if send_discord:
            _send_summary_to_discord(conn)

    except Exception as e:
        logger.exception(f"Error in cycle: {e}")
    finally:
        conn.close()


def start_scheduler(send_discord: bool = False) -> None:
    logger.info(
        f"Starting calendar spread scheduler (Discord: {'ON' if send_discord else 'OFF'})"
    )

    scheduler = BlockingScheduler()

    trigger = CronTrigger(
        day_of_week="mon-fri",
        hour="9-15",
        minute="0,15,30,45",
        timezone=ET,
    )

    scheduler.add_job(run_cycle, trigger, args=[send_discord], id="calendar_spread_job")
    scheduler.add_job(
        run_cycle,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=30, timezone=ET),
        args=[send_discord],
        id="calendar_spread_open",
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
        sys.exit(0)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Calendar Spread Scheduler")
    parser.add_argument("--discord", action="store_true", help="Send alerts to Discord")
    args = parser.parse_args()

    start_scheduler(send_discord=args.discord)
