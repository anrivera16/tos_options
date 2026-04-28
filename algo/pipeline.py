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
from datetime import date
from typing import Any

from algo.types import CandidateSpread, PipelineResult, BacktestResult, OIWall
from algo.config import PipelineConfig
from algo.generators import generate_from_rows, _to_float, _get_mark
from algo.trend_filter import apply_trend_filter
from algo.iv_rank_filter import apply_iv_rank_filter
from algo.earnings_filter import apply_earnings_filter
from algo.wall_detector import detect_walls, fetch_strike_data_from_rows
from algo.wall_proximity import apply_proximity_filter
from algo.scoring import apply_scoring
from algo.risk_manager import RiskManager, apply_risk_filter
from algo.stop_loss import apply_stop_loss, check_exit

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

        # ---- Daily/weekly P&L reset (H1) ----
        today = snapshot_timestamp[:10]
        if today and today != self.risk_mgr.state.current_date:
            if self.risk_mgr.state.current_date:
                self.risk_mgr.reset_daily()
                try:
                    cur = date.fromisoformat(today)
                    prev = date.fromisoformat(self.risk_mgr.state.current_date)
                    if cur.isocalendar()[1] != prev.isocalendar()[1]:
                        self.risk_mgr.reset_weekly()
                except ValueError:
                    pass
            self.risk_mgr.state.current_date = today

        # ---- Exit pass: close expired or triggered positions (C3) ----
        if self.risk_mgr.state.open_positions:
            mark_lookup = _build_mark_lookup(rows)
            for pos in list(self.risk_mgr.state.open_positions):
                pos_expiry = (pos.expiration_date or "")[:10]
                if pos_expiry and pos_expiry <= today:
                    short_m, long_m = _get_leg_marks(pos, mark_lookup)
                    exit_cost = (short_m - long_m) if (short_m is not None and long_m is not None) else 0.0
                    self.risk_mgr.close_position(pos, exit_cost, today)
                    logger.info(f"Expired position closed: {pos.spread_type} {pos.short_strike}/{pos.long_strike}")
                    continue
                if self.config.stop_loss.enabled:
                    short_m, long_m = _get_leg_marks(pos, mark_lookup)
                    if short_m is not None and long_m is not None:
                        try:
                            days_held = (date.fromisoformat(today) - date.fromisoformat(pos.entry_date or today)).days
                        except ValueError:
                            days_held = 0
                        signal = check_exit(pos, short_m, long_m, days_held, self.config.stop_loss)
                        if signal.should_exit:
                            self.risk_mgr.close_position(pos, signal.current_spread_cost, today)
                            logger.info(
                                f"Stop/target exit ({signal.reason}): "
                                f"{pos.spread_type} {pos.short_strike}/{pos.long_strike} "
                                f"pnl={pos.pnl:.2f}"
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
        result.walls_detected = len(walls)

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

        # ---- Module 9: Stop-loss tagging ----
        if self.config.stop_loss.enabled:
            ranked = apply_stop_loss(ranked, self.config.stop_loss)

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
        self.reset()
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


def _build_mark_lookup(rows: list[dict[str, Any]]) -> dict[tuple, float]:
    """Build (strike, put_call, expiry) → mark price index from option chain rows."""
    lookup: dict[tuple, float] = {}
    for row in rows:
        raw = row.get("strike")
        try:
            strike = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            strike = None
        if strike is None:
            continue
        pc = row.get("put_call", "")
        expiry = (row.get("expiration_date") or "")[:10]
        mark = _get_mark(row)
        if mark > 0:
            lookup[(strike, pc, expiry)] = mark
    return lookup


def _get_leg_marks(pos: CandidateSpread, lookup: dict) -> tuple:
    """Return (short_mark, long_mark) for an open position using the lookup table."""
    pc = "PUT" if pos.spread_type == "bull_put_credit" else "CALL"
    expiry = (pos.expiration_date or "")[:10]
    short_m = lookup.get((pos.short_strike, pc, expiry))
    long_m = lookup.get((pos.long_strike, pc, expiry))
    return short_m, long_m
