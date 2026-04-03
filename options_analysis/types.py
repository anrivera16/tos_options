from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class DataCompletenessReport:
    total_signals: int
    available_signals: int
    completeness_ratio: float
    missing_fields: list[str]
    degraded_analyses: list[str]
    is_sufficient: bool
    vol_environment: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RegimeResult:
    name: str
    confidence: float
    reasons: list[str]
    gamma_flip: float | None
    all_scores: dict[str, float]
    prior_regime: str | None
    regime_changed: bool
    score_spread: float
    hysteresis_applied: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TradeLeg:
    option_type: str
    side: str
    strike: float
    expiration: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TradeSuggestion:
    strategy: str
    direction: str
    expiration: str | None
    target_strike: float | None
    secondary_strike: float | None
    probability_of_profit: float
    confidence: float
    entry_thesis: str
    invalidation: str
    valid_while: str
    rationale: list[str] = field(default_factory=list)
    probability_type: str = "POP estimate"
    legs: list[TradeLeg] = field(default_factory=list)
    context_limitations: list[str] = field(default_factory=list)
    supporting_tags: list[str] = field(default_factory=list)
    conflicting_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["probability_of_profit"] = round(float(self.probability_of_profit), 2)
        payload["confidence"] = round(float(self.confidence), 2)
        return payload
