"""
Pipeline — composes all modules into a runnable backtest pipeline.

Usage:
    from algo.pipeline import BacktestPipeline
    from algo.config import full_stack_config

    pipeline = BacktestPipeline(full_stack_config())
    results = pipeline.run_on_snapshots(snapshots)
    results.compute_summary()
"""
from __future__ import annotations

import logging
from typing import Any

from algo.types import CandidateSpread, PipelineResult, BacktestResult, OIWall
from algo.config import PipelineConfig
from algo.generators import generate_from_rows
from algo.trend_filter import apply_trend_filter
from algo.iv_rank_filter import apply_iv_rank_filter
from algo.earnings_filter import apply_earnings_filter
from algo.wall_detector import detect_walls, fetch_strike_data_from_rows
from algo.wall_proximity import apply_proximity_filter
from algo.scoring import apply_scoring
from algo.risk_manager import RiskManager, apply_risk_filter

logger = logging.getLogger(__name__)


class BacktestPipeline:
    """
    Runs the full modular pipeline over historical data.

    Each snapshot (timestamp) is processed independently:
    1. Generate raw candidates
    2. Apply filters (trend, IV rank, earnings, walls, proximity)
    3. Score and rank
    4. Risk check
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.risk_mgr = RiskManager(config.risk)
        self._all_results: list[PipelineResult] = []

    def run_on_snapshot(
        self,
        rows: list[dict[str, Any]],
        underlying_price: float,
        snapshot_timestamp: str,
        price_history: list[float] | None = None,
        historical_ivs: list[float] | None = None,
        current_iv: float | None = None,
    ) -> PipelineResult:
        """
        Run the full pipeline on a single snapshot.

        Args:
            rows: Option chain rows from DB (see generators.py for required fields)
            underlying_price: Current SPY price
            snapshot_timestamp: ISO timestamp string
            price_history: Daily closing prices for trend filter (oldest first)
            historical_ivs: Historical ATM IV readings for IV rank calc
            current_iv: Current ATM IV for IV rank calc

        Returns:
            PipelineResult with candidates at each stage
        """
        result = PipelineResult(
            timestamp=snapshot_timestamp,
            underlying=self.config.generator.underlying,
            underlying_price=underlying_price,
        )

        # ---- Module 1: Generate raw candidates ----
        candidates = generate_from_rows(
            rows, underlying_price, self.config.generator, snapshot_timestamp
        )
        result.raw_candidates = len(candidates)
        if not candidates:
            logger.debug(f"No candidates at {snapshot_timestamp}")
            return result

        # ---- Module 5: Detect walls (do this before filters so all candidates share) ----
        walls: list[OIWall] = []
        if self.config.walls.enabled or self.config.proximity.enabled:
            strike_data = fetch_strike_data_from_rows(rows)
            walls = detect_walls(strike_data, underlying_price, self.config.walls)

        # ---- Module 2: Trend filter ----
        if self.config.trend.enabled and price_history is not None:
            candidates = apply_trend_filter(
                candidates, underlying_price, price_history, self.config.trend
            )
        result.post_trend = len([c for c in candidates if c.passed])

        # ---- Module 3: IV rank filter ----
        if self.config.iv_rank.enabled and historical_ivs is not None:
            candidates = apply_iv_rank_filter(
                candidates, current_iv, historical_ivs, self.config.iv_rank
            )
        result.post_iv_rank = len([c for c in candidates if c.passed])

        # ---- Module 4: Earnings filter ----
        candidates = apply_earnings_filter(candidates, self.config.earnings)
        result.post_earnings = len([c for c in candidates if c.passed])

        # ---- Module 6: Wall proximity ----
        if self.config.proximity.enabled and walls:
            candidates = apply_proximity_filter(
                candidates, walls, underlying_price, self.config.proximity
            )
        result.post_proximity = len([c for c in candidates if c.passed])

        # ---- Module 7: Scoring ----
        passed = [c for c in candidates if c.passed]
        rejected = [c for c in candidates if not c.passed]
        result.rejected = rejected

        ranked = apply_scoring(passed, self.config.scoring)
        result.ranked = ranked

        # ---- Module 8: Risk management ----
        approved = apply_risk_filter(ranked, self.risk_mgr)
        if approved:
            self.risk_mgr.open_position(approved[0])
            result.best = approved[0]

        # Track rejections by module
        if rejected:
            self._count_rejections(result, rejected)

        self._all_results.append(result)
        return result

    def run_on_snapshots(
        self,
        snapshots: list[dict[str, Any]],
    ) -> BacktestResult:
        """
        Run the pipeline over multiple snapshots.

        Each snapshot dict should have:
            rows: list[dict] — option chain data
            underlying_price: float
            timestamp: str
            price_history: list[float] (optional)
            historical_ivs: list[float] (optional)
            current_iv: float (optional)

        Returns a BacktestResult with full summary.
        """
        bt = BacktestResult(config_name=self.config.name)

        for snap in snapshots:
            result = self.run_on_snapshot(
                rows=snap.get("rows", []),
                underlying_price=snap.get("underlying_price", 0),
                snapshot_timestamp=snap.get("timestamp", ""),
                price_history=snap.get("price_history"),
                historical_ivs=snap.get("historical_ivs"),
                current_iv=snap.get("current_iv"),
            )

            if result.best:
                bt.trades.append(result.best)

        bt.compute_summary()

        # Aggregate rejections
        for result in self._all_results:
            for c in result.rejected:
                for reason in c.rejection_reasons:
                    module = reason.split(":")[0] if ":" in reason else "unknown"
                    bt.rejections_by_module[module] = bt.rejections_by_module.get(module, 0) + 1

        return bt

    def _count_rejections(self, result: PipelineResult, rejected: list[CandidateSpread]) -> None:
        """Count rejections per module for this snapshot."""
        counts: dict[str, int] = {}
        for c in rejected:
            for reason in c.rejection_reasons:
                module = reason.split(":")[0] if ":" in reason else "unknown"
                counts[module] = counts.get(module, 0) + 1
        logger.debug(f"Rejections at {result.timestamp}: {counts}")

    def reset(self) -> None:
        """Reset pipeline state for a new backtest run."""
        self.risk_mgr = RiskManager(self.config.risk)
        self._all_results = []

    @property
    def all_results(self) -> list[PipelineResult]:
        return list(self._all_results)
