"""
Shared types for the algo pipeline.

These are kept separate from spread_hunter.spread_types so the algo
package is self-contained for backtesting. We reuse the existing Leg
and VerticalSpread from spread_hunter where possible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class TrendDirection(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class SpreadSide(Enum):
    BULL_PUT = "bull_put_credit"
    BEAR_CALL = "bear_call_credit"


@dataclass
class OIWall:
    """A support or resistance level detected from OI/volume concentration."""
    strike: float
    wall_type: str  # "support" or "resistance"
    wall_score: float  # 0-1 normalized strength
    total_oi: int
    total_volume: int
    put_call: str  # which side's OI created this wall


@dataclass
class CandidateSpread:
    """
    A spread candidate flowing through the pipeline.

    Start with fields from the signal generator, then each module adds
    its own fields or tag/reject.
    """
    # Identity
    spread_type: str  # "bull_put_credit" or "bear_call_credit"
    underlying: str
    underlying_price: float

    # Legs (raw data from generator)
    short_strike: float
    long_strike: float
    strike_width: float
    expiration_date: str
    dte: int

    # Pricing (per-share)
    short_premium: float
    long_premium: float
    credit: float
    max_loss: float
    roc_pct: float

    # Greeks (short leg)
    short_delta: Optional[float] = None
    short_theta: Optional[float] = None
    short_vega: Optional[float] = None
    short_iv: Optional[float] = None

    # Net greeks
    net_delta: Optional[float] = None
    net_theta: Optional[float] = None
    net_vega: Optional[float] = None

    # Liquidity
    short_oi: int = 0
    short_volume: int = 0
    long_oi: int = 0
    long_volume: int = 0
    min_oi: int = 0
    min_volume: int = 0

    # Pipeline state — each module adds tags/rejections
    passed: bool = True
    rejection_reasons: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    # Scoring (Module 7)
    composite_score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)

    # Backtest tracking
    entry_date: Optional[str] = None
    entry_time: Optional[str] = None
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None          # per-share P&L
    pnl_dollars: Optional[float] = None  # total dollar P&L (pnl * 100 * contracts)
    trade_result: Optional[str] = None   # "win", "loss", "partial_win", "scratch"
    contracts: int = 0

    # Trend context (set by trend filter)
    trend_direction: Optional[str] = None

    # IV rank (set by IV rank filter)
    iv_rank: Optional[float] = None

    # Wall proximity (set by wall proximity filter)
    nearest_wall_strike: Optional[float] = None
    nearest_wall_distance_pct: Optional[float] = None

    def reject(self, module: str, reason: str) -> None:
        """Mark this candidate as rejected by a module."""
        self.passed = False
        self.rejection_reasons.append(f"{module}: {reason}")

    def tag(self, tag: str) -> None:
        """Add an informational tag."""
        self.tags.append(tag)

    @property
    def is_win(self) -> Optional[bool]:
        """Did this trade win? None if not yet resolved."""
        if self.trade_result is None:
            return None
        return self.trade_result in ("win", "partial_win")


    @property
    def breakeven(self) -> float:
        """Underlying price at breakeven."""
        if self.spread_type == "bull_put_credit":
            return self.short_strike - self.credit
        else:
            return self.short_strike + self.credit

    @property
    def distance_otm_pct(self) -> float:
        """Distance from short strike to current price as %."""
        if self.underlying_price <= 0:
            return 0.0
        if self.spread_type == "bull_put_credit":
            return (self.underlying_price - self.short_strike) / self.underlying_price * 100.0
        else:
            return (self.short_strike - self.underlying_price) / self.underlying_price * 100.0


@dataclass
class PipelineResult:
    """Output of a single pipeline run (one timestamp)."""
    timestamp: str
    underlying: str
    underlying_price: float

    # Counts at each stage
    raw_candidates: int = 0
    post_trend: int = 0
    post_iv_rank: int = 0
    post_earnings: int = 0
    walls_detected: int = 0
    post_proximity: int = 0

    # Final ranked candidates
    ranked: list[CandidateSpread] = field(default_factory=list)

    # Rejected candidates (for analysis)
    rejected: list[CandidateSpread] = field(default_factory=list)

    # Best trade (top-ranked)
    best: Optional[CandidateSpread] = None


@dataclass
class BacktestResult:
    """Summary of a full backtest run."""
    config_name: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    partial_wins: int = 0
    win_rate: float = 0.0
    avg_roc: float = 0.0
    avg_pnl: float = 0.0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0

    # Per-module rejection counts
    rejections_by_module: dict[str, int] = field(default_factory=dict)

    # All individual trades for detailed analysis
    trades: list[CandidateSpread] = field(default_factory=list)

    def compute_summary(self) -> None:
        """Compute summary stats from the trades list."""
        import logging as _logging
        resolved = [t for t in self.trades if t.trade_result is not None]
        if not resolved:
            if self.trades:
                _logging.getLogger(__name__).warning(
                    f"{len(self.trades)} trades recorded but none have trade_result set — "
                    "positions were never closed. All metrics will be zero."
                )
            return

        self.total_trades = len(resolved)
        self.wins = sum(1 for t in resolved if t.trade_result == "win")
        self.partial_wins = sum(1 for t in resolved if t.trade_result == "partial_win")
        self.losses = sum(1 for t in resolved if t.trade_result == "loss")
        # partial_win = positive P&L below profit target; not counted as a full win
        self.win_rate = self.wins / self.total_trades * 100.0 if self.total_trades else 0.0

        pnls = [t.pnl or 0.0 for t in resolved]
        rocs = [t.roc_pct for t in resolved]
        self.avg_pnl = sum(pnls) / len(pnls) if pnls else 0.0
        self.avg_roc = sum(rocs) / len(rocs) if rocs else 0.0
        self.total_pnl = sum(pnls)

        gross_wins = sum(p for p in pnls if p > 0)
        gross_losses = abs(sum(p for p in pnls if p < 0))
        self.profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

        # Max drawdown from cumulative P&L
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            cumulative += p
            peak = max(peak, cumulative)
            dd = peak - cumulative
            max_dd = max(max_dd, dd)
        self.max_drawdown = max_dd
