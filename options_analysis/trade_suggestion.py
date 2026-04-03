from __future__ import annotations

from typing import Any

from .types import TradeLeg, TradeSuggestion

DEFAULT_CONTEXT_LIMITATIONS = [
    "Assumes no existing position in this name",
    "Does not account for real-time fill prices or slippage",
    "Does not account for account size or max risk tolerance",
    "Does not account for similar existing positions in the portfolio",
]


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _regime_bias(regime_name: str, total_gex: float | None, top_strike: dict[str, Any] | None) -> tuple[str, str, list[str]]:
    strike_tags = set((top_strike or {}).get("opportunity_tags", []))
    strike_reason = []
    if "put_wall" in strike_tags:
        strike_reason.append("dominant nearby strike is tagged as a put wall")
    if "call_wall" in strike_tags:
        strike_reason.append("dominant nearby strike is tagged as a call wall")
    if "breakout_trigger" in strike_tags:
        strike_reason.append("top nearby strike is a breakout trigger")
    if "pin_target" in strike_tags:
        strike_reason.append("top nearby strike is a pin target")

    if regime_name == "expansion":
        if "put_wall" in strike_tags or ((total_gex or 0.0) < 0 and "breakout_trigger" in strike_tags):
            return "bearish", "put_pressure", strike_reason
        if "call_wall" in strike_tags or ((total_gex or 0.0) < 0 and "pin_target" in strike_tags):
            return "bullish", "call_pressure", strike_reason
        return "neutral", "instability", strike_reason
    if regime_name == "transition":
        return "neutral", "transition", strike_reason
    return "neutral", "range", strike_reason


