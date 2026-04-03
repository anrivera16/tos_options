from __future__ import annotations

from typing import Any

from .config import OptionsAnalysisConfig
from .constants import (
    REGIME_BALANCED,
    REGIME_EXHAUSTION,
    REGIME_EXPANSION,
    REGIME_NAMES,
    REGIME_PINNED,
    REGIME_TRANSITION,
)
from .safeguards import apply_regime_hysteresis
from .types import RegimeResult


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _distance_pct(spot_price: float | None, level: float | None) -> float | None:
    if spot_price in (None, 0.0) or level is None:
        return None
    return abs(float(spot_price) - float(level)) / float(spot_price)


def _score_regimes(
    total_gex: float | None,
    spot_price: float | None,
    gamma_flip: float | None,
    call_wall: dict[str, Any] | None,
    put_wall: dict[str, Any] | None,
    concentration: float,
    config: OptionsAnalysisConfig,
) -> tuple[dict[str, float], list[str]]:
    scores = {name: 0.0 for name in REGIME_NAMES}
    reasons: list[str] = []
    flip_distance_pct = _distance_pct(spot_price, gamma_flip)
    call_wall_distance_pct = _distance_pct(spot_price, _coerce_float((call_wall or {}).get("strike")))
    put_wall_distance_pct = _distance_pct(spot_price, _coerce_float((put_wall or {}).get("strike")))

    if total_gex is None:
        scores[REGIME_BALANCED] += 0.35
        reasons.append("total_gex missing, so balanced starts as the fallback regime")
        return scores, reasons

    if total_gex > 0:
        scores[REGIME_PINNED] += 0.28
        scores[REGIME_BALANCED] += 0.2
        reasons.append("positive total_gex supports stabilizing dealer positioning")
    elif total_gex < 0:
        scores[REGIME_EXPANSION] += 0.35
        scores[REGIME_TRANSITION] += 0.12
        reasons.append("negative total_gex supports destabilizing dealer positioning")
    else:
        scores[REGIME_BALANCED] += 0.24
        scores[REGIME_TRANSITION] += 0.18
        reasons.append("flat total_gex keeps the chain near a neutral-to-transition state")

    if flip_distance_pct is not None:
        if flip_distance_pct <= config.pinned_flip_distance_pct:
            scores[REGIME_PINNED] += 0.34
            scores[REGIME_TRANSITION] += 0.18
            reasons.append("spot is extremely close to the gamma flip")
        elif flip_distance_pct <= config.transition_flip_distance_pct:
            scores[REGIME_TRANSITION] += 0.36
            scores[REGIME_BALANCED] += 0.08
            reasons.append("spot is close enough to the gamma flip to create transition risk")
        elif flip_distance_pct >= config.exhaustion_strike_distance_pct:
            scores[REGIME_EXHAUSTION] += 0.32
            if total_gex is not None and total_gex > 0:
                scores[REGIME_EXHAUSTION] += 0.15
                reasons.append("spot has moved significantly beyond the flip into potential exhaustion")
            elif total_gex is not None and total_gex < 0:
                scores[REGIME_EXPANSION] += 0.12
                reasons.append("spot is far from flip in destabilizing territory but not yet exhaustion")
            else:
                reasons.append("spot is far from gamma flip with no strong directional commitment")
        else:
            scores[REGIME_BALANCED] += 0.1
            if total_gex is not None and total_gex < 0:
                scores[REGIME_EXPANSION] += 0.18
            reasons.append("spot is not sitting on the gamma flip")

    nearby_walls = 0
    for wall_distance_pct in (call_wall_distance_pct, put_wall_distance_pct):
        if wall_distance_pct is not None and wall_distance_pct <= config.wall_pressure_distance_pct:
            nearby_walls += 1

    if nearby_walls == 2:
        scores[REGIME_PINNED] += 0.16
        scores[REGIME_TRANSITION] += 0.12
        reasons.append("call and put walls are both close enough to influence spot")
    elif nearby_walls == 1:
        scores[REGIME_BALANCED] += 0.08
        reasons.append("one nearby wall provides a partial structural anchor")

    exhaustion_indicators = 0
    extreme_wall_distance_pct = config.exhaustion_strike_distance_pct
    if call_wall_distance_pct is not None and call_wall_distance_pct >= extreme_wall_distance_pct:
        exhaustion_indicators += 1
    if put_wall_distance_pct is not None and put_wall_distance_pct >= extreme_wall_distance_pct:
        exhaustion_indicators += 1
    if exhaustion_indicators >= 1 and flip_distance_pct is not None and flip_distance_pct >= extreme_wall_distance_pct:
        scores[REGIME_EXHAUSTION] += 0.20
        reasons.append("spot is at an extreme distance from major structural levels, potential exhaustion setup")

    if concentration >= config.strong_concentration_threshold:
        scores[REGIME_PINNED] += 0.18
        scores[REGIME_BALANCED] += 0.08
        reasons.append("top gamma walls are highly concentrated")
    elif concentration <= 0.35 and total_gex is not None and total_gex < 0:
        scores[REGIME_EXPANSION] += 0.16
        reasons.append("gamma concentration is diffuse, which weakens pinning support")

    if flip_distance_pct is not None and flip_distance_pct >= config.exhaustion_strike_distance_pct:
        if total_gex is not None and total_gex > 0:
            scores[REGIME_EXHAUSTION] += 0.15
            reasons.append("positive GEX with spot far from flip suggests dealer hedging exhaustion risk")

    return scores, reasons


