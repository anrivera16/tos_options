"""
Calendar Spread Trading Strategy

Entry Logic:
1. Is there a term structure violation? (IVTermStructure signal)
2. Is the opportunity score high? (CalendarSpreadOpportunity signal)
3. Do we have capital available?
4. Are we not already in a position?

Exit Logic:
1. Profit target: Reach 25-50% of max profit
2. Theta target: Hold 5-10 days (depends on hold_days suggestion)
3. Stop loss: Violation reverses (IV slope turns positive)
4. Max hold: Roll forward before front month expires

Position Management:
- Track unrealized P&L
- Monitor Greeks (especially theta)
- Plan roll 3-5 days before front expiration
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import uuid

from strategies.base import Strategy


class CalendarSpreadStrategy(Strategy):
    """
    Trade calendar spreads based on term structure violations.
    
    Configuration:
        opportunity_threshold: Minimum opportunity score to enter (0-1)
        confidence_threshold: Minimum confidence level (0-1)
        capital_per_trade: Risk capital per spread position
        profit_target_pct: Exit when profit reaches X% of max
        hold_time_days: Target hold duration
        stop_loss_ratio: Exit if loss exceeds X% of entry
    """
    
    name = "calendar_spread_strategy"
    
    # Configuration
    OPPORTUNITY_THRESHOLD = 0.60
    CONFIDENCE_THRESHOLD = 0.55
    CAPITAL_PER_TRADE = 5000  # USD to allocate per trade
    PROFIT_TARGET_PCT = 0.35  # Exit at 35% profit
    HOLD_TIME_DAYS = 7
    MAX_HOLD_DAYS = 25
    STOP_LOSS_PCT = 0.15  # Exit if loss > 15%
    
    def evaluate(self, snapshot_id: int, db_conn: Any) -> dict:
        """
        Evaluate if we should open/hold/close a calendar spread position.
        
        Returns:
            {
                "action": "OPEN" | "HOLD" | "CLOSE" | "NONE",
                "reason": str,
                "signal_score": float,
                "position_data": dict (if OPEN),
                "trade_id": str (if action involves position)
            }
        """
        
        snapshot = self._load_snapshot(snapshot_id, db_conn)
        
        # First, check for existing open positions
        open_positions = self._get_open_positions(snapshot["symbol"], db_conn)
        
        if open_positions:
            # Evaluate exits
            exit_decision = self._evaluate_exit(open_positions[0], snapshot, db_conn)
            if exit_decision["action"] == "CLOSE":
                return exit_decision
            return {"action": "HOLD", "reason": "Position open, monitoring"}
        
        # No open position - check for entry opportunity
        entry_decision = self._evaluate_entry(snapshot, db_conn)
        return entry_decision
    
    def _evaluate_entry(self, snapshot: dict, db_conn: Any) -> dict:
        """
        Decide whether to open a new calendar spread position.
        """
        
        # Get the latest opportunity signal
        opportunity = self._get_latest_opportunity(snapshot["symbol"], db_conn)
        
        if not opportunity:
            return {
                "action": "NONE",
                "reason": "No opportunity signal computed yet"
            }
        
        # Check opportunity score threshold
        if opportunity["opportunity_score"] < self.OPPORTUNITY_THRESHOLD:
            return {
                "action": "NONE",
                "reason": f"Opportunity score {opportunity['opportunity_score']:.2f} below threshold {self.OPPORTUNITY_THRESHOLD}"
            }
        
        # Check confidence threshold
        if opportunity["confidence"] < self.CONFIDENCE_THRESHOLD:
            return {
                "action": "NONE",
                "reason": f"Confidence {opportunity['confidence']:.2f} below threshold {self.CONFIDENCE_THRESHOLD}"
            }
        
        # Get the underlying violation for entry details
        violation = self._get_latest_violation(snapshot["symbol"], db_conn)
        
        if not violation or not violation["is_violation"]:
            return {
                "action": "NONE",
                "reason": "No active term structure violation"
            }
        
        # Create trade record
        trade_id = str(uuid.uuid4())
        
        # Estimate entry price (spread debit/credit)
        entry_price = opportunity["estimated_entry_cost"] or 2.0
        
        db_conn.execute(
            """
            INSERT INTO calendar_spread_trades
                (trade_id, symbol, entry_timestamp, entry_snapshot_id,
                 entry_opportunity_id, entry_price, entry_reason,
                 front_expiry, back_expiry, strike, option_type,
                 quantity, status, entry_iv_slope)
            VALUES (%(trade_id)s, %(symbol)s, %(timestamp)s, %(snap_id)s,
                    %(opp_id)s, %(price)s, %(reason)s,
                    %(front_exp)s, %(back_exp)s, %(strike)s, %(type)s,
                    %(qty)s, %(status)s, %(iv_slope)s)
            """,
            {
                "trade_id": trade_id,
                "symbol": snapshot["symbol"],
                "timestamp": snapshot["captured_at"],
                "snap_id": snapshot["id"],
                "opp_id": opportunity["id"],
                "price": entry_price,
                "reason": opportunity["entry_signal"],
                "front_exp": violation["front_expiry"],
                "back_exp": violation["back_expiry"],
                "strike": opportunity["suggested_strike"],
                "type": "CALL",
                "qty": opportunity["suggested_quantity"] or 1,
                "status": "open",
                "iv_slope": violation["iv_slope"],
            },
        )
        
        db_conn.commit()
        
        return {
            "action": "OPEN",
            "reason": f"Term structure violation + opportunity score {opportunity['opportunity_score']:.2f}",
            "signal_score": opportunity["opportunity_score"],
            "trade_id": trade_id,
            "position_data": {
                "symbol": snapshot["symbol"],
                "strike": opportunity["suggested_strike"],
                "front_expiry": violation["front_expiry"],
                "back_expiry": violation["back_expiry"],
                "entry_price": entry_price,
                "max_profit": opportunity["estimated_max_profit"],
                "hold_days": opportunity["optimal_hold_days"],
            }
        }
    
    def _evaluate_exit(self, position: dict, snapshot: dict, db_conn: Any) -> dict:
        """
        Decide whether to close an existing position.
        """
        
        # Calculate P&L
        current_price = self._estimate_current_price(position, snapshot, db_conn)
        pnl = (position["entry_price"] - current_price)  # Debit spreads: profit = entry > current
        pnl_pct = pnl / position["entry_price"] if position["entry_price"] > 0 else 0
        
        hold_days = (snapshot["captured_at"] - position["entry_timestamp"]).days
        
        # Exit Condition 1: Profit target reached
        if pnl_pct >= self.PROFIT_TARGET_PCT:
            self._close_position(position["id"], current_price, snapshot, "profit_target", db_conn)
            return {
                "action": "CLOSE",
                "reason": f"Profit target: {pnl_pct:.1%} ({pnl:.2f})",
                "trade_id": position["trade_id"],
                "exit_price": current_price,
                "final_pnl": pnl,
                "final_pnl_pct": pnl_pct
            }
        
        # Exit Condition 2: Hold time reached
        if hold_days >= self.HOLD_TIME_DAYS:
            self._close_position(position["id"], current_price, snapshot, "theta_target", db_conn)
            return {
                "action": "CLOSE",
                "reason": f"Hold time reached: {hold_days} days",
                "trade_id": position["trade_id"],
                "exit_price": current_price,
                "final_pnl": pnl,
                "final_pnl_pct": pnl_pct
            }
        
        # Exit Condition 3: Stop loss
        if pnl_pct <= -self.STOP_LOSS_PCT:
            self._close_position(position["id"], current_price, snapshot, "stop_loss", db_conn)
            return {
                "action": "CLOSE",
                "reason": f"Stop loss: {pnl_pct:.1%} ({pnl:.2f})",
                "trade_id": position["trade_id"],
                "exit_price": current_price,
                "final_pnl": pnl,
                "final_pnl_pct": pnl_pct
            }
        
        # Exit Condition 4: Violation reverses + spread widens
        violation = self._get_latest_violation(snapshot["symbol"], db_conn)
        if violation and violation["iv_slope"] > 0:  # Inversion reversed
            self._close_position(position["id"], current_price, snapshot, "thesis_broken", db_conn)
            return {
                "action": "CLOSE",
                "reason": "Term structure reversed (thesis broken)",
                "trade_id": position["trade_id"],
                "exit_price": current_price,
                "final_pnl": pnl,
                "final_pnl_pct": pnl_pct
            }
        
        # Exit Condition 5: Max hold time
        if hold_days >= self.MAX_HOLD_DAYS:
            self._close_position(position["id"], current_price, snapshot, "max_hold", db_conn)
            return {
                "action": "CLOSE",
                "reason": f"Max hold time reached: {hold_days} days",
                "trade_id": position["trade_id"],
                "exit_price": current_price,
                "final_pnl": pnl,
                "final_pnl_pct": pnl_pct
            }
        
        # Position still good - hold
        return {
            "action": "HOLD",
            "reason": f"Monitoring: {pnl_pct:+.1%} P&L, {hold_days} days held",
            "trade_id": position["trade_id"],
            "current_pnl": pnl,
            "current_pnl_pct": pnl_pct
        }
    
    def _close_position(
        self,
        position_id: int,
        exit_price: float,
        snapshot: dict,
        exit_reason: str,
        db_conn: Any,
    ) -> None:
        """Mark a position as closed."""
        
        position = db_conn.execute(
            "SELECT * FROM calendar_spread_trades WHERE id = %s",
            [position_id]
        ).fetchone()
        
        final_pnl = (position["entry_price"] - exit_price)
        final_pnl_pct = final_pnl / position["entry_price"] if position["entry_price"] > 0 else 0
        hold_duration_days = (snapshot["captured_at"] - position["entry_timestamp"]).days
        
        db_conn.execute(
            """
            UPDATE calendar_spread_trades
            SET exit_timestamp = %s,
                exit_snapshot_id = %s,
                exit_price = %s,
                exit_reason = %s,
                final_pnl = %s,
                final_pnl_pct = %s,
                hold_duration_days = %s,
                status = 'closed'
            WHERE id = %s
            """,
            [
                snapshot["captured_at"],
                snapshot["id"],
                exit_price,
                exit_reason,
                final_pnl,
                final_pnl_pct,
                hold_duration_days,
                position_id
            ]
        )
        
        db_conn.commit()
    
    def _get_open_positions(self, symbol: str, db_conn: Any) -> list[dict]:
        """Get all open calendar spread trades for a symbol."""
        results = db_conn.execute(
            """
            SELECT * FROM calendar_spread_trades
            WHERE symbol = %s AND status = 'open'
            ORDER BY entry_timestamp DESC
            """,
            [symbol]
        ).fetchall()
        
        return results or []
    
    def _get_latest_opportunity(self, symbol: str, db_conn: Any) -> dict | None:
        """Get the most recent opportunity signal."""
        result = db_conn.execute(
            """
            SELECT * FROM signal_calendar_opportunities
            WHERE symbol = %s
            ORDER BY captured_at DESC
            LIMIT 1
            """,
            [symbol]
        ).fetchone()
        
        return result
    
    def _get_latest_violation(self, symbol: str, db_conn: Any) -> dict | None:
        """Get the most recent violation."""
        result = db_conn.execute(
            """
            SELECT * FROM signal_calendar_violations
            WHERE symbol = %s
            ORDER BY captured_at DESC
            LIMIT 1
            """,
            [symbol]
        ).fetchone()
        
        return result
    
    def _estimate_current_price(self, position: dict, snapshot: dict, db_conn: Any) -> float:
        """
        Estimate current spread price.
        
        In production, this would query the latest option chain
        and compute the spread bid-ask midpoint.
        
        For now, use a simple decay model.
        """
        
        # How much theta has decayed?
        hold_time = (snapshot["captured_at"] - position["entry_timestamp"]).total_seconds() / 86400
        
        # Assume daily theta decay = ~0.5% of value
        daily_decay = position["entry_price"] * 0.005
        total_decay = daily_decay * hold_time
        
        # Current price = entry - decay
        # (Assuming position was short, so decay is profit)
        current_price = position["entry_price"] - total_decay
        
        return max(0.01, current_price)  # Floor at $0.01
