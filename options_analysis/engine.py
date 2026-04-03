from __future__ import annotations

from typing import Any

from .config import DEFAULT_CONFIG, OptionsAnalysisConfig
from .constants import (
    OPP_CALENDAR_BACK_LEG,
    OPP_CALENDAR_FRONT_LEG,
    OPP_EVENT_PREMIUM,
    OPP_PIN_EXPIRY,
    OPP_SWING_STRUCTURE,
    OPP_VOL_BUY,
    OPP_VOL_SALE,
)
from .regime import classify_regime
from .trade_suggestion import build_trade_suggestion
from .types import DataCompletenessReport
from .volatility import build_backtest_blueprints, build_calendar_relative_value, build_iv_surface, build_realized_implied_profile, build_skew_metrics, build_term_structure


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0.0):
        return None
    return float(numerator) / float(denominator)


def _distance_between_levels(left: Any, right: Any) -> float | None:
    left_value = _coerce_float(left)
    right_value = _coerce_float(right)
    if left_value is None or right_value is None:
        return None
    return abs(left_value - right_value)


def _distance_pct(spot_price: float | None, level: float | None) -> float | None:
    if spot_price in (None, 0.0) or level is None:
        return None
    return abs(float(spot_price) - float(level)) / float(spot_price)


def _normalize_gamma_flip(spot_price: float | None, gamma_flip: float | None, config: OptionsAnalysisConfig) -> tuple[float | None, bool]:
    flip_distance_pct = _distance_pct(spot_price, gamma_flip)
    if gamma_flip is None:
        return None, False
    if flip_distance_pct is None:
        return gamma_flip, False
    if flip_distance_pct > config.max_reasonable_flip_distance_pct:
        return None, True
    return gamma_flip, False


def _compute_vol_environment(report: dict[str, Any], config: OptionsAnalysisConfig) -> dict[str, Any]:
    snapshot = report.get("snapshot", {})
    contracts = report.get("contracts", [])
    atm_iv = _coerce_float(snapshot.get("atm_iv"))
    rv_20 = _coerce_float(snapshot.get("rv_20"))
    iv_rank = _coerce_float(snapshot.get("iv_rank"))
    iv_percentile = _coerce_float(snapshot.get("iv_percentile"))

    iv_minus_rv = None
    if atm_iv is not None and rv_20 is not None:
        iv_minus_rv = atm_iv - rv_20

    term_structure = build_term_structure(report.get("by_expiration", []))
    calendar_relative_value = build_calendar_relative_value(term_structure)
    skew_metrics = build_skew_metrics(contracts)
    realized_implied_profile = build_realized_implied_profile(snapshot, term_structure, skew_metrics)

    vol_environment: dict[str, Any] = {
        "iv_rank": iv_rank,
        "iv_percentile": iv_percentile,
        "rv_20": rv_20,
        "atm_iv": atm_iv,
        "iv_minus_rv": iv_minus_rv,
        "term_structure": term_structure,
        "calendar_relative_value": calendar_relative_value,
        "skew_metrics": skew_metrics,
    }
    vol_environment.update(realized_implied_profile)
    return vol_environment