def _pick_expiration(regime_name: str, strategy: str, expirations: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not expirations:
        return None
    top_two = expirations[:2] or expirations[:1]
    if strategy in {"calendar_spread", "iron_condor"}:
        medium = next(
            (
                item
                for item in top_two
                if (dte := _coerce_float(item.get("dte"))) is not None and dte >= 14.0
            ),
            None,
        )
        if medium is not None:
            return medium
    if regime_name in {"expansion", "transition"}:
        short = min(top_two, key=lambda item: float(item.get("dte") or 9999.0))
        return short
    return top_two[0]


def _pick_strikes(
    direction: str,
    strategy: str,
    spot_price: float | None,
    strikes: list[dict[str, Any]],
) -> tuple[float | None, float | None, dict[str, Any] | None]:
    if not strikes:
        return spot_price, None, None

    preferred_tags: list[str]
    if direction == "bearish":
        preferred_tags = ["put_wall", "breakout_trigger"]
    elif direction == "bullish":
        preferred_tags = ["call_wall", "breakout_trigger"]
    else:
        preferred_tags = ["pin_target", "call_wall", "put_wall", "breakout_trigger"]

    chosen = next(
        (item for item in strikes if any(tag in item.get("opportunity_tags", []) for tag in preferred_tags)),
        strikes[0],
    )
    target_strike = _coerce_float(chosen.get("strike"))
    secondary_strike = None

    ordered = sorted(
        [strike for item in strikes if (strike := _coerce_float(item.get("strike"))) is not None],
        key=lambda strike: abs(strike - float(spot_price if spot_price is not None else strike)),
    )
    reference_spot = spot_price if spot_price is not None else target_strike
    if strategy in {"put_debit_spread", "call_debit_spread", "iron_condor"} and target_strike is not None and reference_spot is not None:
        reference = float(reference_spot)
        if direction == "bearish":
            higher = next((strike for strike in ordered if strike > target_strike), None)
            lower = next((strike for strike in ordered if strike < target_strike), None)
            secondary_strike = lower if strategy == "put_debit_spread" else higher
        elif direction == "bullish":
            higher = next((strike for strike in ordered if strike > target_strike), None)
            lower = next((strike for strike in ordered if strike < target_strike), None)
            secondary_strike = higher if strategy == "call_debit_spread" else lower
        elif strategy == "iron_condor":
            far = next((strike for strike in reversed(ordered) if strike > reference), None)
            near = next((strike for strike in ordered if strike < reference), None)
            if near is not None:
                target_strike = near
            secondary_strike = far
    return target_strike, secondary_strike, chosen


def _build_rationale(
    regime_name: str,
    direction: str,
    strike: dict[str, Any] | None,
    expiration: dict[str, Any] | None,
    total_gex: float | None,
    extra_reasons: list[str],
) -> list[str]:
    rationale: list[str] = []
    if (total_gex or 0.0) < 0:
        rationale.append("negative total_gex supports destabilizing dealer positioning")
    elif (total_gex or 0.0) > 0:
        rationale.append("positive total_gex supports mean-reverting or pinning behavior")
    if strike is not None:
        tags = ", ".join(strike.get("opportunity_tags", [])) or "active structural tags"
        rationale.append(f"{strike.get('strike')} strike carries nearby {tags}")
    if expiration is not None:
        rationale.append(f"{expiration.get('expiration')} is a top-ranked expiry with {expiration.get('opportunity_tags', []) or ['active flow relevance']} driving relevance")
    if regime_name == "transition":
        rationale.append("transition regime favors long-vol structures over narrow directional bets")
    if regime_name in {"balanced", "pinned"}:
        rationale.append("stabilizing regime favors defined-risk neutral or range structures")
    if direction == "neutral" and regime_name == "expansion":
        rationale.append("expansion without clean directional alignment favors volatility exposure")
    rationale.extend(extra_reasons)
    return rationale[:3]


def _estimate_pop(
    regime_confidence: float,
    completeness_ratio: float,
    spot_price: float | None,
    target_strike: float | None,
    chosen_expiration: dict[str, Any] | None,
    chosen_strike: dict[str, Any] | None,
    strategy: str,
) -> float:
    score = 0.50
    score += 0.10 * _clamp(regime_confidence, 0.0, 1.0)
    strike_tags = set((chosen_strike or {}).get("opportunity_tags", []))
    if strategy in {"long_put", "put_debit_spread"} and ({"put_wall", "breakout_trigger"} & strike_tags):
        score += 0.05
    if strategy in {"long_call", "call_debit_spread"} and ({"call_wall", "breakout_trigger"} & strike_tags):
        score += 0.05
    if strategy in {"long_straddle", "calendar_spread", "iron_condor"} and chosen_strike is not None:
        score += 0.03
    if chosen_expiration is not None:
        score += 0.05
    if completeness_ratio < 0.75:
        score -= 0.05
    if spot_price not in (None, 0.0) and target_strike is not None:
        strike_distance_pct = abs(float(target_strike) - float(spot_price)) / float(spot_price)
        if strike_distance_pct > 0.03:
            score -= 0.05
    return round(_clamp(score, 0.35, 0.75), 2)


def build_trade_suggestion(analysis: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    regime = analysis.get("regime", {})
    key_levels = analysis.get("key_levels", {})
    strikes = analysis.get("strikes", [])
    expirations = analysis.get("expirations", [])
    completeness = analysis.get("data_completeness", {})
    narrative = analysis.get("narrative", {})
    regime_name = str(regime.get("name") or "balanced")
    regime_confidence = float(regime.get("confidence", 0.0) or 0.0)
    completeness_ratio = float(completeness.get("completeness_ratio", 0.0) or 0.0)
    spot_price = _coerce_float(key_levels.get("spot_price"))
    total_gex = _coerce_float(report.get("snapshot", {}).get("total_gex"))
    derived_metrics = analysis.get("derived_metrics", {})
    vol_overview = derived_metrics.get("volatility_overview", {})
    skew_metrics = derived_metrics.get("skew_metrics", {})
    forward_curve = derived_metrics.get("forward_volatility_curve", [])
    calendar_relative_value = derived_metrics.get("calendar_relative_value", [])
    put_call_25d_skew = _coerce_float(vol_overview.get("put_call_25d_skew") or skew_metrics.get("put_call_25d_skew"))
    realized_implied_spread = _coerce_float(vol_overview.get("realized_implied_spread"))
    forward_vol_values = [_coerce_float(node.get("forward_vol")) for node in forward_curve]
    clean_forward_vols = [value for value in forward_vol_values if value is not None]
    forward_vol_dispersion = (max(clean_forward_vols) - min(clean_forward_vols)) if clean_forward_vols else None
    top_calendar_pair = calendar_relative_value[0] if calendar_relative_value else None
    top_calendar_pair_score = _coerce_float((top_calendar_pair or {}).get("mispricing_score"))

    direction, bias, extra_reasons = _regime_bias(regime_name, total_gex, strikes[0] if strikes else None)
    degraded = completeness_ratio < 0.75

    if (
        regime_name in {"transition", "balanced", "pinned"}
        and (
            (forward_vol_dispersion is not None and forward_vol_dispersion >= 0.02)
            or (top_calendar_pair_score is not None and top_calendar_pair_score >= 0.03)
        )
    ):
        strategy = "calendar_spread"
        extra_reasons.append("forward volatility differs materially across expirations, supporting calendar relative-value")
        if top_calendar_pair is not None:
            extra_reasons.append(
                f"{top_calendar_pair.get('near_expiration')} vs {top_calendar_pair.get('far_expiration')} shows pair mispricing score {top_calendar_pair_score:.2f}"
            )
    elif regime_name == "expansion":
        if direction == "bearish":
            strategy = "put_debit_spread" if not degraded else "long_put"
        elif direction == "bullish":
            strategy = "call_debit_spread" if not degraded else "long_call"
        else:
            strategy = "long_straddle"
    elif regime_name == "transition":
        strategy = "long_straddle" if degraded else "calendar_spread"
    else:
        strategy = "credit_spread" if degraded else "iron_condor"

    if strategy in {"put_debit_spread", "long_straddle"} and put_call_25d_skew is not None and put_call_25d_skew > 0.04:
        extra_reasons.append("25-delta put skew is elevated, reinforcing downside or defensive volatility structures")
    if strategy in {"iron_condor", "credit_spread"} and realized_implied_spread is not None and realized_implied_spread > 0.03:
        extra_reasons.append("implied volatility remains rich versus realized volatility, supporting premium-selling structures")

    chosen_expiration = _pick_expiration(regime_name, strategy, expirations)
    target_strike, secondary_strike, chosen_strike = _pick_strikes(direction, strategy, spot_price, strikes)

    if strategy == "credit_spread":
        strategy = "calendar_spread"

    expiration = chosen_expiration.get("expiration") if chosen_expiration is not None else None
    rationale = _build_rationale(regime_name, direction, chosen_strike, chosen_expiration, total_gex, extra_reasons)
    if strategy == "calendar_spread" and forward_vol_dispersion is not None and forward_vol_dispersion >= 0.02:
        rationale = [
            "forward volatility differs materially across expirations, supporting calendar relative-value",
            *rationale,
        ][:3]
    if strategy == "calendar_spread" and top_calendar_pair is not None and top_calendar_pair_score is not None:
        rationale = [
            f"{top_calendar_pair.get('near_expiration')} vs {top_calendar_pair.get('far_expiration')} shows pair mispricing score {top_calendar_pair_score:.2f}",
            *rationale,
        ][:3]
    pop_estimate = _estimate_pop(
        regime_confidence,
        completeness_ratio,
        spot_price,
        target_strike,
        chosen_expiration,
        chosen_strike,
        strategy,
    )
    confidence = round(_clamp((regime_confidence * 0.7) + (completeness_ratio * 0.3), 0.25, 0.85), 2)

    nearest_barrier = None
    if direction == "bearish":
        nearest_barrier = _coerce_float((key_levels.get("call_wall") or {}).get("strike"))
    elif direction == "bullish":
        nearest_barrier = _coerce_float((key_levels.get("put_wall") or {}).get("strike"))
    else:
        nearest_barrier = _coerce_float(key_levels.get("gamma_flip"))

    if direction == "bearish":
        invalidation = f"Invalidated if spot reclaims {nearest_barrier:.0f} and regime shifts away from expansion." if nearest_barrier is not None else "Invalidated if bearish pressure fades and regime stability returns."
        valid_while = f"regime == {regime_name} and spot < {nearest_barrier:.0f}" if nearest_barrier is not None else f"regime == {regime_name}"
        entry_thesis = "Expansion regime with dominant downside pressure near active resistance."
    elif direction == "bullish":
        invalidation = f"Invalidated if spot loses {nearest_barrier:.0f} support and directional call pressure fades." if nearest_barrier is not None else "Invalidated if bullish pressure fades and regime stability returns."
        valid_while = f"regime == {regime_name} and spot > {nearest_barrier:.0f}" if nearest_barrier is not None else f"regime == {regime_name}"
        entry_thesis = "Expansion regime with upside continuation favored by nearby call-side structure."
    else:
        invalidation = "Invalidated if realized movement compresses and the regime resolves into a stable directional or pinned state."
        valid_while = f"regime == {regime_name}"
        entry_thesis = "Current structure favors owning or expressing volatility rather than leaning into a single direction."

    legs: list[TradeLeg] = []
    if target_strike is not None and expiration is not None:
        if strategy in {"long_put", "put_debit_spread"}:
            legs.append(TradeLeg(option_type="put", side="long", strike=target_strike, expiration=expiration))
            if strategy == "put_debit_spread" and secondary_strike is not None:
                legs.append(TradeLeg(option_type="put", side="short", strike=secondary_strike, expiration=expiration))
        elif strategy in {"long_call", "call_debit_spread"}:
            legs.append(TradeLeg(option_type="call", side="long", strike=target_strike, expiration=expiration))
            if strategy == "call_debit_spread" and secondary_strike is not None:
                legs.append(TradeLeg(option_type="call", side="short", strike=secondary_strike, expiration=expiration))
        elif strategy == "long_straddle":
            legs.append(TradeLeg(option_type="call", side="long", strike=target_strike, expiration=expiration))
            legs.append(TradeLeg(option_type="put", side="long", strike=target_strike, expiration=expiration))
        elif strategy == "calendar_spread":
            legs.append(TradeLeg(option_type="call", side="short_near", strike=target_strike, expiration=expiration))
        elif strategy == "iron_condor" and secondary_strike is not None:
            legs.append(TradeLeg(option_type="put", side="short", strike=target_strike, expiration=expiration))
            legs.append(TradeLeg(option_type="call", side="short", strike=secondary_strike, expiration=expiration))

    supporting_tags = []
    conflicting_tags = []

    if regime_name in {"pinned", "balanced"}:
        supporting_tags.extend(["pin_target", "short_gamma"])
        conflicting_tags.extend(["breakout_trigger", "long_gamma_here"])
    elif regime_name in {"transition", "expansion"}:
        supporting_tags.extend(["long_gamma_here", "breakout_trigger"])
        conflicting_tags.extend(["pin_target", "short_gamma"])
    elif regime_name == "exhaustion":
        supporting_tags.extend(["exhaustion_zone"])
        conflicting_tags.extend(["breakout_trigger"])

    if "vol_sale" in (expirations[0].get("opportunity_tags", []) if expirations else []):
        supporting_tags.append("vol_sale")
    if "vol_buy" in (expirations[0].get("opportunity_tags", []) if expirations else []):
        supporting_tags.append("vol_buy")

    suggestion = TradeSuggestion(
        strategy=strategy,
        direction=direction,
        expiration=expiration,
        target_strike=target_strike,
        secondary_strike=secondary_strike,
        probability_of_profit=pop_estimate,
        confidence=confidence,
        entry_thesis=entry_thesis,
        invalidation=invalidation,
        valid_while=valid_while,
        rationale=rationale or [narrative.get("market_view", "Trade idea is based on the current regime and active structural levels.")],
        legs=legs,
        context_limitations=DEFAULT_CONTEXT_LIMITATIONS,
        supporting_tags=supporting_tags,
        conflicting_tags=conflicting_tags,
    )
    return suggestion.to_dict()
