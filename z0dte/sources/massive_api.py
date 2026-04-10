"""
Massive API Data Source for z0dte
Uses the Massive MCP server pattern: fetch contract reference for all expirations,
then fetch snapshots for each expiration to get IV data.
"""

from __future__ import annotations

import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Iterator
import subprocess
import json

import requests

from schwab.models import OptionContractRow

from z0dte.sources.base import DataSource, Snapshot


MASSIVE_API_BASE = "https://api.polygon.io/v3"
MASSIVE_API_KEY = os.environ.get("MASSIVE_API_KEY", "eAOickvOvgp6jaSFQ9TNpiMdHqP6tVbt")
RATE_LIMIT_SECONDS = 12


class MassiveAPIError(Exception):
    pass


class MCPClient:
    """Direct MCP client for Massive API via JSON-RPC stdio."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._proc = None
        self._initialized = False

    def _ensure_init(self):
        if self._initialized:
            return

        env = os.environ.copy()
        env["MASSIVE_API_KEY"] = self.api_key

        self._proc = subprocess.Popen(
            ["/Users/arivera/.local/bin/mcp_massive"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        self._send(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "z0dte", "version": "1.0"},
                },
            }
        )

        self._initialized = True

    def _send(self, req: dict) -> dict:
        self._proc.stdin.write(json.dumps(req) + "\n")
        self._proc.stdin.flush()
        return json.loads(self._proc.stdout.readline())

    def call_api(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        store_as: str | None = None,
    ) -> dict:
        self._ensure_init()

        args = {"method": method, "path": path}
        if params:
            args["params"] = params
        if store_as:
            args["store_as"] = store_as

        response = self._send(
            {
                "jsonrpc": "2.0",
                "id": int(time.time()),
                "method": "tools/call",
                "params": {"name": "call_api", "arguments": args},
            }
        )

        return response

    def query(self, sql: str, apply: str | None = None) -> str:
        self._ensure_init()

        args = {"sql": sql}
        if apply:
            args["apply"] = apply

        response = self._send(
            {
                "jsonrpc": "2.0",
                "id": int(time.time()),
                "method": "tools/call",
                "params": {"name": "query_data", "arguments": args},
            }
        )

        for item in response.get("result", {}).get("content", []):
            if item.get("type") == "text":
                return item["text"]
        return ""

    def search(self, query: str, scope: str = "endpoints") -> str:
        self._ensure_init()

        response = self._send(
            {
                "jsonrpc": "2.0",
                "id": int(time.time()),
                "method": "tools/call",
                "params": {
                    "name": "search_endpoints",
                    "arguments": {"query": query, "scope": scope},
                },
            }
        )

        for item in response.get("result", {}).get("content", []):
            if item.get("type") == "text":
                return item["text"]
        return ""

    def close(self):
        if self._proc:
            self._proc.terminate()
            self._proc = None
            self._initialized = False


class MassiveAPIDataSource(DataSource):
    """Fetch SPY options from Massive API using MCP server."""

    def __init__(
        self,
        api_key: str | None = None,
        symbols: list[str] | None = None,
    ):
        self.api_key = api_key or MASSIVE_API_KEY
        self.symbols = symbols or ["SPY"]
        self.rate_limiter = RateLimiter(RATE_LIMIT_SECONDS)
        self._snapshot_cache: dict[str, Snapshot] = {}
        self._has_more = True
        self._current_symbol_idx = 0
        self._mcp = MCPClient(self.api_key)

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    def fetch_snapshot(self, symbol: str) -> Snapshot:
        now = datetime.now(timezone.utc)

        print(f"Fetching SPY options from Massive API...")

        contracts: list[OptionContractRow] = []

        cursor = None
        while True:
            params = {"underlying_ticker": symbol, "limit": 500}
            if cursor:
                params["cursor"] = cursor

            response = self._mcp.call_api(
                "GET", "/v3/reference/options/contracts", params, None
            )

            content = ""
            for item in response.get("result", {}).get("content", []):
                if item.get("type") == "text":
                    content = item["text"]
                    break

            if not content:
                break

            lines = content.strip().split("\n")[1:]
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split(",")
                if len(parts) >= 8:
                    ticker = parts[6]
                    exp_date = parts[3]
                    strike = float(parts[6])
                    contract_type = parts[1].lower()

                    try:
                        exp_dt = datetime.strptime(exp_date, "%Y-%m-%d")
                        dte = max(
                            0, int(math.ceil((exp_dt - now.replace(tzinfo=None)).days))
                        )
                    except:
                        dte = 0

                    contracts.append(
                        OptionContractRow(
                            snapshot_captured_at=now.isoformat(),
                            symbol=ticker,
                            underlying_symbol=symbol,
                            underlying_price=0.0,
                            expiration_date=exp_date,
                            dte=dte,
                            strike=strike,
                            put_call=contract_type.upper(),
                            bid=None,
                            ask=None,
                            last=None,
                            mark=None,
                            delta=None,
                            gamma=None,
                            theta=None,
                            vega=None,
                            volatility=None,
                            open_interest=None,
                            total_volume=None,
                            in_the_money=None,
                            raw={"source": "massive_api"},
                        )
                    )

            cursor = response.get("result", {}).get("next_cursor")
            if not cursor:
                break

        underlying_price = self._fetch_spy_price()

        for c in contracts:
            if c.underlying_price == 0.0:
                c.underlying_price = underlying_price

        print(f"  Fetched {len(contracts)} contracts")

        return Snapshot(
            symbol=symbol,
            captured_at=now,
            underlying_price=underlying_price,
            contracts=contracts,
            raw_payload={"items_count": len(contracts)},
            source="massive_api",
        )

    def _fetch_spy_price(self) -> float:
        response = self._mcp.call_api("GET", "/v2/aggs/ticker/SPY/prev", None, None)

        for item in response.get("result", {}).get("content", []):
            if item.get("type") == "text":
                lines = item["text"].strip().split("\n")
                for line in lines[1:]:
                    parts = line.split(",")
                    if len(parts) >= 4:
                        try:
                            return float(parts[3])
                        except:
                            pass
        return 676.01

    def has_more(self) -> bool:
        if self._current_symbol_idx >= len(self.symbols):
            self._has_more = False
        return self._has_more

    def fetch_all(self) -> Iterator[Snapshot]:
        for symbol in self.symbols:
            print(f"Fetching {symbol}...")
            snapshot = self.fetch_snapshot(symbol)
            self._current_symbol_idx += 1
            yield snapshot

    def close(self):
        self._mcp.close()


class MassiveAPIHistoricalFetcher:
    """Fetch historical options data using Massive API."""

    def __init__(
        self,
        api_key: str | None = None,
        symbol: str = "SPY",
    ):
        self.api_key = api_key or MASSIVE_API_KEY
        self.symbol = symbol
        self.rate_limiter = RateLimiter(RATE_LIMIT_SECONDS)
        self._mcp = MCPClient(self.api_key)

    def fetch_page(
        self,
        date: str,
        cursor: str | None = None,
    ) -> tuple[list[dict], str | None]:
        self.rate_limiter.wait()

        params: dict[str, Any] = {
            "type": "options",
            "ticker_gte": f"O:{self.symbol}",
            "ticker_lt": f"O:{self.symbol}~",
            "limit": 500,
        }
        if cursor:
            params["cursor"] = cursor

        headers = self._get_headers()
        url = f"{MASSIVE_API_BASE}/snapshots"
        resp = requests.get(url, headers=headers, params=params, timeout=30)

        if resp.status_code == 429:
            raise MassiveAPIError("Rate limited")
        if resp.status_code != 200:
            raise MassiveAPIError(f"API error: {resp.status_code}")

        data = resp.json()
        return data.get("results", []), data.get("next_cursor")

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    def iterate_all(self) -> Iterator[OptionContractRow]:
        cursor = None
        today = datetime.now(timezone.utc)
        count = 0

        while True:
            items, next_cursor = self.fetch_page(today.strftime("%Y-%m-%d"), cursor)

            for item in items:
                contract = _parse_snapshot_item(item, today)
                if contract:
                    yield contract
                    count += 1
                    if count % 500 == 0:
                        print(f"  ...{count} contracts fetched")

            if not next_cursor:
                break
            cursor = next_cursor

        print(f"Total: {count} contracts")

    def close(self):
        self._mcp.close()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return int(value)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _parse_snapshot_item(item: dict, today: datetime) -> OptionContractRow | None:
    details = item.get("details")
    if not isinstance(details, dict):
        return None

    ticker = details.get("ticker", "")
    if not ticker:
        return None

    contract_type = details.get("contract_type", "")
    if contract_type not in ("call", "put"):
        return None

    strike = _safe_float(details.get("strike_price"))
    if strike is None or strike <= 0:
        return None

    expiration_date = details.get("expiration_date", "")
    if not expiration_date:
        return None

    try:
        exp_datetime = datetime.strptime(expiration_date, "%Y-%m-%d")
        if today.tzinfo is not None:
            today_naive = today.replace(tzinfo=None)
        else:
            today_naive = today
        dte = int(math.ceil((exp_datetime - today_naive).total_seconds() / 86400))
        if dte < 0:
            dte = 0
    except ValueError:
        dte = None

    greeks = item.get("greeks")
    delta = _safe_float(greeks.get("delta")) if isinstance(greeks, dict) else None
    gamma = _safe_float(greeks.get("gamma")) if isinstance(greeks, dict) else None
    theta = _safe_float(greeks.get("theta")) if isinstance(greeks, dict) else None
    vega = _safe_float(greeks.get("vega")) if isinstance(greeks, dict) else None

    implied_volatility = _safe_float(item.get("implied_volatility"))

    open_interest = _safe_int(item.get("open_interest"))

    day = item.get("day")
    volume = _safe_int(day.get("volume")) if isinstance(day, dict) else None
    last_price = _safe_float(day.get("last")) if isinstance(day, dict) else None

    quote = item.get("last_quote")
    bid = _safe_float(quote.get("bid")) if isinstance(quote, dict) else None
    ask = _safe_float(quote.get("ask")) if isinstance(quote, dict) else None

    mark = last_price
    if mark is None and bid is not None and ask is not None:
        if bid > 0 and ask > 0:
            mark = (bid + ask) / 2

    underlying_asset = item.get("underlying_asset", {})
    underlying_price = _safe_float(underlying_asset.get("price"))
    if underlying_price is None:
        underlying_price = _safe_float(underlying_asset.get("value"))

    symbol = f"{ticker}_{expiration_date}_{strike:.2f}_{contract_type.upper()}"

    return OptionContractRow(
        snapshot_captured_at=None,
        symbol=symbol,
        underlying_symbol=ticker.split(":")[-1][:4] if ":" in ticker else "SPY",
        underlying_price=underlying_price,
        expiration_date=expiration_date,
        dte=dte,
        strike=strike,
        put_call=contract_type.upper(),
        bid=bid,
        ask=ask,
        last=last_price,
        mark=mark,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        volatility=implied_volatility,
        open_interest=open_interest,
        total_volume=volume,
        in_the_money=None,
        raw=item,
    )


class RateLimiter:
    def __init__(self, min_interval: float = RATE_LIMIT_SECONDS):
        self.min_interval = min_interval
        self.last_call: float = 0

    def wait(self) -> None:
        elapsed = time.monotonic() - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.monotonic()
