"""
Pipeline config — all knobs in one place.

Each module has its own section. The `enabled` flag on each lets you
toggle modules on/off for backtesting combinations.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GeneratorConfig:
    """Module 1: Signal generator settings."""
    enabled: bool = True  # always True, here for symmetry
    underlying: str = "SPY"
    spread_types: list[str] = field(default_factory=lambda: ["bull_put_credit", "bear_call_credit"])
    strike_width: float = 5.0
    delta_min: float = 0.10
    delta_max: float = 0.20
    dte_min: int = 5
    dte_max: int = 9
    min_oi: int = 50
    min_volume: int = 10
    min_roc_pct: float = 10.0


@dataclass
class TrendConfig:
    """Module 2: Trend filter settings."""
    enabled: bool = True
    sma_period: int = 20
    slope_lookback: int = 3  # days to check SMA slope
    neutral_action: str = "keep_both"  # "keep_both" or "keep_none"


@dataclass
class IVRankConfig:
    """Module 3: IV rank gate settings."""
    enabled: bool = True
    iv_rank_min: float = 30.0
    iv_rank_max: float = 95.0


@dataclass
class EarningsConfig:
    """Module 4: Earnings blackout settings."""
    enabled: bool = True
    blackout_before_days: int = 1
    blackout_after_days: int = 1
    # SPY doesn't have earnings, but major holdings do
    watch_earnings_for: list[str] = field(default_factory=lambda: [
        "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "BRK.B"
    ])


@dataclass
class WallConfig:
    """Module 5: OI/Volume wall detection settings."""
    enabled: bool = True
    top_n_walls: int = 5
    min_wall_oi: int = 10000
    oi_weight: float = 0.7
    volume_weight: float = 0.3


@dataclass
class ProximityConfig:
    """Module 6: Wall proximity filter settings."""
    enabled: bool = True
    proximity_pct: float = 1.0  # reject if within this % of a wall
    direction: str = "same_side_only"  # "same_side_only" or "any"


@dataclass
class ScoringConfig:
    """Module 7: Scoring weights."""
    enabled: bool = True
    roc_weight: float = 0.35
    delta_center_weight: float = 0.20
    theta_weight: float = 0.20
    liquidity_weight: float = 0.15
    distance_weight: float = 0.10
    ideal_delta: float = 0.15  # center of 0.10-0.20


@dataclass
class RiskConfig:
    """Module 8: Risk management settings."""
    enabled: bool = True
    bankroll: float = 50000.0
    risk_per_trade_pct: float = 0.03  # 3%
    max_positions: int = 4
    daily_loss_limit: float = 500.0
    weekly_loss_limit: float = 1000.0


@dataclass
class PipelineConfig:
    """Master config — composes all module configs."""
    name: str = "default"
    generator: GeneratorConfig = field(default_factory=GeneratorConfig)
    trend: TrendConfig = field(default_factory=TrendConfig)
    iv_rank: IVRankConfig = field(default_factory=IVRankConfig)
    earnings: EarningsConfig = field(default_factory=EarningsConfig)
    walls: WallConfig = field(default_factory=WallConfig)
    proximity: ProximityConfig = field(default_factory=ProximityConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    # Backtest settings
    db_url: str = "postgresql://trader:changeme@localhost:5433/options"

    def with_module(self, module_name: str, enabled: bool) -> PipelineConfig:
        """Return a copy with one module toggled on/off."""
        from dataclasses import fields
        kwargs = {f.name: getattr(self, f.name) for f in fields(self)}
        module_cfg = getattr(self, module_name)
        from dataclasses import replace
        kwargs[module_name] = replace(module_cfg, enabled=enabled)
        return PipelineConfig(**kwargs)

    def describe(self) -> str:
        """Human-readable summary of which modules are active."""
        modules = [
            ("Trend", self.trend.enabled),
            ("IV Rank", self.iv_rank.enabled),
            ("Earnings", self.earnings.enabled),
            ("Walls", self.walls.enabled),
            ("Proximity", self.proximity.enabled),
            ("Scoring", self.scoring.enabled),
            ("Risk", self.risk.enabled),
        ]
        active = [name for name, on in modules if on]
        off = [name for name, on in modules if not on]
        parts = [f"Config: {self.name}"]
        if active:
            parts.append(f"  ON:  {', '.join(active)}")
        if off:
            parts.append(f"  OFF: {', '.join(off)}")
        return "\n".join(parts)


# Pre-built configs for common backtest scenarios

def baseline_config() -> PipelineConfig:
    """Raw signals only, no filters."""
    cfg = PipelineConfig(name="baseline")
    cfg.trend.enabled = False
    cfg.iv_rank.enabled = False
    cfg.earnings.enabled = False
    cfg.walls.enabled = False
    cfg.proximity.enabled = False
    return cfg


def trend_only_config() -> PipelineConfig:
    """Trend filter only."""
    cfg = PipelineConfig(name="trend_only")
    cfg.iv_rank.enabled = False
    cfg.earnings.enabled = False
    cfg.walls.enabled = False
    cfg.proximity.enabled = False
    return cfg


def full_stack_config() -> PipelineConfig:
    """All modules enabled."""
    return PipelineConfig(name="full_stack")
