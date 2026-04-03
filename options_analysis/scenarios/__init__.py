from __future__ import annotations

from typing import Any

from ..config import OptionsAnalysisConfig, DEFAULT_CONFIG
from .generators import generate_scenarios, ScenarioParams


def run_scenario_analysis(
    analysis: dict[str, Any],
    config: OptionsAnalysisConfig = DEFAULT_CONFIG,
) -> list[dict[str, Any]]:
    key_levels = analysis.get("key_levels", {})
    regime = analysis.get("regime", {})
    spot_price = key_levels.get("spot_price")
    gamma_flip = key_levels.get("gamma_flip")

    if spot_price is None or spot_price <= 0:
        return []

    scenarios = generate_scenarios(
        spot_price=spot_price,
        gamma_flip=gamma_flip,
        regime_name=regime.get("name", "balanced"),
        config=config,
    )

    return [s.to_dict() for s in scenarios]
