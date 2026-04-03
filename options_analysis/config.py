from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OptionsAnalysisConfig:
    pinned_flip_distance_pct: float = 0.01
    transition_flip_distance_pct: float = 0.025
    wall_pressure_distance_pct: float = 0.02
    strong_concentration_threshold: float = 0.65
    regime_hysteresis_margin: float = 0.08
    active_strike_distance_pct: float = 0.15
    max_reasonable_flip_distance_pct: float = 0.15
    strike_focus_count: int = 5
    expiration_focus_count: int = 5
    strategy_focus_count: int = 3
    exhaustion_strike_distance_pct: float = 0.08
    vol_sale_iv_rv_threshold: float = 0.05
    vol_buy_iv_rv_threshold: float = -0.05
    high_iv_threshold: float = 0.30
    low_iv_threshold: float = 0.15
    balanced_regime_alert_threshold: float = 0.40


DEFAULT_CONFIG = OptionsAnalysisConfig()
