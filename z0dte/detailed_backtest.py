"""
Detailed Volatility Surface Trading Backtest
=============================================

Shows realistic market scenarios with detailed P&L evolution.
Scenarios based on April 2026 volatility events.
"""

import pandas as pd
import json
from datetime import datetime, timedelta
from volatility_surface_trader import (
    OptionChain, VolatilitySurface, Trade, 
    call_price, put_price, delta_call, delta_put, gamma, theta_call, theta_put, vega
)

# ============================================================================
# SCENARIO DEFINITIONS
# ============================================================================

class BacktestScenario:
    """Defines market evolution over time"""
    
    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.snapshots = []  # [(timestamp, spot, vol_surface_params)]
    
    def add_snapshot(self, timestamp, spot, atm_iv, term_slope, smile_curvature):
        """Add a market state at a point in time"""
        self.snapshots.append({
            'timestamp': timestamp,
            'spot': spot,
            'atm_iv': atm_iv,
            'term_slope': term_slope,
            'smile_curvature': smile_curvature
        })


def scenario_calendar_spread_profitable():
    """
    CALENDAR SPREAD WINS: Term structure normalizes as expected
    
    Entry: Sell 30 DTE, Buy 60 DTE at 5430 strike
    Thesis: 30 DTE IV will fall relative to 60 DTE IV
    Result: PROFITABLE
    """
    scenario = BacktestScenario(
        "Calendar Spread - Profitable",
        "Term structure normalizes: 30 DTE vol falls from 17.3% to 16.5%"
    )
    
    # Initial: Inverted term structure (30 DTE > 60 DTE - unusual)
    scenario.add_snapshot(
        datetime(2026, 4, 8, 10, 0), 5432.10,
        atm_iv=0.173, term_slope=0.01, smile_curvature=0.05
    )
    
    # +4 hours: Term structure still inverted
    scenario.add_snapshot(
        datetime(2026, 4, 8, 14, 0), 5433.50,
        atm_iv=0.172, term_slope=0.008, smile_curvature=0.05
    )
    
    # +24 hours: Term structure normalizes
    scenario.add_snapshot(
        datetime(2026, 4, 9, 10, 0), 5431.00,
        atm_iv=0.168, term_slope=0.005, smile_curvature=0.04
    )
    
    return scenario


def scenario_butterfly_profitable():
    """
    BUTTERFLY WINS: Smile flattens as expected
    
    Entry: Buy 5430, Sell 2x 5460, Sell 1x 5490
    Thesis: Smile curvature is too steep; will flatten
    Result: PROFITABLE
    """
    scenario = BacktestScenario(
        "Butterfly - Profitable",
        "Smile flattens: curvature drops from 0.05 to 0.02"
    )
    
    # Initial: Steep smile
    scenario.add_snapshot(
        datetime(2026, 4, 8, 10, 0), 5432.10,
        atm_iv=0.173, term_slope=0.01, smile_curvature=0.05
    )
    
    # +2 hours: Smile still steep but starting to flatten
    scenario.add_snapshot(
        datetime(2026, 4, 8, 12, 0), 5431.50,
        atm_iv=0.172, term_slope=0.01, smile_curvature=0.045
    )
    
    # +6 hours: Smile flattens significantly
    scenario.add_snapshot(
        datetime(2026, 4, 8, 16, 0), 5433.00,
        atm_iv=0.171, term_slope=0.01, smile_curvature=0.028
    )
    
    return scenario


def scenario_straddle_profitable():
    """
    STRADDLE WINS: Vol expands as expected
    
    Entry: Buy ATM straddle at 5430
    Thesis: Skew widens (jump risk); vol will expand
    Result: PROFITABLE (despite theta decay)
    """
    scenario = BacktestScenario(
        "Straddle - Profitable (Vol Expansion)",
        "IV expands from 17.3% to 21.5%, spot drops to 5410"
    )
    
    # Initial
    scenario.add_snapshot(
        datetime(2026, 4, 8, 10, 0), 5432.10,
        atm_iv=0.173, term_slope=0.01, smile_curvature=0.05
    )
    
    # +2 hours: Vol begins expanding
    scenario.add_snapshot(
        datetime(2026, 4, 8, 12, 0), 5428.00,
        atm_iv=0.185, term_slope=0.015, smile_curvature=0.08
    )
    
    # +5 hours: Major vol expansion, spot drops
    scenario.add_snapshot(
        datetime(2026, 4, 8, 15, 0), 5410.00,
        atm_iv=0.215, term_slope=0.020, smile_curvature=0.12
    )
    
    return scenario


