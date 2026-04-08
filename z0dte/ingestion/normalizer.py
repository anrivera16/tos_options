from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from schwab.models import OptionContractRow

if TYPE_CHECKING:
    from z0dte.sources.base import Snapshot


def normalize_snapshot_for_db(snapshot: Snapshot) -> dict:
    return {
        "symbol": snapshot.symbol,
        "captured_at": snapshot.captured_at,
        "underlying_price": snapshot.underlying_price,
        "source": snapshot.source,
        "is_backtest": snapshot.source == "csv_backtest",
        "chain_json": json.dumps(snapshot.raw_payload) if snapshot.raw_payload else None,
    }


def _extract_volume_at_bid(raw: dict | None) -> int | None:
    if not raw:
        return None
    if "bidAskSize" in raw:
        sizes = raw["bidAskSize"]
        if isinstance(sizes, dict):
            return int(sizes.get("bidSize", 0))
    return None


def _extract_volume_at_ask(raw: dict | None) -> int | None:
    if not raw:
        return None
    if "bidAskSize" in raw:
        sizes = raw["bidAskSize"]
        if isinstance(sizes, dict):
            return int(sizes.get("askSize", 0))
    return None


def normalize_contract_for_db(contract: OptionContractRow, snapshot_id: int) -> dict:
    return {
        "snapshot_id": snapshot_id,
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
        "volume_at_bid": _extract_volume_at_bid(contract.raw),
        "volume_at_ask": _extract_volume_at_ask(contract.raw),
        "raw_json": json.dumps(contract.raw) if contract.raw else None,
    }