def _build_completeness(report: dict[str, Any], contracts: list[dict[str, Any]], config: OptionsAnalysisConfig) -> DataCompletenessReport:
    first_contract = contracts[0] if contracts else {}
    snapshot = report.get("snapshot", {})
    dealer_regime = report.get("dealer_regime", {})

    signal_fields: dict[str, Any] = {
        "total_gex": snapshot.get("total_gex"),
        "spot_price": snapshot.get("spot_price"),
        "gamma_flip": dealer_regime.get("gamma_flip_estimate"),
        "call_wall": dealer_regime.get("largest_call_wall"),
        "put_wall": dealer_regime.get("largest_put_wall"),
        "volatility": first_contract.get("volatility"),
        "delta": first_contract.get("delta"),
        "gamma": first_contract.get("gamma"),
        "theta": first_contract.get("theta"),
        "vega": first_contract.get("vega"),
        "rv_20": snapshot.get("rv_20"),
        "iv_rank": snapshot.get("iv_rank"),
        "iv_percentile": snapshot.get("iv_percentile"),
    }

    vol_env = _compute_vol_environment(report, config)
    iv_minus_rv = vol_env.get("iv_minus_rv")

    available = [name for name, value in signal_fields.items() if value not in (None, "")]
    missing = [name for name, value in signal_fields.items() if value in (None, "")]
    degraded = []
    if "gamma_flip" in missing:
        degraded.append("transition detection has lower confidence because gamma_flip is unavailable")
    if "volatility" in missing:
        degraded.append("volatility-aware strategy selection is limited because volatility is unavailable")
    if "call_wall" in missing or "put_wall" in missing:
        degraded.append("directional wall analysis is limited because one or more wall anchors are unavailable")
    if "rv_20" in missing or "iv_rank" in missing:
        degraded.append("vol-fit scoring is degraded because realized vol and IV rank are unavailable")
    if iv_minus_rv is not None and iv_minus_rv > config.vol_sale_iv_rv_threshold:
        degraded.append(f"IV is elevated vs RV by {iv_minus_rv:.1f} pts, favoring premium-selling strategies")
    if iv_minus_rv is not None and iv_minus_rv < config.vol_buy_iv_rv_threshold:
        degraded.append(f"IV is compressed vs RV by {abs(iv_minus_rv):.1f} pts, favoring long-vol strategies")

    total_signals = len(signal_fields)
    available_signals = len(available)
    completeness_ratio = available_signals / total_signals if total_signals else 0.0
    return DataCompletenessReport(
        total_signals=total_signals,
        available_signals=available_signals,
        completeness_ratio=completeness_ratio,
        missing_fields=missing,
        degraded_analyses=degraded,
        is_sufficient=completeness_ratio >= 0.5,
        vol_environment=vol_env,
    )


def _rank_strikes(
    report: dict[str, Any],
    spot_price: float | None,
    focus_count: int,
    max_distance_pct: float,
    gamma_flip: float | None = None,
) -> list[dict[str, Any]]:
    strikes: list[dict[str, Any]] = []
    for row in report.get("by_strike", []):
        strike = _coerce_float(row.get("strike"))
        net_gex = _coerce_float(row.get("net_gex")) or 0.0
        abs_gex = abs(net_gex)
        distance_pct = None
        if strike is not None and spot_price not in (None, 0.0):
            distance_pct = abs(strike - float(spot_price)) / float(spot_price)
            if distance_pct > max_distance_pct:
                continue
        importance_score = abs_gex / 1_000_000.0
        if distance_pct is not None:
            importance_score += max(0.0, 0.05 - distance_pct) * 20.0
        structural_tags: list[str] = []
        opportunity_tags: list[str] = []

        if net_gex > 0:
            structural_tags.append("long_gamma")
            if distance_pct is not None and distance_pct <= 0.02:
                opportunity_tags.append("pin_target")
        if net_gex < 0:
            structural_tags.append("short_gamma")
            if gamma_flip is not None and strike is not None and spot_price is not None:
                flip_dist = abs(strike - gamma_flip) / spot_price
                if flip_dist <= 0.02:
                    opportunity_tags.append("breakout_trigger")

        call_gex = _coerce_float(row.get("call_gex")) or 0.0
        put_gex = _coerce_float(row.get("put_gex")) or 0.0
        if call_gex > abs(put_gex):
            structural_tags.append("call_wall")
        elif abs(put_gex) > abs(call_gex):
            structural_tags.append("put_wall")

        strikes.append(
            {
                "strike": strike,
                "importance_score": round(importance_score, 4),
                "distance_from_spot_pct": round(distance_pct * 100.0, 3) if distance_pct is not None else None,
                "net_gex": net_gex,
                "call_gex": call_gex,
                "put_gex": put_gex,
                "total_oi": int(row.get("total_oi") or 0),
                "total_volume": int(row.get("total_volume") or 0),
                "structural_tags": structural_tags,
                "opportunity_tags": opportunity_tags,
                "reason": (
                    f"Strike {strike:.2f} carries {abs_gex:,.0f} net gamma exposure"
                    if strike is not None
                    else "Strike carries notable net gamma exposure"
                ),
            }
        )
    strikes.sort(key=lambda row: (-float(row["importance_score"]), abs(row["distance_from_spot_pct"] or 9999.0)))
    return strikes[:focus_count]