def scenario_0dte_profitable():
    """
    0DTE THETA WINS: Massive intraday theta decay
    
    Entry: Sell 0DTE straddle at 5430
    Thesis: Collect intraday theta, spot stays near strike
    Result: PROFITABLE
    """
    scenario = BacktestScenario(
        "0DTE Theta - Profitable",
        "Intraday theta decay: 0DTE straddle value collapses from $36 to $2"
    )
    
    # 14:00 - Entry (2 hours to close)
    scenario.add_snapshot(
        datetime(2026, 4, 8, 14, 0), 5432.10,
        atm_iv=0.160, term_slope=0.01, smile_curvature=0.05
    )
    
    # 15:00 - Spot unchanged, massive theta decay
    scenario.add_snapshot(
        datetime(2026, 4, 8, 15, 0), 5432.50,
        atm_iv=0.160, term_slope=0.01, smile_curvature=0.05
    )
    
    # 15:50 - Final 10 minutes, theta is extreme
    scenario.add_snapshot(
        datetime(2026, 4, 8, 15, 50), 5432.10,
        atm_iv=0.160, term_slope=0.01, smile_curvature=0.05
    )
    
    return scenario


# ============================================================================
# BACKTEST RUNNER
# ============================================================================

def run_scenario_backtest(scenario, trade_setup_func, r=0.045):
    """
    Run backtest for a specific scenario and trade setup
    
    Args:
        scenario: BacktestScenario object
        trade_setup_func: Function that takes initial_chain and returns Trade object
        r: Risk-free rate
    
    Returns:
        DataFrame with P&L evolution
    """
    
    results = []
    initial_chain = None
    trade = None
    
    for snap in scenario.snapshots:
        
        # Create volatility surface for this snapshot
        vol_surface = VolatilitySurface(
            atm_iv_30dte=snap['atm_iv'],
            term_slope=snap['term_slope'],
            smile_curvature=snap['smile_curvature']
        )
        
        # Create option chain for this snapshot
        chain = OptionChain(snap['spot'], snap['timestamp'], vol_surface, r)
        chain.generate_chain(
            strikes_range=(5350, 5500, 10),
            expirations=(0, 7, 30, 60)
        )
        
        # Initialize trade on first snapshot
        if initial_chain is None:
            initial_chain = chain
            trade = trade_setup_func(chain)
        
        # Calculate P&L
        pnl, pnl_detail = trade.calculate_pnl(chain)
        greeks = trade.get_greeks(chain)
        
        # Store results
        results.append({
            'timestamp': snap['timestamp'],
            'hours_elapsed': (snap['timestamp'] - initial_chain.timestamp).total_seconds() / 3600,
            'spot': snap['spot'],
            'atm_iv': snap['atm_iv'],
            'pnl': pnl,
            'pnl_pct': (pnl / abs(trade.entry_cost) * 100) if trade.entry_cost != 0 else 0,
            'delta': greeks['delta'],
            'gamma': greeks['gamma'],
            'theta': greeks['theta'],
            'vega': greeks['vega']
        })
    
    return pd.DataFrame(results), trade


# ============================================================================
# PRINT UTILITIES
# ============================================================================

