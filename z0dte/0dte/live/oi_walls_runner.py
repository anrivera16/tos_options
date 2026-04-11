from __future__ import annotations

import hashlib
import importlib
import os
import signal
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from psycopg.types.json import Json
from z0dte.db.connection import get_connection

import requests
from dotenv import load_dotenv
from discord.webhook import send_message

ET = ZoneInfo("US/Eastern")
MASSIVE_REST_BASE = "https://api.polygon.io"


@dataclass
class ContractRef:
    ticker: str
    strike: float
    put_call: str
    expiration_date: date


class OIWallsLiveRunner:
    def __init__(
        self,
        symbol: str,
        interval_minutes: int,
        top_n: int = 3,
        dry_run: bool = False,
        discord: bool = False,
        max_contracts: int = 120,
        strike_window_pct: float = 0.05,
        debug: bool = False,
        persist_db: bool = False,
        db_dedupe_window_min: int = 5,
    ):
        self.symbol = symbol.upper()
        self.interval_seconds = max(1, interval_minutes) * 60
        self.top_n = max(1, top_n)
        self.dry_run = dry_run
        self.discord = discord
        self.max_contracts = max(10, max_contracts)
        self.strike_window_pct = max(0.01, strike_window_pct)
        self.debug = debug
        self.persist_db = bool(persist_db)
        self.db_dedupe_window_min = max(1, int(db_dedupe_window_min))
        self.running = True
        self.iteration = 0
        self.errors = 0
        self.last_message = ""
        self._last_call_ts = 0.0
        self._last_ref_stats = {"seen": 0, "kept": 0}

        load_dotenv()
        self.api_key = os.getenv("MASSIVE_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("Missing MASSIVE_API_KEY in environment.")

        self._oi_module = importlib.import_module("z0dte.0dte.signals.oi_walls")
        self.conn = None
        if self.persist_db and not self.dry_run:
            self.conn = get_connection()
            self._ensure_notifications_table()

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        self.running = False

    def _ensure_notifications_table(self) -> None:
        if self.conn is None:
            return
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS oi_walls_notifications (
                id                  BIGSERIAL PRIMARY KEY,
                symbol              TEXT NOT NULL,
                captured_at_bucket  TIMESTAMPTZ NOT NULL,
                message_hash        TEXT NOT NULL,
                message_preview     TEXT,
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (symbol, captured_at_bucket, message_hash)
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_oi_walls_notifications_symbol_time
                ON oi_walls_notifications (symbol, captured_at_bucket DESC)
            """
        )
        self.conn.commit()

    def _call_api_json(
        self, method: str, path: str, params: dict | None = None
    ) -> dict:
        query = dict(params or {})
        query["apiKey"] = self.api_key
        delay = 0.25

        for attempt in range(4):
            now = time.time()
            sleep_for = max(0.0, self._last_call_ts + 0.25 - now)
            if sleep_for:
                time.sleep(sleep_for)
            self._last_call_ts = time.time()

            try:
                response = requests.request(
                    method=method,
                    url=f"{MASSIVE_REST_BASE}{path}",
                    params=query,
                    timeout=30,
                )
                if response.status_code == 429 and attempt < 3:
                    time.sleep(delay)
                    delay *= 2
                    continue
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass

            if attempt < 3:
                time.sleep(delay)
                delay *= 2

        return {}

    def _fetch_spot(self) -> tuple[float, dict]:
        index_symbols = {"SPX", "NDX", "RUT", "VIX", "DJI"}
        spot_symbols = [self.symbol]
        if self.symbol in index_symbols:
            spot_symbols = [f"I:{self.symbol}", self.symbol]

        for spot_symbol in spot_symbols:
            payload = self._call_api_json(
                "GET", f"/v2/aggs/ticker/{spot_symbol}/prev", None
            )
            results = payload.get("results") or []
            if self.debug:
                print(
                    f"[debug] spot_symbol={spot_symbol} endpoint=/v2/aggs/ticker/{spot_symbol}/prev results={len(results)}"
                )
            if results:
                return float(
                    results[0].get("c") or results[0].get("vw") or 0.0
                ), payload

        return 0.0, {}

    def _fetch_active_contracts_for_type(
        self, spot: float, contract_type: str, target_count: int
    ) -> tuple[list[ContractRef], int]:
        contracts: list[ContractRef] = []
        cursor = None
        seen = 0

        while len(contracts) < target_count:
            params = {
                "underlying_ticker": self.symbol,
                "expired": "false",
                "limit": 250,
                "sort": "expiration_date",
                "order": "asc",
                "contract_type": contract_type.lower(),
            }
            if cursor:
                params["cursor"] = cursor

            payload = self._call_api_json(
                "GET", "/v3/reference/options/contracts", params
            )
            rows = payload.get("results") or []
            if not rows:
                break

            for row in rows:
                seen += 1
                ticker = row.get("ticker")
                strike = row.get("strike_price")
                exp = row.get("expiration_date")
                ctype = (row.get("contract_type") or "").upper()
                if (
                    not ticker
                    or strike is None
                    or not exp
                    or ctype not in {"CALL", "PUT"}
                ):
                    continue
                try:
                    strike_f = float(strike)
                    exp_d = date.fromisoformat(exp)
                except Exception:
                    continue
                if spot > 0 and abs(strike_f - spot) / spot > self.strike_window_pct:
                    continue
                contracts.append(
                    ContractRef(
                        ticker=ticker,
                        strike=strike_f,
                        put_call=ctype,
                        expiration_date=exp_d,
                    )
                )
                if len(contracts) >= target_count:
                    break

            if len(contracts) >= target_count:
                break
            cursor = payload.get("next_cursor")
            if not cursor:
                break

        return contracts, seen

    def _fetch_active_contracts(self, spot: float) -> list[ContractRef]:
        call_target = max(1, self.max_contracts // 2)
        put_target = max(1, self.max_contracts - call_target)

        calls, seen_calls = self._fetch_active_contracts_for_type(
            spot, "CALL", call_target
        )
        puts, seen_puts = self._fetch_active_contracts_for_type(spot, "PUT", put_target)

        contracts = calls + puts
        self._last_ref_stats = {
            "seen": seen_calls + seen_puts,
            "kept": len(contracts),
            "calls": len(calls),
            "puts": len(puts),
        }
        return contracts

    def _fetch_snapshot_contracts(
        self, contracts: list[ContractRef], spot: float
    ) -> list[dict]:
        today = datetime.now(ET).date()
        out: list[dict] = []

        for contract in contracts:
            payload = self._call_api_json(
                "GET",
                f"/v3/snapshot/options/{self.symbol}/{contract.ticker}",
                None,
            )
            result = payload.get("results") or {}
            greeks = result.get("greeks") or {}
            quote = result.get("last_quote") or {}
            day = result.get("day") or {}

            out.append(
                {
                    "symbol": contract.ticker,
                    "expiration_date": contract.expiration_date,
                    "strike": contract.strike,
                    "put_call": contract.put_call,
                    "dte": max(0, (contract.expiration_date - today).days),
                    "open_interest": result.get("open_interest") or 0,
                    "total_volume": result.get("day", {}).get("volume") or 0,
                    "underlying_price": spot,
                    "bid": quote.get("bid"),
                    "ask": quote.get("ask"),
                    "last": day.get("close"),
                    "delta": greeks.get("delta"),
                    "gamma": greeks.get("gamma"),
                    "raw_json": result,
                }
            )

        return out

    def _debug_transport_checks(self) -> None:
        refs = self._fetch_active_contracts(0.0)
        seen = self._last_ref_stats.get("seen", 0)
        print(
            f"[debug] transport contracts endpoint parseable=True seen={seen} kept={len(refs)} endpoint=/v3/reference/options/contracts"
        )
        if not refs:
            print("[debug] transport snapshot check skipped: no contract tickers")
        pass

        payload = self._call_api_json(
            "GET", f"/v3/snapshot/options/{self.symbol}/{refs[0].ticker}", None
        )
        result = payload.get("results") or {}
        has_oi = "open_interest" in result
        has_quote = bool(result.get("last_quote"))
        has_greeks = bool(result.get("greeks"))
        print(
            "[debug] transport snapshot endpoint parseable="
            f"{bool(result)} has_open_interest={has_oi} has_quote={has_quote} has_greeks={has_greeks} "
            f"endpoint=/v3/snapshot/options/{self.symbol}/<optionContract>"
        )

    def _format_wall(self, wall: dict, key: str) -> str:
        strike = wall.get("strike", 0)
        oi = int(wall.get(key, 0))
        dist = float(wall.get("distance_from_spot", 0.0)) * 100
        return f"- {strike:.0f}: OI {oi:,} ({dist:+.2f}%)"

    def _format_message(
        self,
        spot: float,
        summary: dict,
        captured_at: datetime,
        classified_strikes: list[dict],
    ) -> str:
        top_calls = summary.get("top_call_walls", [])
        top_puts = summary.get("top_put_walls", [])
        if not top_puts:
            top_puts = sorted(
                [s for s in classified_strikes if (s.get("put_oi") or 0) > 0],
                key=lambda s: s.get("put_oi", 0),
                reverse=True,
            )[: self.top_n]
        pin_range = summary.get("pin_range")

        lines = [
            f"**OI Walls | {self.symbol} | {captured_at.strftime('%Y-%m-%d %H:%M:%S ET')}**",
            f"Spot: ${spot:.2f}",
            "",
            "**Top Call Walls**",
        ]
        lines.extend([self._format_wall(w, "call_oi") for w in top_calls] or ["- none"])
        lines.extend(["", "**Top Put Walls**"])
        lines.extend([self._format_wall(w, "put_oi") for w in top_puts] or ["- none"])

        if pin_range:
            lines.append("")
            lines.append(
                f"**Pin Range** {pin_range['lower_bound']:.0f} - {pin_range['upper_bound']:.0f} (width {pin_range['width']:.0f}, {pin_range['width_pct']:.2%})"
            )
        else:
            lines.extend(["", "**Pin Range** none"])

        call_oi = sum(int(s.get("call_oi", 0)) for s in classified_strikes)
        put_oi = sum(int(s.get("put_oi", 0)) for s in classified_strikes)
        bias = "neutral"
        if call_oi > put_oi * 1.2:
            bias = "upside pressure"
        elif put_oi > call_oi * 1.2:
            bias = "downside pressure"
        lines.extend(["", f"**Bias** {bias} (calls {call_oi:,} vs puts {put_oi:,})"])

        return "\n".join(lines)

    def _persist_snapshot(self, captured_at: datetime, spot: float) -> int:
        if self.conn is None:
            return 0
        row = self.conn.execute(
            """
            INSERT INTO snapshots_0dte
                (symbol, captured_at, underlying_price, source, is_backtest, chain_json)
            VALUES (%s, %s, %s, %s, FALSE, %s)
            RETURNING id
            """,
            [
                self.symbol,
                captured_at,
                spot,
                "massive_api_live",
                Json({"runner": "oi_walls"}),
            ],
        ).fetchone()
        return int(row["id"])

    def _persist_contracts(
        self, snapshot_id: int, contracts: list[dict], spot: float
    ) -> None:
        if self.conn is None or not contracts:
            return
        rows = [
            {
                "snapshot_id": snapshot_id,
                "symbol": c.get("symbol"),
                "underlying_symbol": self.symbol,
                "underlying_price": spot,
                "expiration_date": c.get("expiration_date"),
                "dte": c.get("dte"),
                "strike": c.get("strike"),
                "put_call": c.get("put_call"),
                "bid": c.get("bid"),
                "ask": c.get("ask"),
                "last": c.get("last"),
                "delta": c.get("delta"),
                "gamma": c.get("gamma"),
                "open_interest": c.get("open_interest") or 0,
                "total_volume": c.get("total_volume") or 0,
                "raw_json": Json(c.get("raw_json") or {}),
            }
            for c in contracts
        ]
        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO contracts_0dte (
                    snapshot_id, symbol, underlying_symbol, underlying_price,
                    expiration_date, dte, strike, put_call,
                    bid, ask, last, delta, gamma,
                    open_interest, total_volume, raw_json
                )
                VALUES (
                    %(snapshot_id)s, %(symbol)s, %(underlying_symbol)s, %(underlying_price)s,
                    %(expiration_date)s, %(dte)s, %(strike)s, %(put_call)s,
                    %(bid)s, %(ask)s, %(last)s, %(delta)s, %(gamma)s,
                    %(open_interest)s, %(total_volume)s, %(raw_json)s
                )
                """,
                rows,
            )

    def _persist_oi_signal(self, snapshot_id: int) -> None:
        if self.conn is None:
            return
        self._oi_module.OIWalls().compute(snapshot_id, self.conn)

    def _captured_at_bucket(self, captured_at: datetime) -> datetime:
        minute = (
            captured_at.minute // self.db_dedupe_window_min
        ) * self.db_dedupe_window_min
        return captured_at.replace(minute=minute, second=0, microsecond=0)

    def _record_notification(self, captured_at: datetime, message: str) -> bool:
        if self.conn is None:
            return True
        message_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
        bucket = self._captured_at_bucket(captured_at)
        window_start = captured_at - timedelta(minutes=self.db_dedupe_window_min)
        existing = self.conn.execute(
            """
            SELECT 1
            FROM oi_walls_notifications
            WHERE symbol = %s
              AND message_hash = %s
              AND captured_at_bucket >= %s
            LIMIT 1
            """,
            [self.symbol, message_hash, window_start],
        ).fetchone()
        if existing:
            return False
        self.conn.execute(
            """
            INSERT INTO oi_walls_notifications
                (symbol, captured_at_bucket, message_hash, message_preview)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (symbol, captured_at_bucket, message_hash) DO NOTHING
            """,
            [self.symbol, bucket, message_hash, message[:500]],
        )
        return True

    def run_once(self) -> tuple[str | None, bool]:
        captured_at = datetime.now(ET)
        spot, spot_payload = self._fetch_spot()

        if self.debug:
            spot_results = spot_payload.get("results") or []
            print(
                f"[debug] spot=${spot:.2f} results={len(spot_results)} endpoint=/v2/aggs/ticker/{self.symbol}/prev"
            )

        if spot <= 0:
            if self.debug:
                print("[debug] no data reason: spot<=0 or unparseable spot payload")
                self._debug_transport_checks()
            return None, False

        refs = self._fetch_active_contracts(spot)
        contracts = self._fetch_snapshot_contracts(refs, spot)

        aggregate = self._oi_module.aggregate_oi_by_strike
        classify = self._oi_module.classify_walls
        identify = self._oi_module.identify_top_walls

        strikes = aggregate(contracts, spot)
        classified = classify(strikes, spot)
        summary = identify(classified, top_n=self.top_n)

        if self.persist_db and not self.dry_run and self.conn is not None:
            snapshot_id = self._persist_snapshot(captured_at, spot)
            self._persist_contracts(snapshot_id, contracts, spot)
            self._persist_oi_signal(snapshot_id)

        if self.debug:
            with_oi = sum(1 for c in contracts if (c.get("open_interest") or 0) > 0)
            seen = self._last_ref_stats.get("seen", 0)
            kept = self._last_ref_stats.get("kept", len(refs))
            call_wall_count = sum(
                1 for s in classified if s.get("wall_type") == "call_wall"
            )
            put_wall_count = sum(
                1 for s in classified if s.get("wall_type") == "put_wall"
            )
            mixed_count = sum(1 for s in classified if s.get("wall_type") == "mixed")
            total_call_oi = sum(int(s.get("call_oi", 0)) for s in classified)
            total_put_oi = sum(int(s.get("put_oi", 0)) for s in classified)
            ref_calls = self._last_ref_stats.get("calls", 0)
            ref_puts = self._last_ref_stats.get("puts", 0)
            print(
                f"[debug] contracts_seen={seen} contracts_after_filter={kept} refs_calls={ref_calls} refs_puts={ref_puts} snapshots={len(contracts)} snapshots_with_oi={with_oi} strikes_aggregated={len(strikes)}"
            )
            print(
                f"[debug] wall_types call={call_wall_count} put={put_wall_count} mixed={mixed_count} total_call_oi={total_call_oi} total_put_oi={total_put_oi}"
            )
            if not strikes:
                print(
                    "[debug] no data reason: no strikes passed OI aggregation filters (dte/range/min_oi_threshold)"
                )

        message = self._format_message(spot, summary, captured_at, classified)
        should_send = message != self.last_message
        if (
            should_send
            and self.persist_db
            and not self.dry_run
            and self.conn is not None
        ):
            should_send = self._record_notification(captured_at, message)
        if self.conn is not None and self.persist_db and not self.dry_run:
            self.conn.commit()
        return message, should_send

    def run_loop(self, max_iterations: int | None = None) -> None:
        print(
            f"OI walls live runner | {self.symbol} | interval {self.interval_seconds // 60}m"
        )
        while self.running:
            self.iteration += 1
            try:
                message, should_send = self.run_once()
                if not message:
                    print(f"[{self.iteration}] no data")
                else:
                    print(message)
                    if self.discord and not self.dry_run and should_send:
                        send_message(message)
                        self.last_message = message
            except Exception as exc:
                self.errors += 1
                if self.conn is not None:
                    self.conn.rollback()
                print(f"[{self.iteration}] error: {exc}")

            if max_iterations is not None and self.iteration >= max_iterations:
                break
            if not self.running:
                break

            remaining = self.interval_seconds
            while remaining > 0 and self.running:
                sleep_for = min(10, remaining)
                time.sleep(sleep_for)
                remaining -= sleep_for

        if self.conn is not None:
            self.conn.close()
        return
