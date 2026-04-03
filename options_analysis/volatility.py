from __future__ import annotations

from typing import Any
import math


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    numeric = _coerce_float(value)
    if numeric is None:
        return None
    return int(round(numeric))


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0.0):
        return None
    return float(numerator) / float(denominator)


def _bucket_delta(delta: float | None) -> str | None:
    if delta is None:
        return None
    absolute = abs(delta)
    if absolute >= 0.45:
        return "atm"
    if absolute >= 0.25:
        return "25d"
    if absolute >= 0.10:
        return "10d"
    return "tail"


def build_iv_surface(contracts: list[dict[str, Any]], spot_price: float | None, max_points: int = 18) -> list[dict[str, Any]]:
    surface: list[dict[str, Any]] = []
    for contract in contracts:
        iv = _coerce_float(contract.get("volatility") or contract.get("implied_volatility") or contract.get("iv"))
        strike = _coerce_float(contract.get("strike"))
        dte = _coerce_int(contract.get("dte"))
        if iv is None or strike is None:
            continue
        moneyness = _safe_div(strike, spot_price)
        delta = _coerce_float(contract.get("delta"))
        surface.append(
            {
                "expiration": contract.get("expiration") or contract.get("expiration_date"),
                "dte": dte,
                "strike": strike,
                "option_type": contract.get("option_type") or contract.get("type"),
                "implied_volatility": iv,
                "moneyness": round(moneyness, 4) if moneyness is not None else None,
                "delta_bucket": _bucket_delta(delta),
            }
        )
    surface.sort(
        key=lambda row: (
            row.get("dte") is None,
            row.get("dte") or 9999,
            abs((row.get("moneyness") or 1.0) - 1.0),
        )
    )
    return surface[:max_points]


def build_skew_metrics(contracts: list[dict[str, Any]]) -> dict[str, Any]:
    put_25d: float | None = None
    call_25d: float | None = None
    atm_iv: float | None = None

    best_put_distance = float("inf")
    best_call_distance = float("inf")
    best_atm_distance = float("inf")

    for contract in contracts:
        iv = _coerce_float(contract.get("volatility") or contract.get("implied_volatility") or contract.get("iv"))
        delta = _coerce_float(contract.get("delta"))
        option_type = (contract.get("option_type") or contract.get("type") or "").lower()
        if iv is None or delta is None:
            continue

        absolute_delta = abs(delta)
        atm_distance = abs(absolute_delta - 0.50)
        if atm_distance < best_atm_distance:
            best_atm_distance = atm_distance
            atm_iv = iv

        if option_type == "put":
            distance = abs(absolute_delta - 0.25)
            if distance < best_put_distance:
                best_put_distance = distance
                put_25d = iv
        elif option_type == "call":
            distance = abs(absolute_delta - 0.25)
            if distance < best_call_distance:
                best_call_distance = distance
                call_25d = iv

    put_call_25d_skew = None
    put_atm_skew = None
    call_atm_skew = None
    if put_25d is not None and call_25d is not None:
        put_call_25d_skew = round(put_25d - call_25d, 4)
    if put_25d is not None and atm_iv is not None:
        put_atm_skew = round(put_25d - atm_iv, 4)
    if call_25d is not None and atm_iv is not None:
        call_atm_skew = round(call_25d - atm_iv, 4)

    return {
        "put_25d_iv": put_25d,
        "call_25d_iv": call_25d,
        "atm_surface_iv": atm_iv,
        "put_call_25d_skew": put_call_25d_skew,
        "put_atm_skew": put_atm_skew,
        "call_atm_skew": call_atm_skew,
    }


