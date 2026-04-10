"""
Calendar Spread Backtest Engine

Simulates calendar spread trading with configurable parameters.
Walks through historical snapshots and executes trades based on strategy signals.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterator
import math

from scipy.stats import norm

from z0dte.backtest.csv_loader import OptionSnapshot


@dataclass
class TradePosition:
    """Represents an open calendar spread position."""
    trade_id: str
    entry_timestamp: datetime
    entry_price: float
    strike: float
    front_expiry: str
    back_expiry: str
    option_type: str
    quantity: int
    max_profit: float
    expected_hold_days: int
    
    front_iv_entry: float = 0.0
    back_iv_entry: float = 0.0
    
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0


@dataclass
class TradeResult:
    """Result of a closed trade."""
    trade_id: str
    entry_timestamp: datetime
    exit_timestamp: datetime
    entry_price: float
    exit_price: float
    strike: float
    front_expiry: str
    back_expiry: str
    option_type: str
    quantity: int
    pnl: float
    pnl_pct: float
    hold_days: float
    exit_reason: str
    max_profit: float
    front_iv_entry: float
    back_iv_entry: float


@dataclass
class SignalSnapshot:
    """Computed signal data for a snapshot."""
    timestamp: datetime
    iv_slope: float
    violation_severity: float
    is_violation: bool
    front_expiry: str
    back_expiry: str
    front_dte: int
    back_dte: int
    front_atm_iv: float
    back_atm_iv: float
    front_atm_strike: float
    back_atm_strike: float
    opportunity_score: float
    confidence: float


@dataclass
class BacktestConfig:
    """Configuration for backtest run."""
    opportunity_threshold: float = 0.60
    confidence_threshold: float = 0.55
    profit_target_pct: float = 0.35
    stop_loss_pct: float = 0.15
    max_hold_days: int = 25
    
    min_front_dte: int = 5
    min_back_dte: int = 14
    
    use_real_pricing: bool = True
    
    def __hash__(self) -> int:
        return hash((
            self.opportunity_threshold,
            self.confidence_threshold,
            self.profit_target_pct,
            self.stop_loss_pct,
            self.max_hold_days,
        ))


@dataclass
class BacktestState:
    """Current state of the backtest."""
    current_timestamp: datetime
    current_snapshot: OptionSnapshot | None
    current_signal: SignalSnapshot | None
    open_position: TradePosition | None = None
    trade_results: list[TradeResult] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    
    total_pnl: float = 0.0
    trade_count: int = 0
    winning_trades: int = 0
    
    snapshot_count: int = 0


class CalendarSpreadBacktester:
    """
    Backtest engine for calendar spread strategy.
    
    Walks through historical option snapshots and simulates trading
    calendar spreads based on term structure violations.
    """
    
    def __init__(
        self,
        snapshots: list[OptionSnapshot],
        config: BacktestConfig | None = None,
        risk_free_rate: float = 0.045,
    ):
        self.snapshots = snapshots
        self.snapshots.sort(key=lambda s: s.timestamp)
        self.config = config or BacktestConfig()
        self.risk_free_rate = risk_free_rate
        
        self.state = BacktestState(
            current_timestamp=snapshots[0].timestamp if snapshots else datetime.now(),
            current_snapshot=None,
            current_signal=None,
        )
        
        self._prior_slope: float | None = None
        self._signal_history: list[SignalSnapshot] = []
    
    def run(self) -> list[TradeResult]:
        """Run the backtest over all snapshots."""
        for snapshot in self.snapshots:
            self._process_snapshot(snapshot)
        
        self._close_all_positions()
        self._compute_equity_curve()
        
        return self.state.trade_results
    
    def _process_snapshot(self, snapshot: OptionSnapshot) -> None:
        """Process a single snapshot."""
        self.state.current_timestamp = snapshot.timestamp
        self.state.current_snapshot = snapshot
        self.state.snapshot_count += 1
        
        signal = self._compute_signal(snapshot)
        self.state.current_signal = signal
        
        if signal:
            self._signal_history.append(signal)
            self._prior_slope = signal.iv_slope
        
        if self.state.open_position:
            self._evaluate_exit(snapshot, signal)
        else:
            self._evaluate_entry(snapshot, signal)
        
        self._update_unrealized_pnl(snapshot)
    
    def _compute_signal(self, snapshot: OptionSnapshot) -> SignalSnapshot | None:
        """Compute the term structure violation signal for a snapshot."""
        if not snapshot.contracts:
            return None
        
        expirations = snapshot.get_expirations()
        if len(expirations) < 2:
            return None
        
        front_expiry: str | None = None
        back_expiry: str | None = None
        front_dte = 0
        back_dte = 0
        
        for i, exp in enumerate(expirations):
            dte = self._get_dte(snapshot, exp)
            if dte >= self.config.min_front_dte:
                front_expiry = exp
                front_dte = dte
                for j in range(i + 1, len(expirations)):
                    back_exp_j = expirations[j]
                    back_dte_j = self._get_dte(snapshot, back_exp_j)
                    if back_dte_j >= self.config.min_back_dte:
                        back_expiry = back_exp_j
                        back_dte = back_dte_j
                        break
                if back_expiry:
                    break
        
        if front_expiry is None or back_expiry is None:
            return None
        
        atm_strike = snapshot.get_atm_strike()
        if atm_strike is None:
            return None
        
        front_iv = self._get_atm_iv(snapshot, front_expiry, atm_strike)
        back_iv = self._get_atm_iv(snapshot, back_expiry, atm_strike)
        
        if front_iv is None or back_iv is None:
            return None
        
        iv_slope = front_iv - back_iv
        violation_threshold = 0.005
        is_violation = iv_slope < -violation_threshold
        violation_severity = abs(iv_slope) if is_violation else 0.0
        
        opportunity_score = self._compute_opportunity_score(
            violation_severity, front_dte, back_dte, front_iv, back_iv, self._prior_slope
        )
        
        confidence = self._compute_confidence(
            opportunity_score, violation_severity, front_dte, self._prior_slope
        )
        
        return SignalSnapshot(
            timestamp=snapshot.timestamp,
            iv_slope=iv_slope,
            violation_severity=violation_severity,
            is_violation=is_violation,
            front_expiry=front_expiry,
            back_expiry=back_expiry,
            front_dte=front_dte,
            back_dte=back_dte,
            front_atm_iv=front_iv,
            back_atm_iv=back_iv,
            front_atm_strike=atm_strike,
            back_atm_strike=atm_strike,
            opportunity_score=opportunity_score,
            confidence=confidence,
        )
        
        confidence = self._compute_confidence(
            opportunity_score, violation_severity, front_dte, self._prior_slope
        )
        
        return SignalSnapshot(
            timestamp=snapshot.timestamp,
            iv_slope=iv_slope,
            violation_severity=violation_severity,
            is_violation=is_violation,
            front_expiry=front_expiry,
            back_expiry=back_expiry,
            front_dte=front_dte,
            back_dte=back_dte,
            front_atm_iv=front_iv,
            back_atm_iv=back_iv,
            front_atm_strike=atm_strike,
            back_atm_strike=atm_strike,
            opportunity_score=opportunity_score,
            confidence=confidence,
        )
    
    def _get_dte(self, snapshot: OptionSnapshot, expiration: str) -> int:
        """Calculate DTE from expiration string."""
        try:
            exp_date = datetime.strptime(expiration, "%Y-%m-%d")
            delta = exp_date - snapshot.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            return max(0, delta.days)
        except ValueError:
            return 0
    
    def _get_atm_iv(self, snapshot: OptionSnapshot, expiration: str, strike: float) -> float | None:
        """Get ATM IV for an expiration. Estimates from price if not available."""
        contracts = snapshot.get_contracts_at_strike(strike, expiration)
        ivs = []
        for c in contracts:
            if c.volatility:
                ivs.append(c.volatility)
        
        if ivs:
            return sum(ivs) / len(ivs)
        
        for c in contracts:
            if c.mark and c.mark > 0:
                iv = self._estimate_iv_from_price(
                    snapshot.underlying_price, strike, expiration, snapshot.timestamp, c.mark, "CALL"
                )
                if iv is not None:
                    return iv
        
        return None
    
    def _estimate_iv_from_price(
        self,
        S: float,
        K: float,
        expiration: str,
        timestamp: datetime,
        price: float,
        option_type: str,
    ) -> float | None:
        """Estimate IV from option price using Newton-Raphson."""
        try:
            T = (datetime.strptime(expiration, "%Y-%m-%d") - timestamp).days / 365
            if T <= 0 or T > 5:
                return None
            
            r = self.risk_free_rate
            sigma = 0.20
            for _ in range(50):
                d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
                d2 = d1 - sigma * math.sqrt(T)
                
                if option_type.upper() == "CALL":
                    price_calc = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
                else:
                    price_calc = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
                
                diff = price - price_calc
                if abs(diff) < 0.01:
                    return sigma
                
                vega = S * norm.pdf(d1) * math.sqrt(T) / 100
                if abs(vega) < 1e-6:
                    break
                
                sigma += diff / vega * 0.5
                sigma = max(0.01, min(sigma, 2.0))
            
            return sigma
        except (ValueError, OverflowError):
            return None
    
    def _compute_opportunity_score(
        self,
        violation_severity: float,
        front_dte: int,
        back_dte: int,
        front_iv: float,
        back_iv: float,
        prior_slope: float | None,
    ) -> float:
        """Compute the overall opportunity score."""
        severity_score = min(violation_severity / 0.015, 1.0) if violation_severity > 0 else 0.0
        
        if 20 <= front_dte <= 50:
            theta_score = 1.0 - (abs(front_dte - 35) / 15 * 0.2)
        elif 15 <= front_dte <= 70:
            theta_score = 0.7
        elif front_dte < 15:
            theta_score = max(0.3, front_dte / 15 * 0.5)
        else:
            theta_score = 0.4
        
        avg_iv = (front_iv + back_iv) / 2
        if 0.12 <= avg_iv <= 0.20:
            iv_score = 1.0 - (abs(avg_iv - 0.16) / 0.04 * 0.15)
        elif 0.10 <= avg_iv <= 0.25:
            iv_score = 0.75
        elif 0.25 < avg_iv <= 0.35:
            iv_score = 0.5
        elif avg_iv > 0.35:
            iv_score = 0.2
        else:
            iv_score = 0.6
        
        momentum_score = 0.5
        if prior_slope is not None:
            slope_change = front_iv - back_iv - prior_slope
            if slope_change < -0.002:
                momentum_score = 1.0
            elif slope_change < 0:
                momentum_score = 0.8
            elif slope_change < 0.002:
                momentum_score = 0.5
            elif slope_change < 0.005:
                momentum_score = 0.3
        
        score = (
            0.35 * severity_score +
            0.30 * theta_score +
            0.20 * iv_score +
            0.15 * momentum_score
        )
        
        return max(0.0, min(score, 1.0))
    
    def _compute_confidence(
        self,
        opportunity_score: float,
        violation_severity: float,
        front_dte: int,
        prior_slope: float | None,
    ) -> float:
        """Compute confidence level for the opportunity."""
        confidence = opportunity_score
        
        if front_dte < 5:
            confidence *= 0.6
        elif front_dte < 10:
            confidence *= 0.8
        
        if violation_severity < 0.003:
            confidence *= 0.7
        
        return max(0.0, min(confidence, 1.0))
    
    def _evaluate_entry(self, snapshot: OptionSnapshot, signal: SignalSnapshot | None) -> None:
        """Evaluate whether to open a new position."""
        if signal is None:
            return
        
        if not signal.is_violation:
            return
        
        if signal.opportunity_score < self.config.opportunity_threshold:
            return
        
        if signal.confidence < self.config.confidence_threshold:
            return
        
        if self.state.open_position:
            return
        
        entry_price = self._estimate_spread_price(
            snapshot, signal, is_entry=True
        )
        
        if entry_price <= 0:
            return
        
        position = TradePosition(
            trade_id=str(uuid.uuid4()),
            entry_timestamp=signal.timestamp,
            entry_price=entry_price,
            strike=signal.front_atm_strike,
            front_expiry=signal.front_expiry,
            back_expiry=signal.back_expiry,
            option_type="CALL",
            quantity=1,
            max_profit=entry_price * 2,
            expected_hold_days=min(signal.back_dte // 2, self.config.max_hold_days),
            front_iv_entry=signal.front_atm_iv,
            back_iv_entry=signal.back_atm_iv,
            current_price=entry_price,
        )
        
        self.state.open_position = position
        self.state.trade_count += 1
    
    def _evaluate_exit(
        self, snapshot: OptionSnapshot, signal: SignalSnapshot | None
    ) -> None:
        """Evaluate whether to close the current position."""
        position = self.state.open_position
        if not position:
            return
        
        hold_days = (snapshot.timestamp - position.entry_timestamp).total_seconds() / 86400
        
        pnl_pct = position.unrealized_pnl_pct
        
        if pnl_pct >= self.config.profit_target_pct:
            self._close_position(position, snapshot, "profit_target")
            return
        
        if hold_days >= self.config.max_hold_days:
            self._close_position(position, snapshot, "max_hold")
            return
        
        if pnl_pct <= -self.config.stop_loss_pct:
            self._close_position(position, snapshot, "stop_loss")
            return
        
        if signal and signal.iv_slope > 0.01:
            self._close_position(position, snapshot, "thesis_broken")
            return
        
        if hold_days >= position.expected_hold_days and pnl_pct > 0:
            self._close_position(position, snapshot, "time_exit")
            return
    
    def _estimate_spread_price(
        self,
        snapshot: OptionSnapshot,
        signal: SignalSnapshot,
        is_entry: bool = True,
    ) -> float:
        """Estimate the calendar spread price using actual or modeled prices."""
        front_contracts = snapshot.get_contracts_at_strike(
            signal.front_atm_strike, signal.front_expiry
        )
        back_contracts = snapshot.get_contracts_at_strike(
            signal.back_atm_strike, signal.back_expiry
        )
        
        front_price = None
        back_price = None
        
        for c in front_contracts:
            if c.put_call.upper() == signal.option_type.upper():
                if c.bid and c.ask:
                    front_price = (c.bid + c.ask) / 2
                elif c.mark:
                    front_price = c.mark
                break
        
        for c in back_contracts:
            if c.put_call.upper() == signal.option_type.upper():
                if c.bid and c.ask:
                    back_price = (c.bid + c.ask) / 2
                elif c.mark:
                    back_price = c.mark
                break
        
        if front_price and back_price:
            spread_price = front_price - back_price
            if is_entry:
                spread_price *= 0.98
            return max(0.01, spread_price)
        
        if self.config.use_real_pricing:
            return self._model_spread_price(snapshot, signal, is_entry)
        
        return 2.0
    
    def _model_spread_price(
        self,
        snapshot: OptionSnapshot,
        signal: SignalSnapshot,
        is_entry: bool = True,
    ) -> float:
        """Model spread price using Black-Scholes when actual prices are unavailable."""
        S = snapshot.underlying_price
        K = signal.front_atm_strike
        r = self.risk_free_rate
        
        front_dte = signal.front_dte
        back_dte = signal.back_dte
        
        T_front = front_dte / 365
        T_back = back_dte / 365
        
        if T_front <= 0:
            return 0.0
        
        front_sigma = signal.front_atm_iv
        back_sigma = signal.back_atm_iv
        
        front_price = self._bs_call_price(S, K, T_front, r, front_sigma)
        back_price = self._bs_call_price(S, K, T_back, r, back_sigma)
        
        spread_price = front_price - back_price
        
        if is_entry:
            spread_price *= 0.98
        
        return max(0.01, spread_price)
    
    def _bs_call_price(self, S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Black-Scholes call price."""
        if T <= 0:
            return max(0, S - K)
        
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    
    def _update_unrealized_pnl(self, snapshot: OptionSnapshot) -> None:
        """Update unrealized P&L for open position."""
        position = self.state.open_position
        if not position:
            return
        
        signal = self.state.current_signal
        if signal:
            current_price = self._estimate_spread_price(
                snapshot, signal, is_entry=False
            )
        else:
            days_held = (snapshot.timestamp - position.entry_timestamp).total_seconds() / 86400
            daily_decay = position.entry_price * 0.005
            current_price = max(0.01, position.entry_price - daily_decay * days_held)
        
        position.current_price = current_price
        
        position.unrealized_pnl = position.entry_price - current_price
        position.unrealized_pnl_pct = (
            position.unrealized_pnl / position.entry_price if position.entry_price > 0 else 0
        )
        
        self.state.total_pnl = sum(t.pnl for t in self.state.trade_results) + position.unrealized_pnl
    
    def _close_position(
        self,
        position: TradePosition,
        snapshot: OptionSnapshot,
        exit_reason: str,
    ) -> None:
        """Close a position and record the result."""
        signal = self.state.current_signal
        
        exit_price = position.current_price
        
        if signal:
            exit_price = self._estimate_spread_price(snapshot, signal, is_entry=False)
        
        pnl = position.entry_price - exit_price
        pnl_pct = pnl / position.entry_price if position.entry_price > 0 else 0
        
        hold_days = (snapshot.timestamp - position.entry_timestamp).total_seconds() / 86400
        
        result = TradeResult(
            trade_id=position.trade_id,
            entry_timestamp=position.entry_timestamp,
            exit_timestamp=snapshot.timestamp,
            entry_price=position.entry_price,
            exit_price=exit_price,
            strike=position.strike,
            front_expiry=position.front_expiry,
            back_expiry=position.back_expiry,
            option_type=position.option_type,
            quantity=position.quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            hold_days=hold_days,
            exit_reason=exit_reason,
            max_profit=position.max_profit,
            front_iv_entry=position.front_iv_entry,
            back_iv_entry=position.back_iv_entry,
        )
        
        self.state.trade_results.append(result)
        self.state.total_pnl += pnl
        
        if pnl > 0:
            self.state.winning_trades += 1
        
        self.state.open_position = None
    
    def _close_all_positions(self) -> None:
        """Close any remaining open positions at end of backtest."""
        if self.state.open_position and self.state.current_snapshot:
            self._close_position(
                self.state.open_position,
                self.state.current_snapshot,
                "end_of_backtest"
            )
    
    def _compute_equity_curve(self) -> None:
        """Compute the equity curve over time."""
        if not self.state.trade_results:
            return
        
        sorted_trades = sorted(self.state.trade_results, key=lambda t: t.exit_timestamp)
        
        cumulative_pnl = 0.0
        self.state.equity_curve = []
        
        for trade in sorted_trades:
            cumulative_pnl += trade.pnl
            self.state.equity_curve.append((trade.exit_timestamp, cumulative_pnl))
    
    def get_results(self) -> list[TradeResult]:
        """Get all trade results."""
        return self.state.trade_results
    
    def get_equity_curve(self) -> list[tuple[datetime, float]]:
        """Get the equity curve."""
        return self.state.equity_curve
    
    def get_summary(self) -> dict[str, Any]:
        """Get a summary of backtest results."""
        results = self.state.trade_results
        
        if not results:
            return {
                "trade_count": 0,
                "winning_trades": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "avg_pnl": 0.0,
            }
        
        total_pnl = sum(r.pnl for r in results)
        winning_trades = sum(1 for r in results if r.pnl > 0)
        avg_hold = sum(r.hold_days for r in results) / len(results)
        
        return {
            "trade_count": len(results),
            "winning_trades": winning_trades,
            "losing_trades": len(results) - winning_trades,
            "total_pnl": total_pnl,
            "win_rate": winning_trades / len(results),
            "avg_pnl": total_pnl / len(results),
            "avg_hold_days": avg_hold,
            "config": {
                "opportunity_threshold": self.config.opportunity_threshold,
                "confidence_threshold": self.config.confidence_threshold,
                "profit_target_pct": self.config.profit_target_pct,
                "stop_loss_pct": self.config.stop_loss_pct,
                "max_hold_days": self.config.max_hold_days,
            },
        }


def run_single_backtest(
    snapshots: list[OptionSnapshot],
    config: BacktestConfig,
) -> list[TradeResult]:
    """Run a single backtest with the given configuration."""
    backtester = CalendarSpreadBacktester(snapshots, config)
    return backtester.run()