def _rank_expirations(
    report: dict[str, Any],
    focus_count: int,
    config: OptionsAnalysisConfig,
    spot_price: float | None = None,
) -> list[dict[str, Any]]:
    vol_env = _compute_vol_environment(report, config)
    atm_iv_global = vol_env.get("atm_iv")

    expirations: list[dict[str, Any]] = []
    for row in report.get("by_expiration", []):
        total_oi = float(row.get("total_oi", 0.0) or 0.0)
        total_volume = float(row.get("total_volume", 0.0) or 0.0)
        net_gex = _coerce_float(row.get("net_gex")) or 0.0
        abs_gex = abs(net_gex)
        score = (abs_gex / 1_000_000.0) + (total_oi / 1000.0) + (total_volume / 500.0)
        structural_tags: list[str] = []
        opportunity_tags: list[str] = []

        if net_gex > 0:
            structural_tags.append("stability_window")
        if net_gex < 0:
            structural_tags.append("expansion_window")
        if row.get("atm_iv") not in (None, ""):
            structural_tags.append("term_structure_node")

        dte = _coerce_float(row.get("dte")) or 0
        atm_iv_exp = _coerce_float(row.get("atm_iv"))
        iv_minus_rv_exp = None
        if atm_iv_exp is not None and vol_env.get("rv_20") is not None:
            iv_minus_rv_exp = atm_iv_exp - vol_env["rv_20"]

        if iv_minus_rv_exp is not None:
            if iv_minus_rv_exp > config.vol_sale_iv_rv_threshold:
                opportunity_tags.append(OPP_VOL_SALE)
            elif iv_minus_rv_exp < config.vol_buy_iv_rv_threshold:
                opportunity_tags.append(OPP_VOL_BUY)

        if atm_iv_global is not None and atm_iv_exp is not None and dte > 0:
            if atm_iv_exp > atm_iv_global * 1.15 and dte <= 14:
                opportunity_tags.append(OPP_CALENDAR_FRONT_LEG)
            elif atm_iv_exp < atm_iv_global * 0.85 and dte >= 30:
                opportunity_tags.append(OPP_CALENDAR_BACK_LEG)

        if dte <= 7 and abs_gex > 5_000_000:
            opportunity_tags.append(OPP_PIN_EXPIRY)
        elif 14 <= dte <= 45:
            opportunity_tags.append(OPP_SWING_STRUCTURE)

        if atm_iv_exp is not None and atm_iv_global is not None and atm_iv_exp > atm_iv_global * 1.25:
            opportunity_tags.append(OPP_EVENT_PREMIUM)

        expirations.append(
            {
                "expiration": row.get("expiration_date"),
                "dte": row.get("dte"),
                "importance_score": round(score, 4),
                "net_gex": net_gex,
                "abs_gex": abs_gex,
                "total_oi": total_oi,
                "total_volume": total_volume,
                "atm_iv": atm_iv_exp,
                "iv_minus_rv": iv_minus_rv_exp,
                "structural_tags": structural_tags,
                "opportunity_tags": opportunity_tags,
                "reason": f"Expiry combines {abs_gex:,.0f} net gamma with {total_oi:,.0f} open interest",
            }
        )
    expirations.sort(key=lambda row: -float(row["importance_score"]))
    return expirations[:focus_count]