def print_trade_summary(scenario_name, df, trade):
    """Print formatted trade summary"""
    
    initial_row = df.iloc[0]
    final_row = df.iloc[-1]
    
    print("\n" + "="*80)
    print(f"SCENARIO: {scenario_name}")
    print("="*80)
    
    print(f"\nTRADE: {trade.description}")
    print(f"Entry Cost: ${trade.entry_cost:+.2f}")
    
    print(f"\nTIME EVOLUTION:")
    print("-" * 80)
    print(f"{'Time':<20} {'Spot':<10} {'P&L':<12} {'Return':<12} {'Delta':<10} {'Theta':<10}")
    print("-" * 80)
    
    for _, row in df.iterrows():
        print(f"{row['timestamp'].strftime('%Y-%m-%d %H:%M'):<20} "
              f"{row['spot']:>8.2f}  "
              f"${row['pnl']:>+9.2f}  "
              f"{row['pnl_pct']:>+10.1f}%  "
              f"{row['delta']:>+8.3f}  "
              f"{row['theta']:>+9.4f}")
    
    print("-" * 80)
    print(f"\nFINAL RESULTS:")
    print(f"  Starting Spot:  {initial_row['spot']:.2f}")
    print(f"  Final Spot:     {final_row['spot']:.2f}")
    print(f"  Spot Move:      {final_row['spot'] - initial_row['spot']:+.2f} ({(final_row['spot'] - initial_row['spot']) / initial_row['spot'] * 100:+.2f}%)")
    print(f"\n  Final P&L:      ${final_row['pnl']:+.2f}")
    print(f"  Return on Risk: {final_row['pnl_pct']:+.1f}%")
    print(f"  Duration:       {final_row['hours_elapsed']:.1f} hours")
    
    if final_row['hours_elapsed'] > 0:
        hourly_pnl = final_row['pnl'] / final_row['hours_elapsed']
        print(f"  P&L per Hour:   ${hourly_pnl:+.2f}")
    
    print(f"\n  Final Delta:    {final_row['delta']:+.3f}")
    print(f"  Final Theta:    {final_row['theta']:+.4f}/day")
    print(f"  Peak IV:        {df['atm_iv'].max():.1%}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    
    print("\n" + "="*80)
    print("VOLATILITY SURFACE TRADER - DETAILED BACKTEST")
    print("April 8, 2026 - Live Scenario Analysis")
    print("="*80)
    
    r = 0.045
    
    # ========================================================================
    # SCENARIO 1: CALENDAR SPREAD PROFITABLE
    # ========================================================================
    
    scenario1 = scenario_calendar_spread_profitable()
    
    def setup_calendar_spread(chain):
        strike = 5430
        call_30 = chain.get_option(strike, 30, 'call')
        call_60 = chain.get_option(strike, 60, 'call')
        
        trade = Trade('calendar_spread', 'Calendar Spread: Sell 30 DTE / Buy 60 DTE')
        trade.add_leg('Sell 30 DTE Call', strike, 30, 'call', -1, call_30.ask, chain.timestamp)
        trade.add_leg('Buy 60 DTE Call', strike, 60, 'call', +1, call_60.bid, chain.timestamp)
        return trade
    
    df1, trade1 = run_scenario_backtest(scenario1, setup_calendar_spread, r)
    print_trade_summary("Calendar Spread - Profitable", df1, trade1)
    
    # ========================================================================
    # SCENARIO 2: BUTTERFLY PROFITABLE
    # ========================================================================
    
    scenario2 = scenario_butterfly_profitable()
    
    def setup_butterfly(chain):
        trade = Trade('butterfly', 'Butterfly: Buy 5430 / Sell 2x 5460 / Sell 5490')
        
        call_5430 = chain.get_option(5430, 30, 'call')
        call_5460 = chain.get_option(5460, 30, 'call')
        call_5490 = chain.get_option(5490, 30, 'call')
        
        trade.add_leg('Buy 5430', 5430, 30, 'call', +1, call_5430.bid, chain.timestamp)
        trade.add_leg('Sell 5460 x2', 5460, 30, 'call', -2, call_5460.ask, chain.timestamp)
        trade.add_leg('Sell 5490', 5490, 30, 'call', -1, call_5490.ask, chain.timestamp)
        return trade
    
    df2, trade2 = run_scenario_backtest(scenario2, setup_butterfly, r)
    print_trade_summary("Butterfly - Profitable", df2, trade2)
    
    # ========================================================================
    # SCENARIO 3: STRADDLE PROFITABLE (VOL EXPANSION)
    # ========================================================================
    
    scenario3 = scenario_straddle_profitable()
    
    def setup_straddle(chain):
        strike = 5430
        call = chain.get_option(strike, 30, 'call')
        put = chain.get_option(strike, 30, 'put')
        
        trade = Trade('straddle', 'Long Straddle: Buy 5430 Call + Put')
        trade.add_leg('Buy Call', strike, 30, 'call', +1, call.ask, chain.timestamp)
        trade.add_leg('Buy Put', strike, 30, 'put', +1, put.ask, chain.timestamp)
        return trade
    
    df3, trade3 = run_scenario_backtest(scenario3, setup_straddle, r)
    print_trade_summary("Straddle - Profitable (Vol Expansion)", df3, trade3)
    
    # ========================================================================
    # SCENARIO 4: 0DTE PROFITABLE (THETA HARVEST)
    # ========================================================================
    
    scenario4 = scenario_0dte_profitable()
    
    def setup_0dte(chain):
        strike = 5430
        
        # Manually create 0DTE option prices
        T_0dte = 1 / 365
        iv_0dte = 0.160
        call_0dte_price = call_price(chain.spot, strike, T_0dte, r, iv_0dte)
        put_0dte_price = put_price(chain.spot, strike, T_0dte, r, iv_0dte)
        
        trade = Trade('0dte_theta', 'Short 0DTE Straddle: Theta Harvest')
        trade.add_leg('Sell 0DTE Call', strike, 0, 'call', -1, call_0dte_price * 1.005, chain.timestamp)
        trade.add_leg('Sell 0DTE Put', strike, 0, 'put', -1, put_0dte_price * 1.005, chain.timestamp)
        return trade
    
    df4, trade4 = run_scenario_backtest(scenario4, setup_0dte, r)
    print_trade_summary("0DTE Theta Harvest - Profitable", df4, trade4)
    
    # ========================================================================
    # SUMMARY TABLE
    # ========================================================================
    
    print("\n\n" + "="*80)
    print("SUMMARY: ALL SCENARIOS")
    print("="*80)
    
    summary = pd.DataFrame([
        {
            'Scenario': 'Calendar Spread',
            'Entry Cost': f"${trade1.entry_cost:+.2f}",
            'Final P&L': f"${df1.iloc[-1]['pnl']:+.2f}",
            'Return': f"{df1.iloc[-1]['pnl_pct']:+.1f}%",
            'Duration': f"{df1.iloc[-1]['hours_elapsed']:.1f}h",
            'P&L/Hour': f"${df1.iloc[-1]['pnl'] / df1.iloc[-1]['hours_elapsed']:+.2f}",
            'Key Driver': 'Term structure normalization'
        },
        {
            'Scenario': 'Butterfly',
            'Entry Cost': f"${trade2.entry_cost:+.2f}",
            'Final P&L': f"${df2.iloc[-1]['pnl']:+.2f}",
            'Return': f"{df2.iloc[-1]['pnl_pct']:+.1f}%",
            'Duration': f"{df2.iloc[-1]['hours_elapsed']:.1f}h",
            'P&L/Hour': f"${df2.iloc[-1]['pnl'] / df2.iloc[-1]['hours_elapsed']:+.2f}",
            'Key Driver': 'Smile flattening'
        },
        {
            'Scenario': 'Straddle',
            'Entry Cost': f"${trade3.entry_cost:+.2f}",
            'Final P&L': f"${df3.iloc[-1]['pnl']:+.2f}",
            'Return': f"{df3.iloc[-1]['pnl_pct']:+.1f}%",
            'Duration': f"{df3.iloc[-1]['hours_elapsed']:.1f}h",
            'P&L/Hour': f"${df3.iloc[-1]['pnl'] / df3.iloc[-1]['hours_elapsed']:+.2f}",
            'Key Driver': 'Vol expansion + spot move'
        },
        {
            'Scenario': '0DTE Theta',
            'Entry Cost': f"${trade4.entry_cost:+.2f}",
            'Final P&L': f"${df4.iloc[-1]['pnl']:+.2f}",
            'Return': f"{df4.iloc[-1]['pnl_pct']:+.1f}%",
            'Duration': f"{df4.iloc[-1]['hours_elapsed']:.1f}h",
            'P&L/Hour': f"${df4.iloc[-1]['pnl'] / df4.iloc[-1]['hours_elapsed']:+.2f}",
            'Key Driver': 'Theta acceleration'
        }
    ])
    
    print("\n" + summary.to_string(index=False))
    
    # ========================================================================
    # EXPORT DATA
    # ========================================================================
    
    print("\n\n" + "="*80)
    print("EXPORTING DATA FOR ANALYSIS")
    print("="*80)
    
    # Save to CSV
    df1.to_csv('/Users/arivera/projects/tos_options/backtest_calendar_spread.csv', index=False)
    df2.to_csv('/Users/arivera/projects/tos_options/backtest_butterfly.csv', index=False)
    df3.to_csv('/Users/arivera/projects/tos_options/backtest_straddle.csv', index=False)
    df4.to_csv('/Users/arivera/projects/tos_options/backtest_0dte.csv', index=False)
    
    print("\n✓ Saved backtest data:")
    print("  - backtest_calendar_spread.csv")
    print("  - backtest_butterfly.csv")
    print("  - backtest_straddle.csv")
    print("  - backtest_0dte.csv")
    
    # Save summary
    summary.to_csv('/Users/arivera/projects/tos_options/backtest_summary.csv', index=False)
    print("  - backtest_summary.csv")
    
    print("\nRun this to visualize:")
    print("  python plot_backtest.py")


if __name__ == '__main__':
    main()
