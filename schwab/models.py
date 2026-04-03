from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass
class OptionContractRow:
    snapshot_captured_at: str | None
    symbol: str
    underlying_symbol: str
    underlying_price: float | None
    expiration_date: str
    dte: int | None
    strike: float
    put_call: str
    bid: float | None
    ask: float | None
    last: float | None
    mark: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    volatility: float | None
    open_interest: int | None
    total_volume: int | None
    in_the_money: bool | None
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _split_expiration_key(expiration_key: str) -> tuple[str, int | None]:
    if ":" not in expiration_key:
        return expiration_key, None
    expiration_date, dte = expiration_key.split(":", 1)
    return expiration_date, _safe_int(dte)


def _first_non_null_float(*values: Any) -> float | None:
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return None


def flatten_option_chain(chain_data: dict[str, Any], symbol: str) -> list[OptionContractRow]:
    underlying_quote = chain_data.get("underlying") or {}
    quote_section = underlying_quote.get("quote") if isinstance(underlying_quote, dict) else {}
    if not quote_section and isinstance(underlying_quote, dict):
        quote_section = underlying_quote
    underlying_price = _first_non_null_float(
        (quote_section or {}).get("lastPrice"),
        (quote_section or {}).get("mark"),
        (quote_section or {}).get("closePrice"),
        (underlying_quote or {}).get("last"),
        chain_data.get("underlyingPrice"),
    )
    underlying_symbol = chain_data.get("symbol") or symbol
    snapshot_captured_at = datetime.now().isoformat()

    rows: list[OptionContractRow] = []
    for put_call, map_key in (("CALL", "callExpDateMap"), ("PUT", "putExpDateMap")):
        expiration_map = chain_data.get(map_key, {}) or {}
        for expiration_key, strike_map in expiration_map.items():
            expiration_date, dte = _split_expiration_key(expiration_key)
            for strike_key, contracts in (strike_map or {}).items():
                strike = _safe_float(strike_key)
                if strike is None:
                    continue
                for contract in contracts or []:
                    rows.append(
                        OptionContractRow(
                            snapshot_captured_at=snapshot_captured_at,
                            symbol=contract.get("symbol") or "",
                            underlying_symbol=underlying_symbol,
                            underlying_price=_first_non_null_float(
                                contract.get("underlyingPrice"),
                                underlying_price,
                                contract.get("mark"),
                                contract.get("last"),
                            ),
                            expiration_date=contract.get("expirationDate") or expiration_date,
                            dte=_safe_int(contract.get("daysToExpiration")) or dte,
                            strike=strike,
                            put_call=contract.get("putCall") or put_call,
                            bid=_safe_float(contract.get("bid")),
                            ask=_safe_float(contract.get("ask")),
                            last=_safe_float(contract.get("last")),
                            mark=_safe_float(contract.get("mark")),
                            delta=_safe_float(contract.get("delta")),
                            gamma=_safe_float(contract.get("gamma")),
                            theta=_safe_float(contract.get("theta")),
                            vega=_safe_float(contract.get("vega")),
                            volatility=_safe_float(contract.get("volatility")),
                            open_interest=_safe_int(contract.get("openInterest")),
                            total_volume=_safe_int(contract.get("totalVolume")),
                            in_the_money=contract.get("inTheMoney"),
                            raw=contract,
                        )
                    )

    rows.sort(
        key=lambda row: (
            _sort_expiration(row.expiration_date),
            row.strike,
            row.put_call,
        )
    )
    return rows


def option_chain_rows_to_dicts(chain_data: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
    return [row.to_dict() for row in flatten_option_chain(chain_data, symbol)]


def _sort_expiration(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return datetime.max
