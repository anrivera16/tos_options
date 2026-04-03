from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VolEnvironment(BaseModel):
    model_config = ConfigDict(extra="allow")

    iv_rank: float | None = None
    iv_percentile: float | None = None
    rv_20: float | None = None
    atm_iv: float | None = None
    iv_minus_rv: float | None = None
    vol_regime: str | None = None
    surface_shape: str | None = None
    front_month_iv: float | None = None
    back_month_iv: float | None = None
    term_structure_slope: float | None = None
    realized_implied_spread: float | None = None


class IVSurfacePoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    expiration: str | None = None
    dte: int | None = None
    strike: float | None = None
    option_type: str | None = None
    implied_volatility: float | None = None
    moneyness: float | None = None
    delta_bucket: str | None = None


class BacktestBlueprint(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    setup: str = ""
    entry_rules: list[str] = Field(default_factory=list)
    exit_rules: list[str] = Field(default_factory=list)
    metrics_to_track: list[str] = Field(default_factory=list)


class OpportunityTag(BaseModel):
    model_config = ConfigDict(extra="allow")

    tag: str
    direction: Literal["long", "short", "neutral"] = "neutral"
    thesis: str = ""
    conviction: float = Field(default=0.5, ge=0.0, le=1.0)
    regime_dependency: str | None = None
    invalidation: str = ""
    valid_while: str = ""


class StrikeData(BaseModel):
    model_config = ConfigDict(extra="allow")

    strike: float | None = None
    distance_from_spot_pct: float | None = None
    net_gex: float = 0.0
    call_gex: float = 0.0
    put_gex: float = 0.0
    total_oi: int = 0
    total_volume: int = 0
    opportunity_tags: list[str] = Field(default_factory=list)
    structural_tags: list[str] = Field(default_factory=list)


class ExpirationData(BaseModel):
    model_config = ConfigDict(extra="allow")

    expiration: str | None = None
    dte: int | None = None
    net_gex: float = 0.0
    abs_gex: float = 0.0
    total_oi: int = 0
    total_volume: int = 0
    atm_iv: float | None = None
    opportunity_tags: list[str] = Field(default_factory=list)
    structural_tags: list[str] = Field(default_factory=list)


class DataCompletenessReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_signals: int = 0
    available_signals: int = 0
    completeness_ratio: float = 0.0
    missing_fields: list[str] = Field(default_factory=list)
    degraded_analyses: list[str] = Field(default_factory=list)
    is_sufficient: bool = False
    vol_environment: VolEnvironment | None = None


class RegimeResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = "balanced"
    confidence: float = 0.5
    reasons: list[str] = Field(default_factory=list)
    gamma_flip: float | None = None
    all_scores: dict[str, float] = Field(default_factory=dict)
    prior_regime: str | None = None
    regime_changed: bool = False
    score_spread: float = 0.0
    hysteresis_applied: bool = False


class WallLevel(BaseModel):
    model_config = ConfigDict(extra="allow")

    strike: float | None = None
    call_gex: float | None = None
    put_gex: float | None = None


class KeyLevels(BaseModel):
    model_config = ConfigDict(extra="allow")

    spot_price: float | None = None
    gamma_flip: float | None = None
    call_wall: WallLevel | None = None
    put_wall: WallLevel | None = None
    top_strike: float | None = None


class StrategyFit(BaseModel):
    model_config = ConfigDict(extra="allow")

    strategy: str
    fit_score: float = 0.5
    thesis: str = ""
    vol_fit_score: float | None = None
    regime_fit_score: float | None = None
    supporting_tags: list[str] = Field(default_factory=list)
    conflicting_tags: list[str] = Field(default_factory=list)


class TradeLeg(BaseModel):
    model_config = ConfigDict(extra="allow")

    option_type: Literal["call", "put"] = "call"
    side: Literal["long", "short", "short_near", "short_far"] = "long"
    strike: float | None = None
    expiration: str | None = None


class TradeSuggestion(BaseModel):
    model_config = ConfigDict(extra="allow")

    strategy: str = "iron_condor"
    direction: Literal["bullish", "bearish", "neutral"] = "neutral"
    expiration: str | None = None
    target_strike: float | None = None
    secondary_strike: float | None = None
    probability_of_profit: float = 0.5
    confidence: float = 0.5
    entry_thesis: str = ""
    invalidation: str = ""
    valid_while: str = ""
    rationale: list[str] = Field(default_factory=list)
    probability_type: str = "POP estimate"
    legs: list[TradeLeg] = Field(default_factory=list)
    context_limitations: list[str] = Field(default_factory=list)
    supporting_tags: list[str] = Field(default_factory=list)
    conflicting_tags: list[str] = Field(default_factory=list)


class ScenarioResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    scenario_name: str
    spot_change_pct: float = 0.0
    iv_change: float = 0.0
    price_change: float | None = None
    delta_exposure: float | None = None
    gamma_exposure: float | None = None
    vega_exposure: float | None = None
    theta_exposure: float | None = None
    regime_shift: str | None = None
    description: str = ""


class OptionsAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    regime: RegimeResult
    data_completeness: DataCompletenessReport
    key_levels: KeyLevels
    strikes: list[StrikeData] = Field(default_factory=list)
    expirations: list[ExpirationData] = Field(default_factory=list)
    strategies: list[StrategyFit] = Field(default_factory=list)
    trade_suggestion: TradeSuggestion | None = None
    scenarios: list[ScenarioResult] = Field(default_factory=list)
    narrative: dict[str, str] = Field(default_factory=dict)
    derived_metrics: dict[str, Any] = Field(default_factory=dict)
    backtest_blueprints: list[BacktestBlueprint] = Field(default_factory=list)


class OptionsAnalysisInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = ""
    spot_price: float
    timestamp: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict)
    dealer_regime: dict[str, Any] = Field(default_factory=dict)
    by_strike: list[dict[str, Any]] = Field(default_factory=list)
    by_expiration: list[dict[str, Any]] = Field(default_factory=list)
    contracts: list[dict[str, Any]] = Field(default_factory=list)
    prior_regime: str | None = None

    @field_validator("spot_price")
    @classmethod
    def spot_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("spot_price must be positive")
        return v
