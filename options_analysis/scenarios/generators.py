from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import OptionsAnalysisConfig


@dataclass
class ScenarioParams:
    spot_change_pct: float
    iv_change: float
    scenario_name: str
    description: str = ""


@dataclass
class ScenarioResult:
    scenario_name: str
    spot_change_pct: float
    iv_change: float
    new_spot: float
    new_iv: float | None
    price_change: float | None = None
    regime_shift: str | None = None
    description: str = ""
    delta_exposure: float | None = None
    gamma_exposure: float | None = None
    vega_exposure: float | None = None
    theta_exposure: float | None = None
    gamma_flip_new: float | None = None

    def to_dict(self) -> dict:
        return {
            "scenario_name": self.scenario_name,
            "spot_change_pct": round(self.spot_change_pct, 4),
            "iv_change": round(self.iv_change, 4),
            "new_spot": round(self.new_spot, 4) if self.new_spot else None,
            "new_iv": round(self.new_iv, 4) if self.new_iv else None,
            "price_change": round(self.price_change, 4) if self.price_change else None,
            "regime_shift": self.regime_shift,
            "description": self.description,
            "delta_exposure": round(self.delta_exposure, 4) if self.delta_exposure else None,
            "gamma_exposure": round(self.gamma_exposure, 4) if self.gamma_exposure else None,
            "vega_exposure": round(self.vega_exposure, 4) if self.vega_exposure else None,
            "theta_exposure": round(self.theta_exposure, 4) if self.theta_exposure else None,
            "gamma_flip_new": round(self.gamma_flip_new, 4) if self.gamma_flip_new else None,
        }


def _compute_regime_shift(
    regime_name: str,
    new_spot: float,
    gamma_flip: float | None,
    total_gex: float | None,
) -> str | None:
    if gamma_flip is None:
        return None

    flip_distance_pct = abs(new_spot - gamma_flip) / new_spot

    expected_regime = regime_name
    if total_gex is not None:
        if total_gex > 0 and flip_distance_pct <= 0.01:
            expected_regime = "pinned"
        elif total_gex < 0 and flip_distance_pct > 0.05:
            expected_regime = "expansion"
        elif flip_distance_pct <= 0.025:
            expected_regime = "transition"

    if expected_regime != regime_name:
        return f"regime_shift_to_{expected_regime}"
    return None


def _estimate_delta_for_move(spot_price: float, move_pct: float) -> float:
    return move_pct * 100


def _estimate_gamma_exposure(spot_price: float, move_pct: float) -> float:
    return abs(move_pct) * 50


def _estimate_vega_exposure(iv_change: float) -> float:
    return iv_change * 100


def _estimate_theta_exposure(days_pass: float = 1.0) -> float:
    return days_pass * 7


def generate_scenarios(
    spot_price: float,
    gamma_flip: float | None,
    regime_name: str,
    current_iv: float | None = None,
    total_gex: float | None = None,
    config: OptionsAnalysisConfig | None = None,
) -> list[ScenarioResult]:
    if config is None:
        config = OptionsAnalysisConfig()

    scenarios: list[ScenarioParams] = [
        ScenarioParams(spot_change_pct=0.0, iv_change=0.0, scenario_name="spot_unchanged", description="Spot unchanged, 1 day passes"),
        ScenarioParams(spot_change_pct=0.01, iv_change=0.0, scenario_name="spot_plus_1pct", description="Spot up 1%"),
        ScenarioParams(spot_change_pct=-0.01, iv_change=0.0, scenario_name="spot_minus_1pct", description="Spot down 1%"),
        ScenarioParams(spot_change_pct=0.02, iv_change=0.0, scenario_name="spot_plus_2pct", description="Spot up 2%"),
        ScenarioParams(spot_change_pct=-0.02, iv_change=0.0, scenario_name="spot_minus_2pct", description="Spot down 2%"),
        ScenarioParams(spot_change_pct=0.0, iv_change=2.0, scenario_name="iv_up_2pts", description="IV expands by 2 points"),
        ScenarioParams(spot_change_pct=0.0, iv_change=-2.0, scenario_name="iv_down_2pts", description="IV compresses by 2 points"),
        ScenarioParams(spot_change_pct=0.01, iv_change=2.0, scenario_name="spot_up_1pct_iv_up_2", description="Spot up 1% with vol expansion"),
        ScenarioParams(spot_change_pct=-0.01, iv_change=-2.0, scenario_name="spot_down_1pct_iv_down_2", description="Spot down 1% with vol crush"),
        ScenarioParams(spot_change_pct=0.02, iv_change=3.0, scenario_name="spot_up_2pct_iv_up_3", description="Spot up 2% with significant vol expansion"),
        ScenarioParams(spot_change_pct=-0.02, iv_change=3.0, scenario_name="spot_down_2pct_iv_up_3", description="Spot down 2% with vol expansion (fear scenario)"),
    ]

    results: list[ScenarioResult] = []
    for scenario in scenarios:
        new_spot = spot_price * (1 + scenario.spot_change_pct)
        new_iv = None
        if current_iv is not None:
            new_iv = max(0.0, current_iv + scenario.iv_change)

        regime_shift = _compute_regime_shift(
            regime_name=regime_name,
            new_spot=new_spot,
            gamma_flip=gamma_flip,
            total_gex=total_gex,
        )

        gamma_flip_new = None
        if gamma_flip is not None:
            gamma_flip_new = gamma_flip

        result = ScenarioResult(
            scenario_name=scenario.scenario_name,
            spot_change_pct=scenario.spot_change_pct * 100,
            iv_change=scenario.iv_change,
            new_spot=new_spot,
            new_iv=new_iv,
            price_change=scenario.spot_change_pct * 100,
            regime_shift=regime_shift,
            description=scenario.description,
            delta_exposure=_estimate_delta_for_move(spot_price, scenario.spot_change_pct),
            gamma_exposure=_estimate_gamma_exposure(spot_price, scenario.spot_change_pct),
            vega_exposure=_estimate_vega_exposure(scenario.iv_change),
            theta_exposure=_estimate_theta_exposure(1.0),
            gamma_flip_new=gamma_flip_new,
        )
        results.append(result)

    return results