def build_term_structure(by_expiration: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for row in by_expiration:
        atm_iv = _coerce_float(row.get("atm_iv"))
        dte = _coerce_int(row.get("dte"))
        if atm_iv is None or dte is None:
            continue
        nodes.append(
            {
                "expiration": row.get("expiration_date") or row.get("expiration"),
                "dte": dte,
                "atm_iv": atm_iv,
                "net_gex": _coerce_float(row.get("net_gex")),
                "total_oi": _coerce_float(row.get("total_oi")),
            }
        )
    nodes.sort(key=lambda row: row["dte"])
    if not nodes:
        return []

    enriched: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        previous_iv = nodes[index - 1]["atm_iv"] if index > 0 else None
        slope = None if previous_iv is None else round(node["atm_iv"] - previous_iv, 4)
        previous_dte = nodes[index - 1]["dte"] if index > 0 else None
        forward_vol = None
        if index > 0 and previous_iv is not None and previous_dte is not None and node["dte"] > previous_dte:
            total_var = (node["atm_iv"] ** 2) * node["dte"]
            prior_var = (previous_iv ** 2) * previous_dte
            forward_window = node["dte"] - previous_dte
            if total_var >= prior_var and forward_window > 0:
                forward_vol = round(math.sqrt((total_var - prior_var) / forward_window), 4)
        enriched.append({**node, "slope_from_prev": slope, "forward_vol": forward_vol})
    return enriched


def build_realized_implied_profile(snapshot: dict[str, Any], term_structure: list[dict[str, Any]], skew_metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    rv_20 = _coerce_float(snapshot.get("rv_20"))
    atm_iv = _coerce_float(snapshot.get("atm_iv"))
    spread = None
    if atm_iv is not None and rv_20 is not None:
        spread = round(atm_iv - rv_20, 4)

    front_month_iv = term_structure[0]["atm_iv"] if term_structure else None
    back_month_iv = term_structure[-1]["atm_iv"] if term_structure else None
    slope = None
    if front_month_iv is not None and back_month_iv is not None:
        slope = round(back_month_iv - front_month_iv, 4)

    if spread is None:
        vol_regime = "unknown"
    elif spread >= 0.05:
        vol_regime = "premium_rich"
    elif spread <= -0.05:
        vol_regime = "premium_cheap"
    else:
        vol_regime = "fair_value"

    if slope is None:
        surface_shape = "unknown"
    elif slope > 0.02:
        surface_shape = "contango"
    elif slope < -0.02:
        surface_shape = "backwardation"
    else:
        surface_shape = "flat"

    return {
        "rv_20": rv_20,
        "atm_iv": atm_iv,
        "realized_implied_spread": spread,
        "front_month_iv": front_month_iv,
        "back_month_iv": back_month_iv,
        "term_structure_slope": slope,
        "vol_regime": vol_regime,
        "surface_shape": surface_shape,
        "forward_volatility_curve": [
            {
                "expiration": node.get("expiration"),
                "dte": node.get("dte"),
                "forward_vol": node.get("forward_vol"),
            }
            for node in term_structure
            if node.get("forward_vol") is not None
        ],
        "put_call_25d_skew": (skew_metrics or {}).get("put_call_25d_skew"),
        "put_atm_skew": (skew_metrics or {}).get("put_atm_skew"),
        "call_atm_skew": (skew_metrics or {}).get("call_atm_skew"),
    }


def build_calendar_relative_value(term_structure: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(term_structure) < 2:
        return []

    pair_scores: list[dict[str, Any]] = []
    slopes = [
        abs(node.get("slope_from_prev"))
        for node in term_structure
        if node.get("slope_from_prev") is not None
    ]
    baseline_slope = (sum(slopes) / len(slopes)) if slopes else 0.0

    for index in range(1, len(term_structure)):
        near = term_structure[index - 1]
        far = term_structure[index]
        near_iv = _coerce_float(near.get("atm_iv"))
        far_iv = _coerce_float(far.get("atm_iv"))
        near_dte = _coerce_float(near.get("dte"))
        far_dte = _coerce_float(far.get("dte"))
        forward_vol = _coerce_float(far.get("forward_vol"))
        if near_iv is None or far_iv is None or near_dte is None or far_dte is None or far_dte <= near_dte:
            continue

        iv_spread = round(far_iv - near_iv, 4)
        slope_from_prev = _coerce_float(far.get("slope_from_prev")) or 0.0
        deviation_from_curve = round(abs(slope_from_prev) - baseline_slope, 4)
        forward_gap = None if forward_vol is None else round(forward_vol - far_iv, 4)
        mispricing_score = round(abs(iv_spread) + max(0.0, deviation_from_curve), 4)

        if iv_spread > 0.01:
            bias = "long_near_short_far"
            thesis = "Back month IV is rich relative to the near month."
        elif iv_spread < -0.01:
            bias = "short_near_long_far"
            thesis = "Front month IV is rich relative to the back month."
        else:
            bias = "balanced_pair"
            thesis = "Adjacent expirations price volatility similarly."

        pair_scores.append(
            {
                "near_expiration": near.get("expiration"),
                "far_expiration": far.get("expiration"),
                "near_dte": int(near_dte),
                "far_dte": int(far_dte),
                "near_iv": near_iv,
                "far_iv": far_iv,
                "forward_vol": forward_vol,
                "iv_spread": iv_spread,
                "forward_gap": forward_gap,
                "deviation_from_curve": deviation_from_curve,
                "mispricing_score": mispricing_score,
                "bias": bias,
                "thesis": thesis,
            }
        )

    pair_scores.sort(key=lambda row: -float(row["mispricing_score"]))
    return pair_scores


def build_backtest_blueprints(vol_environment: dict[str, Any]) -> list[dict[str, Any]]:
    blueprints: list[dict[str, Any]] = [
        {
            "name": "short_premium_iv_rank",
            "setup": "Sell defined-risk premium when implied volatility is rich versus expected realized volatility.",
            "entry_rules": [
                "Enter when implied volatility is high relative to expected realized volatility",
                "Use iv_rank >= 60 as a secondary context filter, not the primary reason",
                "Prefer 14-45 DTE expirations with stable or upward-sloping term structure",
            ],
            "exit_rules": [
                "Take profits at 40-60% of max credit",
                "Exit early if realized_implied_spread compresses below 0.02",
            ],
            "metrics_to_track": ["win_rate", "premium_capture", "max_drawdown", "vega_pnl"],
        },
        {
            "name": "long_gamma_scalp",
            "setup": "Own near-ATM gamma when implied volatility is cheap and hedge directional exposure.",
            "entry_rules": [
                "Enter when realized_implied_spread <= -0.03",
                "Prefer short-dated ATM options with expanding realized range",
            ],
            "exit_rules": [
                "Exit when cumulative hedge PnL no longer offsets theta decay",
                "Exit before major event if term structure inverts sharply",
            ],
            "metrics_to_track": ["hedge_pnl", "theta_bleed", "realized_vol", "net_gamma_pnl"],
        },
        {
            "name": "calendar_term_structure",
            "setup": "Trade relative value across expirations using term structure and forward volatility.",
            "entry_rules": [
                "Enter when one expiration appears mispriced versus adjacent months or forward volatility",
                "Use ATM strikes near the highest-interest node",
            ],
            "exit_rules": [
                "Exit after event premium compresses or slope normalizes below 0.01",
                "Cut if spot trends away from the entry strike by more than 2%",
            ],
            "metrics_to_track": ["term_structure_pnl", "vega_pnl", "theta_pnl", "event_gap_risk"],
        },
    ]

    if vol_environment.get("surface_shape") == "backwardation":
        blueprints.append(
            {
                "name": "event_premium_fade",
                "setup": "Fade front-loaded volatility after the event premium peaks.",
                "entry_rules": [
                    "Enter when surface_shape == backwardation and front_month_iv is elevated",
                    "Prefer structures with limited gap risk such as flies or calendars",
                ],
                "exit_rules": [
                    "Exit once front-month IV mean reverts into the back-month range",
                    "Stop if event repricing lifts deferred IV as well",
                ],
                "metrics_to_track": ["iv_crush_capture", "theta_decay", "post_event_gap", "hold_time_days"],
            }
        )

    return blueprints
