from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any


CONTRACT_MULTIPLIER = 100
DTE_BUCKETS = (
    (0, 0, "0DTE"),
    (1, 3, "1-3DTE"),
    (4, 7, "4-7DTE"),
    (8, 30, "8-30DTE"),
    (31, 90, "31-90DTE"),
    (91, None, "90+DTE"),
)


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _parse_expiration(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _spot_price_from_contracts(contracts: list[dict[str, Any]]) -> float | None:
    for contract in contracts:
        underlying_price = _coerce_float(contract.get("underlying_price"))
        if underlying_price not in (None, 0.0):
            return underlying_price
    return None


def _signed_side(contract: dict[str, Any]) -> float:
    return 1.0 if str(contract.get("put_call", "")).upper() == "CALL" else -1.0


def _unsigned_gamma_exposure(contract: dict[str, Any]) -> float:
    gamma = _coerce_float(contract.get("gamma")) or 0.0
    open_interest = _coerce_float(contract.get("open_interest")) or 0.0
    underlying_price = _coerce_float(contract.get("underlying_price")) or 0.0
    return gamma * open_interest * CONTRACT_MULTIPLIER * (underlying_price ** 2)


def _signed_gamma_exposure(contract: dict[str, Any]) -> float:
    return _signed_side(contract) * _unsigned_gamma_exposure(contract)


def _signed_delta_exposure(contract: dict[str, Any]) -> float:
    delta = _coerce_float(contract.get("delta")) or 0.0
    open_interest = _coerce_float(contract.get("open_interest")) or 0.0
    underlying_price = _coerce_float(contract.get("underlying_price")) or 0.0
    return delta * open_interest * CONTRACT_MULTIPLIER * underlying_price


def _signed_vega_exposure(contract: dict[str, Any]) -> float:
    vega = _coerce_float(contract.get("vega")) or 0.0
    open_interest = _coerce_float(contract.get("open_interest")) or 0.0
    return vega * open_interest * CONTRACT_MULTIPLIER


def _signed_theta_exposure(contract: dict[str, Any]) -> float:
    theta = _coerce_float(contract.get("theta")) or 0.0
    open_interest = _coerce_float(contract.get("open_interest")) or 0.0
    return theta * open_interest * CONTRACT_MULTIPLIER


def _estimate_dte(contract: dict[str, Any], today: date) -> int | None:
    dte_value = _coerce_int(contract.get("dte"))
    if dte_value is not None:
        return dte_value
    expiration = _parse_expiration(contract.get("expiration_date"))
    if expiration is None:
        return None
    return (expiration - today).days


def _bucket_for_dte(dte: int | None) -> str:
    if dte is None:
        return "unknown"
    for lower, upper, label in DTE_BUCKETS:
        if dte < lower:
            continue
        if upper is None or dte <= upper:
            return label
    return "unknown"


def _distance_bucket(contract: dict[str, Any]) -> str:
    strike = _coerce_float(contract.get("strike"))
    spot = _coerce_float(contract.get("underlying_price"))
    if strike in (None, 0.0) or spot in (None, 0.0):
        return "unknown"
    pct = ((strike - spot) / spot) * 100.0
    bins = [
        (-1000.0, -10.0, "<=-10%"),
        (-10.0, -5.0, "-10% to -5%"),
        (-5.0, -2.0, "-5% to -2%"),
        (-2.0, 2.0, "-2% to +2%"),
        (2.0, 5.0, "+2% to +5%"),
        (5.0, 10.0, "+5% to +10%"),
        (10.0, 1000.0, ">=+10%"),
    ]
    for lower, upper, label in bins:
        if lower <= pct < upper:
            return label
    return ">=+10%"


def _moneyness_bucket(contract: dict[str, Any]) -> str:
    strike = _coerce_float(contract.get("strike"))
    spot = _coerce_float(contract.get("underlying_price"))
    side = str(contract.get("put_call") or "").upper()
    if strike in (None, 0.0) or spot in (None, 0.0):
        return "unknown"
    atm_band = spot * 0.02
    if abs(strike - spot) <= atm_band:
        return "ATM"
    if side == "CALL":
        return "ITM" if strike < spot else "OTM"
    if side == "PUT":
        return "ITM" if strike > spot else "OTM"
    return "unknown"


def _contract_metrics(contract: dict[str, Any], today: date) -> dict[str, Any]:
    expiration = _parse_expiration(contract.get("expiration_date"))
    dte = _estimate_dte(contract, today)
    strike = _coerce_float(contract.get("strike")) or 0.0
    side = str(contract.get("put_call") or "").upper()
    open_interest = _coerce_float(contract.get("open_interest")) or 0.0
    volume = _coerce_float(contract.get("total_volume")) or 0.0
    iv = _coerce_float(contract.get("volatility"))
    distance_bucket = _distance_bucket(contract)
    moneyness_bucket = _moneyness_bucket(contract)
    gamma = _signed_gamma_exposure(contract)
    dex = _signed_delta_exposure(contract)
    vex = _signed_vega_exposure(contract)
    tex = _signed_theta_exposure(contract)
    return {
        "expiration": expiration.isoformat() if expiration is not None else str(contract.get("expiration_date") or ""),
        "dte": dte,
        "dte_bucket": _bucket_for_dte(dte),
        "strike": strike,
        "side": side,
        "open_interest": open_interest,
        "volume": volume,
        "iv": iv,
        "distance_bucket": distance_bucket,
        "moneyness_bucket": moneyness_bucket,
        "net_gex": gamma,
        "net_dex": dex,
        "net_vex": vex,
        "net_tex": tex,
        "abs_gex": abs(gamma),
    }


def _new_group() -> dict[str, Any]:
    return {
        "net_gex": 0.0,
        "call_gex": 0.0,
        "put_gex": 0.0,
        "net_dex": 0.0,
        "net_vex": 0.0,
        "net_tex": 0.0,
        "call_oi": 0.0,
        "put_oi": 0.0,
        "total_oi": 0.0,
        "total_volume": 0.0,
        "contracts_count": 0,
        "expirations": set(),
        "atm_candidates": [],
    }


def _update_group(group: dict[str, Any], metrics: dict[str, Any]) -> None:
    side = metrics["side"]
    group["net_gex"] += metrics["net_gex"]
    group["net_dex"] += metrics["net_dex"]
    group["net_vex"] += metrics["net_vex"]
    group["net_tex"] += metrics["net_tex"]
    group["total_oi"] += metrics["open_interest"]
    group["total_volume"] += metrics["volume"]
    group["contracts_count"] += 1
    if side == "CALL":
        group["call_gex"] += metrics["net_gex"]
        group["call_oi"] += metrics["open_interest"]
    elif side == "PUT":
        group["put_gex"] += metrics["net_gex"]
        group["put_oi"] += metrics["open_interest"]
    if metrics["expiration"]:
        group["expirations"].add(metrics["expiration"])
    if metrics["iv"] is not None:
        group["atm_candidates"].append((abs(metrics["strike"]), metrics["iv"]))


def _finalize_group(key_name: str, key_value: Any, group: dict[str, Any]) -> dict[str, Any]:
    atm_iv = None
    if group["atm_candidates"]:
        atm_iv = min(group["atm_candidates"], key=lambda item: item[0])[1]
    put_oi = float(group["put_oi"])
    call_oi = float(group["call_oi"])
    total_volume = float(group["total_volume"])
    return {
        key_name: key_value,
        "net_gex": float(group["net_gex"]),
        "call_gex": float(group["call_gex"]),
        "put_gex": float(group["put_gex"]),
        "net_dex": float(group["net_dex"]),
        "net_vex": float(group["net_vex"]),
        "net_tex": float(group["net_tex"]),
        "call_oi": call_oi,
        "put_oi": put_oi,
        "total_oi": float(group["total_oi"]),
        "total_volume": total_volume,
        "contracts_count": int(group["contracts_count"]),
        "expirations": sorted(group["expirations"]),
        "pcr_oi": (put_oi / call_oi) if call_oi else None,
        "pcr_volume": None,
        "atm_iv": atm_iv,
    }


def _aggregate_contracts(contracts: list[dict[str, Any]]) -> dict[str, Any]:
    today = date.today()
    total_group = _new_group()
    by_expiry: dict[str, dict[str, Any]] = defaultdict(_new_group)
    by_strike: dict[float, dict[str, Any]] = defaultdict(_new_group)
    by_dte_bucket: dict[str, dict[str, Any]] = defaultdict(_new_group)
    by_moneyness: dict[str, dict[str, Any]] = defaultdict(_new_group)
    by_distance: dict[str, dict[str, Any]] = defaultdict(_new_group)

    processed: list[dict[str, Any]] = []
    for contract in contracts:
        metrics = _contract_metrics(contract, today)
        processed.append(metrics)
        _update_group(total_group, metrics)
        _update_group(by_expiry[metrics["expiration"]], metrics)
        _update_group(by_strike[metrics["strike"]], metrics)
        _update_group(by_dte_bucket[metrics["dte_bucket"]], metrics)
        _update_group(by_moneyness[metrics["moneyness_bucket"]], metrics)
        _update_group(by_distance[metrics["distance_bucket"]], metrics)

    expiry_rows = []
    for expiration, group in sorted(by_expiry.items()):
        row = _finalize_group("expiration_date", expiration, group)
        dte_values = [int(item["dte"]) for item in processed if item["expiration"] == expiration and item["dte"] is not None]
        row["dte"] = min(dte_values) if dte_values else None
        expiry_rows.append(row)

    strike_rows = []
    for strike, group in sorted(by_strike.items()):
        row = _finalize_group("strike", float(strike), group)
        row["abs_gex"] = abs(float(row["net_gex"]))
        strike_rows.append(row)

    bucket_rows = []
    for bucket_type, groups in (
        ("dte", by_dte_bucket),
        ("moneyness", by_moneyness),
        ("distance_from_spot", by_distance),
    ):
        for bucket_label, group in sorted(groups.items()):
            row = _finalize_group("bucket_label", bucket_label, group)
            row["bucket_type"] = bucket_type
            bucket_rows.append(row)

    total = _finalize_group("label", "total", total_group)
    total["spot_price"] = _spot_price_from_contracts(contracts)
    return {
        "total": total,
        "by_expiration": expiry_rows,
        "by_strike": strike_rows,
        "by_dte_bucket": [row for row in bucket_rows if row["bucket_type"] == "dte"],
        "by_bucket": bucket_rows,
    }


def compute_gex(contracts: list[dict[str, Any]]) -> dict[str, Any]:
    aggregates = _aggregate_contracts(contracts)
    return {
        "total_gex": aggregates["total"]["net_gex"],
        "total_dex": aggregates["total"]["net_dex"],
        "total_vex": aggregates["total"]["net_vex"],
        "total_tex": aggregates["total"]["net_tex"],
        "spot_price": aggregates["total"]["spot_price"],
        "by_expiration": {row["expiration_date"]: row["net_gex"] for row in aggregates["by_expiration"]},
        "by_strike": {row["strike"]: row["net_gex"] for row in aggregates["by_strike"]},
        "by_dte_bucket": {row["bucket_label"]: row["net_gex"] for row in aggregates["by_dte_bucket"]},
    }


def compute_gex_levels(
    contracts: list[dict[str, Any]],
    max_levels: int = 10,
    min_dte: int = 0,
    max_dte: int = 30,
    strike_min: float | None = None,
    strike_max: float | None = None,
    spot_range_pct: float | None = 0.2,
) -> list[dict[str, Any]]:
    totals_by_strike: dict[float, dict[str, Any]] = {}
    today = date.today()
    spot_price = _spot_price_from_contracts(contracts)

    if spot_price is not None and spot_range_pct is not None:
        dynamic_min = spot_price * (1.0 - spot_range_pct)
        dynamic_max = spot_price * (1.0 + spot_range_pct)
        strike_min = dynamic_min if strike_min is None else max(strike_min, dynamic_min)
        strike_max = dynamic_max if strike_max is None else min(strike_max, dynamic_max)

    for contract in contracts:
        dte = _estimate_dte(contract, today)
        if dte is None or dte < min_dte or dte > max_dte:
            continue

        strike = _coerce_float(contract.get("strike"))
        if strike is None:
            continue
        if strike_min is not None and strike < strike_min:
            continue
        if strike_max is not None and strike > strike_max:
            continue

        expiration = _parse_expiration(contract.get("expiration_date"))
        exposure = _signed_gamma_exposure(contract)
        side = str(contract.get("put_call") or "").upper()

        bucket = totals_by_strike.setdefault(
            strike,
            {
                "strike": strike,
                "net_gex": 0.0,
                "call_gex": 0.0,
                "put_gex": 0.0,
                "expirations": set(),
            },
        )
        bucket["net_gex"] += exposure
        if side == "CALL":
            bucket["call_gex"] += exposure
        elif side == "PUT":
            bucket["put_gex"] += exposure
        if expiration is not None:
            bucket["expirations"].add(expiration.isoformat())

    levels: list[dict[str, Any]] = []
    for bucket in totals_by_strike.values():
        net_gex = float(bucket["net_gex"])
        call_gex = float(bucket["call_gex"])
        put_gex = float(bucket["put_gex"])
        if call_gex and not put_gex:
            dominant_side = "CALL"
        elif put_gex and not call_gex:
            dominant_side = "PUT"
        elif abs(call_gex) >= abs(put_gex):
            dominant_side = "CALL" if call_gex else "MIXED"
        else:
            dominant_side = "PUT"

        levels.append(
            {
                "strike": float(bucket["strike"]),
                "net_gex": net_gex,
                "abs_gex": abs(net_gex),
                "dominant_side": dominant_side,
                "expirations_contributing": sorted(bucket["expirations"]),
            }
        )

    levels.sort(key=lambda level: (-float(level["abs_gex"]), float(level["strike"])))
    return levels[:max_levels]


def estimate_gamma_flip(contracts: list[dict[str, Any]]) -> float | None:
    ordered = sorted(_aggregate_contracts(contracts)["by_strike"], key=lambda row: float(row["strike"]))
    if len(ordered) < 2:
        return None
    previous = ordered[0]
    previous_gex = float(previous["net_gex"])
    if previous_gex == 0.0:
        return float(previous["strike"])
    for current in ordered[1:]:
        current_gex = float(current["net_gex"])
        if current_gex == 0.0:
            return float(current["strike"])
        if previous_gex * current_gex < 0:
            prev_strike = float(previous["strike"])
            curr_strike = float(current["strike"])
            weight = abs(previous_gex) / (abs(previous_gex) + abs(current_gex))
            return prev_strike + ((curr_strike - prev_strike) * weight)
        previous = current
        previous_gex = current_gex
    return None


def summarize_top_walls(contracts: list[dict[str, Any]], max_walls: int = 5) -> dict[str, Any]:
    strike_rows = _aggregate_contracts(contracts)["by_strike"]
    if not strike_rows:
        return {
            "largest_call_wall": None,
            "largest_put_wall": None,
            "largest_net_wall": None,
            "top_abs_gex_concentration": 0.0,
            "top_walls": [],
        }

    largest_call = max(strike_rows, key=lambda row: float(row["call_gex"]))
    largest_put = min(strike_rows, key=lambda row: float(row["put_gex"]))
    largest_net = max(strike_rows, key=lambda row: abs(float(row["net_gex"])))
    ordered = sorted(strike_rows, key=lambda row: abs(float(row["net_gex"])), reverse=True)
    total_abs = sum(abs(float(row["net_gex"])) for row in ordered)
    top_abs = sum(abs(float(row["net_gex"])) for row in ordered[:max_walls])
    return {
        "largest_call_wall": {"strike": largest_call["strike"], "call_gex": largest_call["call_gex"]},
        "largest_put_wall": {"strike": largest_put["strike"], "put_gex": largest_put["put_gex"]},
        "largest_net_wall": {"strike": largest_net["strike"], "net_gex": largest_net["net_gex"]},
        "top_abs_gex_concentration": (top_abs / total_abs) if total_abs else 0.0,
        "top_walls": ordered[:max_walls],
    }


def compute_exposure_report(contracts: list[dict[str, Any]]) -> dict[str, Any]:
    aggregates = _aggregate_contracts(contracts)
    positive_gamma = sum(max(float(row["net_gex"]), 0.0) for row in aggregates["by_strike"])
    negative_gamma = sum(min(float(row["net_gex"]), 0.0) for row in aggregates["by_strike"])
    return {
        "snapshot": {
            "spot_price": aggregates["total"]["spot_price"],
            "total_gex": aggregates["total"]["net_gex"],
            "total_dex": aggregates["total"]["net_dex"],
            "total_vex": aggregates["total"]["net_vex"],
            "total_tex": aggregates["total"]["net_tex"],
            "total_oi": aggregates["total"]["total_oi"],
            "total_volume": aggregates["total"]["total_volume"],
        },
        "by_strike": aggregates["by_strike"],
        "by_expiration": aggregates["by_expiration"],
        "by_dte_bucket": aggregates["by_dte_bucket"],
        "by_bucket": aggregates["by_bucket"],
        "dealer_regime": {
            "positive_gamma_total": positive_gamma,
            "negative_gamma_total": negative_gamma,
            "gamma_flip_estimate": estimate_gamma_flip(contracts),
            **summarize_top_walls(contracts),
        },
    }
