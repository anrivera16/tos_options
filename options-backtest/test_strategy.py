#!/usr/bin/env python3
"""Unit tests for options backtest strategy logic.

Bull Put Credit Spread recap:
  - SELL put at strike K_short (higher)
  - BUY  put at strike K_long  (lower, protection)
  - Receive credit = short premium - long premium
  - Max profit = credit (both expire OTM)
  - Max loss   = width - credit (both expire ITM)
  - Breakeven  = K_short - credit

At expiry:
  - If underlying >= K_short:  both OTM, FULL WIN, P&L = +credit
  - If K_long < underlying < K_short: short ITM, partial
  - If underlying <= K_long:   both ITM, MAX LOSS, P&L = -(width - credit)
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from strategy import compute_pnl, classify_trade, select_spread, build_trading_days
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# compute_pnl tests
# ---------------------------------------------------------------------------
class TestComputePnL(unittest.TestCase):
    """Test P&L calculation for bull put credit spreads at expiry.

    Spread: SELL 620P @ $3.50, BUY 615P @ $1.50
    Width = $5, Credit = $2.00 ($200/contract)
    Max profit = $200, Max loss = $300
    """

    def _make_trade(self, **overrides):
        defaults = {
            "short_strike": 620.0,
            "long_strike": 615.0,
            "short_premium": 3.50,
            "long_premium": 1.50,
            "expiry": pd.Timestamp("2025-07-11"),
            "dte": 7,
            "short_ticker": "O:SPY250711P00620000",
            "long_ticker": "O:SPY250711P00615000",
            "actual_width": 5.0,
        }
        defaults.update(overrides)
        return defaults

    def _make_expiry_data(self, short_close=0.0, long_close=0.0,
                          short_ticker="O:SPY250711P00620000",
                          long_ticker="O:SPY250711P00615000"):
        return pd.DataFrame({
            "ticker": [short_ticker, long_ticker],
            "close": [short_close, long_close],
        })

    # -- Full win: both expire OTM --
    def test_full_win_both_worthless(self):
        """Both puts expire worthless. Keep full credit."""
        trade = self._make_trade()
        expiry = self._make_expiry_data(short_close=0.01, long_close=0.01)
        result = compute_pnl(trade, expiry)
        self.assertEqual(result["result"], "FULL_WIN")
        self.assertAlmostEqual(result["pnl_per_contract"], 200.0, places=1)

    def test_full_win_both_zero(self):
        """Both puts close at exactly 0."""
        trade = self._make_trade()
        expiry = self._make_expiry_data(short_close=0.0, long_close=0.0)
        result = compute_pnl(trade, expiry)
        self.assertEqual(result["result"], "FULL_WIN")
        self.assertAlmostEqual(result["pnl_per_contract"], 200.0, places=1)

    # -- Max loss: both deep ITM --
    def test_max_loss_both_deep_itm(self):
        """Both puts deep ITM. Loss = width - credit per share."""
        trade = self._make_trade()
        # If underlying = 610: short = 10, long = 5
        expiry = self._make_expiry_data(short_close=10.0, long_close=5.0)
        result = compute_pnl(trade, expiry)
        self.assertEqual(result["result"], "MAX_LOSS")
        self.assertAlmostEqual(result["pnl_per_contract"], -300.0, places=1)

    def test_max_loss_intrinsic(self):
        """Both ITM, spread trades at exactly width."""
        trade = self._make_trade()
        expiry = self._make_expiry_data(short_close=15.0, long_close=10.0)
        result = compute_pnl(trade, expiry)
        self.assertEqual(result["result"], "MAX_LOSS")
        self.assertAlmostEqual(result["pnl_per_contract"], -300.0, places=1)

    # -- Partial win: short slightly ITM, credit > close cost --
    def test_partial_win(self):
        """Short put slightly ITM but not enough to eat all credit."""
        trade = self._make_trade()
        # Close cost = 1.50 - 0.10 = 1.40, credit = 2.00, P&L = +0.60 ($60)
        expiry = self._make_expiry_data(short_close=1.50, long_close=0.10)
        result = compute_pnl(trade, expiry)
        self.assertEqual(result["result"], "PARTIAL_WIN")
        self.assertAlmostEqual(result["pnl_per_contract"], 60.0, places=1)

    # -- Partial loss: short ITM eats into credit --
    def test_partial_loss(self):
        """Short ITM enough to lose some but not max."""
        trade = self._make_trade()
        # Close cost = 3.80 - 0.10 = 3.70, credit = 2.00, P&L = -1.70 ($170)
        expiry = self._make_expiry_data(short_close=3.80, long_close=0.10)
        result = compute_pnl(trade, expiry)
        self.assertEqual(result["result"], "PARTIAL_LOSS")
        self.assertAlmostEqual(result["pnl_per_contract"], -170.0, places=1)

    # -- Breakeven --
    def test_breakeven(self):
        """Close cost exactly equals credit. P&L = 0."""
        trade = self._make_trade()
        # Close cost = 2.10 - 0.10 = 2.00 = credit
        expiry = self._make_expiry_data(short_close=2.10, long_close=0.10)
        result = compute_pnl(trade, expiry)
        # P&L is essentially zero
        self.assertAlmostEqual(result["pnl_per_contract"], 0.0, places=1)

    # -- P&L bounded: can't exceed max profit --
    def test_pnl_capped_at_max_profit(self):
        """Data anomaly: raw P&L exceeds credit. Should be capped."""
        trade = self._make_trade()
        # Anomalous: short=0 but long=13.58 (shouldn't happen for same expiry)
        expiry = self._make_expiry_data(short_close=0.0, long_close=13.58)
        result = compute_pnl(trade, expiry)
        # P&L should be capped at credit ($200), not $1,558
        self.assertLessEqual(result["pnl_per_contract"], 200.0)
        self.assertEqual(result["anomalous"], True)

    # -- P&L bounded: can't exceed max loss --
    def test_pnl_floored_at_max_loss(self):
        """Data anomaly: raw loss exceeds width - credit. Should be floored."""
        trade = self._make_trade()
        # Anomalous: spread value > width
        expiry = self._make_expiry_data(short_close=20.0, long_close=5.0)
        result = compute_pnl(trade, expiry)
        # Max loss = $300
        self.assertGreaterEqual(result["pnl_per_contract"], -300.0)

    # -- Missing expiry data --
    def test_no_expiry_data(self):
        """No data for the expiry date."""
        trade = self._make_trade()
        expiry = pd.DataFrame(columns=["ticker", "close"])
        result = compute_pnl(trade, expiry)
        self.assertEqual(result["result"], "NO_EXPIRY_DATA")
        self.assertIsNone(result["pnl_per_contract"])

    def test_missing_short_leg(self):
        """Short leg has no close data on expiry."""
        trade = self._make_trade()
        expiry = pd.DataFrame({
            "ticker": ["O:SPY250711P00615000"],
            "close": [0.01],
        })
        result = compute_pnl(trade, expiry)
        self.assertEqual(result["result"], "MISSING_DATA")

    def test_missing_long_leg(self):
        """Long leg has no close data on expiry."""
        trade = self._make_trade()
        expiry = pd.DataFrame({
            "ticker": ["O:SPY250711P00620000"],
            "close": [0.01],
        })
        result = compute_pnl(trade, expiry)
        self.assertEqual(result["result"], "MISSING_DATA")

    # -- Different widths --
    def test_two_dollar_width(self):
        """$2 wide spread."""
        trade = self._make_trade(
            short_strike=620.0, long_strike=618.0,
            short_premium=2.50, long_premium=1.00,
            actual_width=2.0,
        )
        # Full win
        expiry = self._make_expiry_data(short_close=0.01, long_close=0.01)
        result = compute_pnl(trade, expiry)
        self.assertEqual(result["result"], "FULL_WIN")
        self.assertAlmostEqual(result["pnl_per_contract"], 150.0, places=1)

        # Max loss
        expiry2 = self._make_expiry_data(short_close=5.0, long_close=3.0)
        result2 = compute_pnl(trade, expiry2)
        self.assertEqual(result2["result"], "MAX_LOSS")
        self.assertAlmostEqual(result2["pnl_per_contract"], -50.0, places=1)


# ---------------------------------------------------------------------------
# classify_trade tests
# ---------------------------------------------------------------------------
class TestClassifyTrade(unittest.TestCase):

    def test_full_win(self):
        self.assertEqual(classify_trade(pnl=2.0, credit=2.0, width=5.0), "FULL_WIN")

    def test_full_win_near_zero(self):
        """P&L within 5 cents of full credit."""
        self.assertEqual(classify_trade(pnl=1.95, credit=2.0, width=5.0), "FULL_WIN")

    def test_max_loss(self):
        self.assertEqual(classify_trade(pnl=-3.0, credit=2.0, width=5.0), "MAX_LOSS")

    def test_max_loss_near(self):
        """P&L within 5 cents of max loss."""
        self.assertEqual(classify_trade(pnl=-2.95, credit=2.0, width=5.0), "MAX_LOSS")

    def test_partial_win(self):
        self.assertEqual(classify_trade(pnl=1.0, credit=2.0, width=5.0), "PARTIAL_WIN")

    def test_partial_win_small(self):
        """Tiny positive P&L."""
        self.assertEqual(classify_trade(pnl=0.05, credit=2.0, width=5.0), "PARTIAL_WIN")

    def test_partial_loss(self):
        self.assertEqual(classify_trade(pnl=-1.0, credit=2.0, width=5.0), "PARTIAL_LOSS")

    def test_breakeven(self):
        """Exactly zero is a push -- classify as PARTIAL_WIN (no loss)."""
        self.assertEqual(classify_trade(pnl=0.0, credit=2.0, width=5.0), "PUSH")

    def test_invalid_pnl_above_credit(self):
        """P&L above credit is anomalous."""
        self.assertEqual(classify_trade(pnl=3.0, credit=2.0, width=5.0), "ANOMALOUS")

    def test_invalid_pnl_below_max_loss(self):
        """P&L below -(width - credit) is anomalous."""
        self.assertEqual(classify_trade(pnl=-4.0, credit=2.0, width=5.0), "ANOMALOUS")


# ---------------------------------------------------------------------------
# select_spread tests
# ---------------------------------------------------------------------------
class TestSelectSpread(unittest.TestCase):

    def _make_puts(self, strikes_and_premiums, dte=7, expiry="2025-07-11"):
        """Helper to create a puts DataFrame.

        strikes_and_premiums: list of (strike, open_price)
        """
        rows = []
        for i, (strike, premium) in enumerate(strikes_and_premiums):
            rows.append({
                "ticker": f"O:SPY250711P00{strike:05d}",
                "strike": float(strike),
                "open": premium,
                "volume": 100,
                "option_type": "P",
                "dte": dte,
                "expiry": pd.Timestamp(expiry),
                "date": pd.Timestamp("2025-07-01"),
            })
        return pd.DataFrame(rows)

    def test_basic_selection(self):
        """Should select a put spread at the requested delta/width."""
        # Create puts from ITM to OTM: strikes 630 down to 600
        puts = self._make_puts([
            (630, 12.0), (625, 8.0), (620, 5.0),
            (615, 3.0), (610, 1.50), (605, 0.60), (600, 0.20),
        ])
        trade = select_spread(puts, dte_range=(5, 7), width=5.0, delta_pct=15)
        self.assertIsNotNone(trade)
        # Short should be roughly 15th percentile from ATM (OTM = lower strikes for puts)
        # Long should be $5 below short
        self.assertGreater(trade["short_strike"], trade["long_strike"])
        self.assertAlmostEqual(trade["actual_width"], 5.0, places=1)

    def test_no_candidates_wrong_dte(self):
        """No puts in the DTE range."""
        puts = self._make_puts([(620, 5.0), (615, 3.0)], dte=14)
        trade = select_spread(puts, dte_range=(5, 7), width=5.0, delta_pct=15)
        self.assertIsNone(trade)

    def test_no_matching_long_leg(self):
        """Not enough strike range for the requested width."""
        puts = self._make_puts([(620, 5.0), (619, 4.5)])
        trade = select_spread(puts, dte_range=(5, 7), width=5.0, delta_pct=15)
        self.assertIsNone(trade)

    def test_prefers_closer_to_target_dte(self):
        """When multiple expiries available, prefer the one closest to dte_max."""
        rows = []
        for dte, expiry in [(5, "2025-07-08"), (7, "2025-07-11")]:
            for strike, premium in [(620, 5.0), (615, 3.0), (610, 1.5), (605, 0.5)]:
                rows.append({
                    "ticker": f"O:SPY{expiry.replace('-','')}P00{strike:05d}",
                    "strike": float(strike),
                    "open": premium,
                    "volume": 100,
                    "option_type": "P",
                    "dte": dte,
                    "expiry": pd.Timestamp(expiry),
                    "date": pd.Timestamp("2025-07-01"),
                })
        puts = pd.DataFrame(rows)
        trade = select_spread(puts, dte_range=(5, 7), width=5.0, delta_pct=15)
        self.assertIsNotNone(trade)
        # Should pick the 7 DTE expiry
        self.assertEqual(trade["dte"], 7)

    def test_empty_puts(self):
        """Empty DataFrame returns None."""
        puts = pd.DataFrame(columns=["ticker", "strike", "open", "volume",
                                      "option_type", "dte", "expiry", "date"])
        trade = select_spread(puts, dte_range=(5, 7), width=5.0, delta_pct=15)
        self.assertIsNone(trade)

    def test_zero_volume_skipped(self):
        """Puts with zero volume should still be selectable (illiquid strikes)."""
        puts = self._make_puts([
            (620, 5.0), (615, 3.0), (610, 1.5), (605, 0.5),
        ])
        puts.loc[2, "volume"] = 0  # Zero volume on one strike
        trade = select_spread(puts, dte_range=(5, 7), width=5.0, delta_pct=15)
        self.assertIsNotNone(trade)


# ---------------------------------------------------------------------------
# build_trading_days tests
# ---------------------------------------------------------------------------
class TestBuildTradingDays(unittest.TestCase):

    def test_weekdays_only(self):
        """Should only include Mon-Fri."""
        from strategy import build_trading_days
        # July 4 2025 = Friday, but holiday. Our function returns all weekdays.
        # Let's just verify Mon-Fri only.
        days = build_trading_days("2025-07-07", "2025-07-11")
        # Mon 7/7 through Fri 7/11 = 5 days
        self.assertEqual(len(days), 5)

    def test_single_day(self):
        days = build_trading_days("2025-07-07", "2025-07-07")
        self.assertEqual(len(days), 1)

    def test_weekend_only_range(self):
        """A range that's only Sat-Sun should return empty."""
        days = build_trading_days("2025-07-05", "2025-07-06")
        self.assertEqual(len(days), 0)


if __name__ == "__main__":
    unittest.main()
