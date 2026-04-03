from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from requests import RequestException

from schwab.client import create_client
from schwab.models import option_chain_rows_to_dicts


class SchwabApiError(RuntimeError):
    pass


INDEX_OPTION_SYMBOL_ALIASES = {
    "SPX": "$SPX",
    "$SPX": "$SPX",
}


def normalize_option_chain_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    return INDEX_OPTION_SYMBOL_ALIASES.get(normalized, normalized)


def _coerce_date(value: str | date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _coerce_datetime(value: str | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _response_json(response: Any, endpoint: str) -> Any:
    status_code = getattr(response, "status_code", None)
    if status_code != 200:
        text = getattr(response, "text", "") or ""
        detail = text[:500].strip()
        raise SchwabApiError(
            f"Schwab API request failed for {endpoint} with status {status_code}. {detail}"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise SchwabApiError(f"Schwab API returned invalid JSON for {endpoint}.") from exc


def _request_json(request_fn: Any, endpoint: str, **kwargs: Any) -> Any:
    client = create_client()
    try:
        response = request_fn(client, **kwargs)
    except RequestException as exc:
        raise SchwabApiError(f"Schwab API request failed for {endpoint}: {exc}") from exc
    except Exception as exc:
        raise SchwabApiError(f"Unexpected error calling {endpoint}: {exc}") from exc

    return _response_json(response, endpoint)


def get_quote(symbol: str) -> dict[str, Any]:
    payload = _request_json(lambda client, **_: client.quote(symbol), f"quote({symbol})")
    try:
        return payload[symbol]
    except KeyError as exc:
        raise SchwabApiError(f"Quote payload did not contain symbol {symbol}.") from exc


def get_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    payload = _request_json(lambda client, **_: client.quotes(symbols), f"quotes({','.join(symbols)})")
    if not isinstance(payload, dict):
        raise SchwabApiError("Quotes payload was not a JSON object.")
    return payload


def get_top_movers(symbol: str, sort: str, frequency: int = 0, limit: int = 5) -> list[dict[str, Any]]:
    payload = _request_json(
        lambda client, **_: client.movers(symbol, sort=sort, frequency=frequency),
        f"movers({symbol},{sort})",
    )
    screeners = payload.get("screeners") if isinstance(payload, dict) else None
    if not isinstance(screeners, list):
        raise SchwabApiError(f"Movers payload for {symbol} did not include a screeners list.")

    rows: list[dict[str, Any]] = []
    for screener in screeners:
        if not isinstance(screener, dict):
            continue
        symbols = screener.get("symbols")
        if isinstance(symbols, list):
            for mover in symbols:
                if isinstance(mover, dict):
                    rows.append(mover)
            continue
        rows.append(screener)
    return rows[:limit]


def debug_top_movers_payload(symbol: str, sort: str, frequency: int = 0) -> dict[str, Any]:
    payload = _request_json(
        lambda client, **_: client.movers(symbol, sort=sort, frequency=frequency),
        f"movers({symbol},{sort})",
    )
    if isinstance(payload, dict):
        return payload
    return {"payload": payload}


def get_expirations(symbol: str) -> list[dict[str, Any]]:
    payload = _request_json(
        lambda client, **_: client.option_expiration_chain(symbol),
        f"option_expiration_chain({symbol})",
    )
    return payload.get("expirationList", [])


def get_option_chain(
    symbol: str,
    from_date: str | date | datetime | None = None,
    to_date: str | date | datetime | None = None,
    contract_type: str = "ALL",
    option_range: str = "OTM",
    strike_range: str | None = None,
    include_underlying_quote: bool = True,
    strategy: str = "SINGLE",
    interval: str = "1",
    days: int | None = None,
) -> dict[str, Any]:
    request_symbol = normalize_option_chain_symbol(symbol)
    if days is not None:
        from_date = from_date or date.today()
        if isinstance(from_date, str):
            start = datetime.fromisoformat(from_date)
        elif isinstance(from_date, datetime):
            start = from_date
        else:
            start = datetime.combine(from_date, datetime.min.time())
        to_date = to_date or (start.date() + timedelta(days=days))

    params = {
        "contractType": contract_type,
        "includeUnderlyingQuote": include_underlying_quote,
        "strategy": strategy,
        "range": option_range,
        "interval": interval,
    }
    if strike_range:
        params["strikeRange"] = strike_range
    coerced_from = _coerce_date(from_date)
    coerced_to = _coerce_date(to_date)
    if coerced_from:
        params["fromDate"] = coerced_from
    if coerced_to:
        params["toDate"] = coerced_to

    return _request_json(
        lambda client, **_: client.option_chains(request_symbol, **params),
        f"option_chains({request_symbol})",
    )


def get_option_chain_rows(
    symbol: str,
    from_date: str | date | datetime | None = None,
    to_date: str | date | datetime | None = None,
    contract_type: str = "ALL",
    option_range: str = "OTM",
    strike_range: str | None = None,
    include_underlying_quote: bool = True,
    strategy: str = "SINGLE",
    interval: str = "1",
    days: int | None = None,
) -> list[dict[str, Any]]:
    chain_data = get_option_chain(
        symbol=symbol,
        from_date=from_date,
        to_date=to_date,
        contract_type=contract_type,
        option_range=option_range,
        strike_range=strike_range,
        include_underlying_quote=include_underlying_quote,
        strategy=strategy,
        interval=interval,
        days=days,
    )
    return option_chain_rows_to_dicts(chain_data, symbol)


def get_price_history(
    symbol: str,
    start_datetime: str | datetime | None = None,
    end_datetime: str | datetime | None = None,
    period_type: str | None = None,
    period: str | int | None = None,
    frequency_type: str = "hourly",
    frequency: int = 1,
    need_extended_hours: bool = False,
    need_previous_close: bool = False,
) -> list[dict[str, Any]]:
    frequency_type_value = "minute" if frequency_type == "hourly" else frequency_type
    frequency_value = 30 if frequency_type == "hourly" and frequency == 1 else frequency

    params = {
        "frequencyType": frequency_type_value,
        "frequency": frequency_value,
        "needExtendedHoursData": need_extended_hours,
        "needPreviousClose": need_previous_close,
    }

    if period_type is None and start_datetime is not None and end_datetime is not None:
        period_type = "day"

    if period_type:
        params["periodType"] = period_type
    if period is not None:
        params["period"] = str(period)

    coerced_start = _coerce_datetime(start_datetime)
    coerced_end = _coerce_datetime(end_datetime)
    if coerced_start:
        if isinstance(start_datetime, datetime):
            params["startDate"] = int(start_datetime.timestamp() * 1000)
        else:
            params["startDate"] = int(datetime.fromisoformat(coerced_start).timestamp() * 1000)
    if coerced_end:
        if isinstance(end_datetime, datetime):
            params["endDate"] = int(end_datetime.timestamp() * 1000)
        else:
            params["endDate"] = int(datetime.fromisoformat(coerced_end).timestamp() * 1000)

    payload = _request_json(
        lambda client, **_: client.price_history(symbol, **params),
        f"price_history({symbol})",
    )

    candles = payload.get("candles") or []
    normalized: list[dict[str, Any]] = []
    for candle in candles:
        timestamp_raw = candle.get("datetime")
        timestamp = None
        if timestamp_raw not in (None, ""):
            try:
                timestamp = datetime.fromtimestamp(float(timestamp_raw) / 1000.0).isoformat()
            except (TypeError, ValueError, OSError):
                timestamp = None

        normalized.append(
            {
                "timestamp": timestamp,
                "open": candle.get("open"),
                "high": candle.get("high"),
                "low": candle.get("low"),
                "close": candle.get("close"),
                "volume": candle.get("volume"),
            }
        )

    return normalized