def _score_strategies(
    regime_name: str,
    spot_price: float | None,
    gamma_flip: float | None,
    total_gex: float | None,
    focus_count: int,
    iv_minus_rv: float | None = None,
    iv_rank: float | None = None,
    surface_shape: str | None = None,
    forward_volatility_curve: list[dict[str, Any]] | None = None,
    skew_metrics: dict[str, Any] | None = None,
    calendar_relative_value: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    distance_pct = None
    if spot_price not in (None, 0.0) and gamma_flip is not None:
        distance_pct = abs(float(spot_price) - float(gamma_flip)) / float(spot_price)

    vol_fit_bullish = False
    vol_fit_bearish = False
    if iv_minus_rv is not None:
        vol_fit_bullish = iv_minus_rv < -0.03
        vol_fit_bearish = iv_minus_rv > 0.05

    skew_metrics = skew_metrics or {}
    forward_volatility_curve = forward_volatility_curve or []
    calendar_relative_value = calendar_relative_value or []
    put_call_25d_skew = _coerce_float(skew_metrics.get("put_call_25d_skew"))
    forward_vols: list[float] = []
    for node in forward_volatility_curve:
        forward_value = _coerce_float(node.get("forward_vol"))
        if forward_value is not None:
            forward_vols.append(forward_value)
    max_forward_vol = max(forward_vols) if forward_vols else None
    min_forward_vol = min(forward_vols) if forward_vols else None
    forward_vol_dispersion = None
    if max_forward_vol is not None and min_forward_vol is not None:
        forward_vol_dispersion = max_forward_vol - min_forward_vol
    top_pair_score = _coerce_float(calendar_relative_value[0].get("mispricing_score")) if calendar_relative_value else None

    candidates: list[dict[str, Any]] = [
        {
            "strategy": "iron_condor",
            "regime_fit_score": 0.78 if regime_name in {"pinned", "balanced"} else 0.32,
            "vol_fit_score": 0.75 if iv_minus_rv is not None and iv_minus_rv > 0.03 else 0.45,
            "thesis": "Defined-risk premium selling fits stabilizing or range-bound dealer positioning.",
            "supporting_tags": ["pin_target", "short_gamma"] if regime_name in {"pinned", "balanced"} else [],
            "conflicting_tags": ["long_gamma_here", "breakout_trigger"] if regime_name in {"pinned", "balanced"} else [],
        },
        {
            "strategy": "iron_fly",
            "regime_fit_score": 0.76 if regime_name in {"pinned", "transition"} else 0.40,
            "vol_fit_score": 0.60,
            "thesis": "Iron fly suits pinned or transition regimes where spot is near a known level.",
            "supporting_tags": ["pin_target", "calendar_spread_node"] if regime_name == "pinned" else [],
            "conflicting_tags": ["breakout_trigger"] if regime_name == "pinned" else [],
        },
        {
            "strategy": "debit_call_spread",
            "regime_fit_score": 0.74 if regime_name == "expansion" and (total_gex or 0.0) < 0 else 0.38,
            "vol_fit_score": 0.72 if vol_fit_bullish else 0.48,
            "thesis": "Bullish defined-risk delta works better when negative gamma can amplify directional continuation.",
            "supporting_tags": ["breakout_trigger", "long_delta_call", "call_wall"] if regime_name == "expansion" else [],
            "conflicting_tags": ["pin_target", "put_wall"] if regime_name == "expansion" else [],
        },
        {
            "strategy": "debit_put_spread",
            "regime_fit_score": 0.74 if regime_name == "expansion" and (total_gex or 0.0) < 0 else 0.38,
            "vol_fit_score": 0.77 if vol_fit_bearish or (put_call_25d_skew is not None and put_call_25d_skew > 0.04) else 0.48,
            "thesis": "Bearish defined-risk delta works when negative gamma, downside skew, and put pressure dominate.",
            "supporting_tags": ["breakout_trigger", "long_delta_put", "put_wall", "put_skew"] if regime_name == "expansion" else [],
            "conflicting_tags": ["pin_target", "call_wall"] if regime_name == "expansion" else [],
        },
        {
            "strategy": "long_straddle",
            "regime_fit_score": 0.76 if regime_name in {"transition", "expansion"} else 0.35,
            "vol_fit_score": 0.70 if iv_minus_rv is not None and iv_minus_rv < 0 else 0.50,
            "thesis": "Long volatility structures benefit when the market is near a regime shift or already unstable.",
            "supporting_tags": ["long_gamma_here", "breakout_trigger"] if regime_name in {"transition", "expansion"} else [],
            "conflicting_tags": ["pin_target", "short_gamma"] if regime_name in {"transition", "expansion"} else [],
        },
        {
            "strategy": "long_strangle",
            "regime_fit_score": 0.73 if regime_name in {"transition", "expansion"} else 0.38,
            "vol_fit_score": 0.68 if iv_minus_rv is not None and iv_minus_rv < 0 else 0.48,
            "thesis": "Long strangles offer cheaper vol exposure than straddles with similar directional flexibility.",
            "supporting_tags": ["long_gamma_here", "breakout_trigger"] if regime_name in {"transition", "expansion"} else [],
            "conflicting_tags": ["pin_target"] if regime_name in {"transition", "expansion"} else [],
        },
        {
            "strategy": "calendar_spread",
            "regime_fit_score": 0.78 if (distance_pct is not None and distance_pct <= 0.02) or regime_name in {"balanced", "transition", "pinned"} else 0.44,
            "vol_fit_score": 0.85 if (surface_shape in {"backwardation", "flat"} and ((forward_vol_dispersion is not None and forward_vol_dispersion >= 0.02) or (top_pair_score is not None and top_pair_score >= 0.03))) else 0.50,
            "thesis": "Calendars fit best when spot is rotating around a high-interest node and expiry-pair relative value shows a measurable mispricing.",
            "supporting_tags": ["calendar_spread_node", "term_structure_node", "forward_vol_mispricing", "calendar_pair_edge"],
            "conflicting_tags": ["breakout_trigger", "long_gamma_here"],
        },
        {
            "strategy": "butterfly_spread",
            "regime_fit_score": 0.77 if regime_name == "pinned" else 0.42,
            "vol_fit_score": 0.65 if iv_minus_rv is not None and iv_minus_rv > 0.02 else 0.50,
            "thesis": "Butterfly spreads profit from pin behavior around a specific strike.",
            "supporting_tags": ["pin_target", "short_gamma"] if regime_name == "pinned" else [],
            "conflicting_tags": ["breakout_trigger", "long_gamma_here"] if regime_name == "pinned" else [],
        },
        {
            "strategy": "credit_call_spread",
            "regime_fit_score": 0.72 if regime_name in {"balanced", "exhaustion"} else 0.40,
            "vol_fit_score": 0.70 if iv_minus_rv is not None and iv_minus_rv > 0.03 else 0.48,
            "thesis": "Credit call spreads collect premium when expecting limited upside expansion.",
            "supporting_tags": ["put_wall", "stability_window"] if regime_name == "balanced" else [],
            "conflicting_tags": ["call_wall", "breakout_trigger"] if regime_name == "balanced" else [],
        },
        {
            "strategy": "credit_put_spread",
            "regime_fit_score": 0.72 if regime_name in {"balanced", "exhaustion"} else 0.40,
            "vol_fit_score": 0.70 if iv_minus_rv is not None and iv_minus_rv > 0.03 else 0.48,
            "thesis": "Credit put spreads collect premium when expecting limited downside in a stabilized regime.",
            "supporting_tags": ["call_wall", "stability_window"] if regime_name == "balanced" else [],
            "conflicting_tags": ["put_wall", "breakout_trigger"] if regime_name == "balanced" else [],
        },
        {
            "strategy": "gamma_scalp_straddle",
            "regime_fit_score": 0.79 if regime_name in {"transition", "expansion"} else 0.34,
            "vol_fit_score": 0.78 if iv_minus_rv is not None and iv_minus_rv < -0.03 else 0.44,
            "thesis": "Delta-hedged long gamma is attractive when implied volatility is cheap relative to realized movement.",
            "supporting_tags": ["long_gamma_here", "breakout_trigger"],
            "conflicting_tags": ["pin_target", "vol_sale"],
        },
        {
            "strategy": "short_strangle_iv_rich",
            "regime_fit_score": 0.76 if regime_name in {"balanced", "pinned"} else 0.30,
            "vol_fit_score": 0.82 if (iv_rank is not None and iv_rank >= 60 and iv_minus_rv is not None and iv_minus_rv > 0.03) else 0.42,
            "thesis": "Rich implied volatility relative to expected realized movement and stable structure support wider premium-selling structures.",
            "supporting_tags": ["pin_target", "vol_sale", "stability_window", "rich_implied_vs_realized"],
            "conflicting_tags": ["breakout_trigger", "long_gamma_here"],
        },
    ]

    for candidate in candidates:
        candidate["fit_score"] = round(
            (candidate["regime_fit_score"] * 0.50)
            + (candidate.get("vol_fit_score", 0.5) * 0.30)
            + (0.20 if iv_rank is not None and iv_rank > 50 else 0.10),
            4,
        )

    candidates.sort(key=lambda row: -float(row["fit_score"]))
    return candidates[:focus_count]


def build_options_analysis(
    report: dict[str, Any],
    contracts: list[dict[str, Any]],
    prior_regime: str | None = None,
    config: OptionsAnalysisConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    report = {**report, "contracts": contracts}
    snapshot = report.get("snapshot", {})
    dealer_regime = report.get("dealer_regime", {})
    spot_price = _coerce_float(snapshot.get("spot_price"))
    total_gex = _coerce_float(snapshot.get("total_gex"))
    completeness = _build_completeness(report, contracts, config)
    regime_result = classify_regime(snapshot, dealer_regime, prior_regime=prior_regime, config=config)
    raw_gamma_flip = _coerce_float(dealer_regime.get("gamma_flip_estimate"))
    normalized_gamma_flip, gamma_flip_filtered = _normalize_gamma_flip(spot_price, raw_gamma_flip, config)
    vol_env = _compute_vol_environment(report, config)
    iv_surface = build_iv_surface(contracts, spot_price)
    strike_focus = _rank_strikes(report, spot_price, config.strike_focus_count, config.active_strike_distance_pct, normalized_gamma_flip)
    expiration_focus = _rank_expirations(report, config.expiration_focus_count, config, spot_price)
    strategy_focus = _score_strategies(
        regime_result.name,
        spot_price,
        normalized_gamma_flip,
        total_gex,
        config.strategy_focus_count,
        iv_minus_rv=vol_env.get("iv_minus_rv"),
        iv_rank=vol_env.get("iv_rank"),
        surface_shape=vol_env.get("surface_shape"),
        forward_volatility_curve=vol_env.get("forward_volatility_curve"),
        skew_metrics=vol_env.get("skew_metrics"),
        calendar_relative_value=vol_env.get("calendar_relative_value"),
    )
    backtest_blueprints = build_backtest_blueprints(vol_env)
    call_wall = dealer_regime.get("largest_call_wall") or {}
    put_wall = dealer_regime.get("largest_put_wall") or {}
    top_strike = strike_focus[0]["strike"] if strike_focus else None

    analysis = {
        "regime": regime_result.to_dict(),
        "data_completeness": completeness.to_dict(),
        "key_levels": {
            "spot_price": spot_price,
            "gamma_flip": normalized_gamma_flip,
            "call_wall": call_wall,
            "put_wall": put_wall,
            "top_strike": top_strike,
        },
        "strikes": strike_focus,
        "expirations": expiration_focus,
        "strategies": strategy_focus,
        "narrative": {
            "market_view": (
                f"Current regime is {regime_result.name} with confidence {regime_result.confidence:.2f}; the highest-priority strike is {top_strike}."
                if top_strike is not None
                else f"Current regime is {regime_result.name} with confidence {regime_result.confidence:.2f}."
            ),
            "risk_note": (
                "Analysis is running on partial data and should be treated as directional rather than complete."
                if not completeness.is_sufficient
                else "Signal coverage is sufficient for a regime-aware read of the chain."
            ),
            "volatility_view": (
                f"Vol regime is {vol_env.get('vol_regime', 'unknown')} with a {vol_env.get('surface_shape', 'unknown')} term structure."
                if "volatility" not in completeness.missing_fields
                else "Implied-vol-aware ranking is degraded because volatility inputs are incomplete."
            ),
            "quality_note": (
                "Gamma flip was excluded from active analysis because it is too far from spot; active levels are gated to strikes near spot."
                if gamma_flip_filtered
                else "Active levels are gated to strikes near spot."
            ),
        },
        "derived_metrics": {
            "wall_distance_ratio": _safe_ratio(_distance_between_levels(call_wall.get("strike"), put_wall.get("strike")), spot_price),
            "top_abs_gex_concentration": float(dealer_regime.get("top_abs_gex_concentration", 0.0)),
            "active_strike_distance_pct": config.active_strike_distance_pct,
            "iv_surface": iv_surface,
            "term_structure": vol_env.get("term_structure", []),
            "forward_volatility_curve": vol_env.get("forward_volatility_curve", []),
            "calendar_relative_value": vol_env.get("calendar_relative_value", []),
            "skew_metrics": vol_env.get("skew_metrics", {}),
            "volatility_overview": {
                "iv_rank": vol_env.get("iv_rank"),
                "iv_percentile": vol_env.get("iv_percentile"),
                "atm_iv": vol_env.get("atm_iv"),
                "rv_20": vol_env.get("rv_20"),
                "realized_implied_spread": vol_env.get("realized_implied_spread"),
                "term_structure_slope": vol_env.get("term_structure_slope"),
                "surface_shape": vol_env.get("surface_shape"),
                "vol_regime": vol_env.get("vol_regime"),
                "put_call_25d_skew": vol_env.get("put_call_25d_skew"),
                "put_atm_skew": vol_env.get("put_atm_skew"),
                "call_atm_skew": vol_env.get("call_atm_skew"),
            },
        },
        "backtest_blueprints": backtest_blueprints,
    }
    analysis["trade_suggestion"] = build_trade_suggestion(analysis, report)
    return analysis