def classify_regime(
    snapshot: dict[str, Any],
    dealer_regime: dict[str, Any],
    prior_regime: str | None = None,
    config: OptionsAnalysisConfig | None = None,
) -> RegimeResult:
    config = config or OptionsAnalysisConfig()
    total_gex = _coerce_float(snapshot.get("total_gex"))
    spot_price = _coerce_float(snapshot.get("spot_price"))
    gamma_flip = _coerce_float(dealer_regime.get("gamma_flip_estimate"))
    call_wall = dealer_regime.get("largest_call_wall")
    put_wall = dealer_regime.get("largest_put_wall")
    concentration = float(dealer_regime.get("top_abs_gex_concentration", 0.0) or 0.0)
    flip_distance_pct = _distance_pct(spot_price, gamma_flip)
    if flip_distance_pct is not None and flip_distance_pct > config.max_reasonable_flip_distance_pct:
        gamma_flip = None

    scores, reasons = _score_regimes(total_gex, spot_price, gamma_flip, call_wall, put_wall, concentration, config)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    selected_regime, regime_changed = apply_regime_hysteresis(scores, prior_regime, config.regime_hysteresis_margin)
    top_score = ordered[0][1]
    second_score = ordered[1][1] if len(ordered) > 1 else 0.0
    score_spread = top_score - second_score
    confidence = min(0.95, max(0.3, 0.45 + score_spread))
    if prior_regime is not None and selected_regime == prior_regime and ordered[0][0] != prior_regime:
        reasons.append("hysteresis retained the prior regime because the challenger did not clear the margin")
    elif regime_changed and prior_regime is not None:
        reasons.append("hysteresis allowed the regime change because the challenger cleared the margin")
    if flip_distance_pct is not None and flip_distance_pct > config.max_reasonable_flip_distance_pct:
        reasons.append("gamma flip was ignored because it is too far from spot to be a reliable active reference")

    return RegimeResult(
        name=selected_regime,
        confidence=round(confidence, 4),
        reasons=reasons,
        gamma_flip=gamma_flip,
        all_scores={name: round(score, 4) for name, score in scores.items()},
        prior_regime=prior_regime,
        regime_changed=regime_changed,
        score_spread=round(score_spread, 4),
        hysteresis_applied=prior_regime is not None,
    )
