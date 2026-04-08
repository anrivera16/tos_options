"""
Volatility Surface Trader - Live Backtesting Example
=====================================================

Simulates trading calendar spreads, butterflies, and 0DTE straddles 
using realistic SPX options data for April 8, 2026.

Runs 4 concurrent trades and tracks P&L over a trading day.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Tuple
from datetime import datetime, timedelta
import json

# ============================================================================
# BLACK-SCHOLES OPTION PRICING
# ============================================================================

from scipy.stats import norm

def d1(S, K, T, r, sigma):
    """Calculate d1 from Black-Scholes"""
    if T <= 0:
        return np.nan
    return (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))

def d2(S, K, T, r, sigma):
    """Calculate d2 from Black-Scholes"""
    if T <= 0:
        return np.nan
    return d1(S, K, T, r, sigma) - sigma * np.sqrt(T)

def call_price(S, K, T, r, sigma):
    """Black-Scholes call price"""
    if T <= 0:
        return max(S - K, 0)
    d1_val = d1(S, K, T, r, sigma)
    d2_val = d2(S, K, T, r, sigma)
    return S * norm.cdf(d1_val) - K * np.exp(-r * T) * norm.cdf(d2_val)

def put_price(S, K, T, r, sigma):
    """Black-Scholes put price"""
    if T <= 0:
        return max(K - S, 0)
    d1_val = d1(S, K, T, r, sigma)
    d2_val = d2(S, K, T, r, sigma)
    return K * np.exp(-r * T) * norm.cdf(-d2_val) - S * norm.cdf(-d1_val)

def delta_call(S, K, T, r, sigma):
    """Call delta"""
    if T <= 0:
        return 1.0 if S > K else 0.0
    return norm.cdf(d1(S, K, T, r, sigma))

def delta_put(S, K, T, r, sigma):
    """Put delta"""
    if T <= 0:
        return -1.0 if S < K else 0.0
    return -norm.cdf(-d1(S, K, T, r, sigma))

def gamma(S, K, T, r, sigma):
    """Gamma (shared for calls and puts)"""
    if T <= 0:
        return 0.0
    return norm.pdf(d1(S, K, T, r, sigma)) / (S * sigma * np.sqrt(T))

def theta_call(S, K, T, r, sigma):
    """Call theta (per day)"""
    if T <= 0:
        return 0.0
    d1_val = d1(S, K, T, r, sigma)
    d2_val = d2(S, K, T, r, sigma)
    return (-S * norm.pdf(d1_val) * sigma / (2 * np.sqrt(T)) 
            - r * K * np.exp(-r * T) * norm.cdf(d2_val)) / 365

def theta_put(S, K, T, r, sigma):
    """Put theta (per day)"""
    if T <= 0:
        return 0.0
    d1_val = d1(S, K, T, r, sigma)
    d2_val = d2(S, K, T, r, sigma)
    return (-S * norm.pdf(d1_val) * sigma / (2 * np.sqrt(T)) 
            + r * K * np.exp(-r * T) * norm.cdf(-d2_val)) / 365

def vega(S, K, T, r, sigma):
    """Vega (per 1% change in sigma)"""
    if T <= 0:
        return 0.0
    return S * norm.pdf(d1(S, K, T, r, sigma)) * np.sqrt(T) / 100

# ============================================================================
# VOLATILITY SURFACE MODEL
# ============================================================================

class VolatilitySurface:
    """
    Generates realistic IV surface with term structure and smile.
    
    Parameterization:
    - Base IV at ATM, 30 DTE
    - Term structure slope (far-term vol vs near-term)
    - Smile curvature (OTM vol vs ATM)
    """
    
    def __init__(self, atm_iv_30dte=0.173, term_slope=0.01, smile_curvature=0.05):
        self.atm_iv_30dte = atm_iv_30dte
        self.term_slope = term_slope  # Vol increases with time to expiry
        self.smile_curvature = smile_curvature  # Vol increases with strike distance
    
    def get_iv(self, S, K, T_years, moneyness_adjustment=1.0):
        """
        Get IV for a given strike, spot, and time to expiration.
        
        Args:
            S: Spot price
            K: Strike price
            T_years: Time to expiration in years
            moneyness_adjustment: Scaling factor for smile (used in scenarios)
        
        Returns:
            Implied volatility (decimal)
        """
        # Term structure: vol increases with time to expiry (normal case)
        # But can be inverted if moneyness_adjustment > 1.0
        T_30dte = 30 / 365
        term_factor = 1.0 + self.term_slope * (T_years - T_30dte) / T_30dte
        
        # Smile: vol increases with distance from ATM
        moneyness = K / S
        smile_factor = 1.0 + self.smile_curvature * ((moneyness - 1.0) ** 2) * moneyness_adjustment
        
        base_iv = self.atm_iv_30dte * term_factor * smile_factor
        return max(base_iv, 0.08)  # Floor at 8% (no negative vol)
    
    def scale_by_scenario(self, factor=1.0):
        """Scale the entire surface (for volatility expansion scenarios)"""
        self.atm_iv_30dte *= factor


# ============================================================================
# OPTIONS CHAIN DATA STRUCTURE
# ============================================================================

@dataclass
class OptionPrice:
    """Single option price snapshot"""
    strike: float
    expiration_days: int
    option_type: str  # 'call' or 'put'
    price: float
    bid: float
    ask: float
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
    volume: int
    open_interest: int


class OptionChain:
    """Full options chain snapshot at a point in time"""
    
    def __init__(self, spot, timestamp, vol_surface, r=0.045):
        self.spot = spot
        self.timestamp = timestamp
        self.vol_surface = vol_surface
        self.r = r
        self.chain = {}  # {(strike, expiration_days, type): OptionPrice}
    
    def generate_chain(self, strikes_range=(5350, 5500, 10), expirations=(7, 30, 60)):
        """
        Generate a realistic options chain.
        
        Args:
            strikes_range: (min, max, step)
            expirations: tuple of days to expiration
        """
        strikes = np.arange(strikes_range[0], strikes_range[1] + strikes_range[2], strikes_range[2])
        
        for exp_days in expirations:
            T = exp_days / 365
            
            for K in strikes:
                iv = self.vol_surface.get_iv(self.spot, K, T)
                
                # Call option
                call_fair = call_price(self.spot, K, T, self.r, iv)
                call_bid = call_fair * 0.995  # Realistic bid-ask
                call_ask = call_fair * 1.005
                
                call_data = OptionPrice(
                    strike=K,
                    expiration_days=exp_days,
                    option_type='call',
                    price=call_fair,
                    bid=call_bid,
                    ask=call_ask,
                    iv=iv,
                    delta=delta_call(self.spot, K, T, self.r, iv),
                    gamma=gamma(self.spot, K, T, self.r, iv),
                    theta=theta_call(self.spot, K, T, self.r, iv),
                    vega=vega(self.spot, K, T, self.r, iv),
                    volume=max(1, int(1000 * np.exp(-abs(K - self.spot) / 100))),  # More volume at-the-money
                    open_interest=max(10, int(5000 * np.exp(-abs(K - self.spot) / 100)))
                )
                self.chain[(K, exp_days, 'call')] = call_data
                
                # Put option
                put_fair = put_price(self.spot, K, T, self.r, iv)
                put_bid = put_fair * 0.995
                put_ask = put_fair * 1.005
                
                put_data = OptionPrice(
                    strike=K,
                    expiration_days=exp_days,
                    option_type='put',
                    price=put_fair,
                    bid=put_bid,
                    ask=put_ask,
                    iv=iv,
                    delta=delta_put(self.spot, K, T, self.r, iv),
                    gamma=gamma(self.spot, K, T, self.r, iv),
                    theta=theta_put(self.spot, K, T, self.r, iv),
                    vega=vega(self.spot, K, T, self.r, iv),
                    volume=max(1, int(1000 * np.exp(-abs(K - self.spot) / 100))),
                    open_interest=max(10, int(5000 * np.exp(-abs(K - self.spot) / 100)))
                )
                self.chain[(K, exp_days, 'put')] = put_data
    
    def get_option(self, strike, exp_days, opt_type):
        """Retrieve a single option from the chain"""
        return self.chain.get((strike, exp_days, opt_type))
    
    def get_atm_straddle_price(self, exp_days):
        """Get price of ATM straddle"""
        K_atm = round(self.spot / 10) * 10  # Round to nearest 10
        call = self.get_option(K_atm, exp_days, 'call')
        put = self.get_option(K_atm, exp_days, 'put')
        return call.bid + put.bid, call.ask + put.ask  # Bid and ask


# ============================================================================
# POSITION AND TRADE TRACKING
# ============================================================================

@dataclass
class TradePosition:
    """Single position (leg) in a trade"""
    name: str
    strike: float
    expiration_days: int
    option_type: str
    quantity: int  # +1 = long, -1 = short
    entry_price: float
    entry_time: datetime


class Trade:
    """Multi-leg trade (calendar spread, butterfly, etc.)"""
    
    def __init__(self, trade_type, description):
        self.trade_type = trade_type  # 'calendar_spread', 'butterfly', 'straddle', '0dte_theta'
        self.description = description
        self.positions: List[TradePosition] = []
        self.entry_time = None
        self.entry_cost = 0.0
        self.pnl_history = []
    
    def add_leg(self, name, strike, exp_days, opt_type, qty, entry_price, timestamp):
        """Add a position leg"""
        leg = TradePosition(
            name=name,
            strike=strike,
            expiration_days=exp_days,
            option_type=opt_type,
            quantity=qty,
            entry_price=entry_price,
            entry_time=timestamp
        )
        self.positions.append(leg)
        
        if self.entry_time is None:
            self.entry_time = timestamp
        
        # Update entry cost (positive = cash outflow, negative = cash inflow)
        self.entry_cost += qty * entry_price
    
    def calculate_pnl(self, chain: OptionChain):
        """Calculate current P&L vs entry"""
        pnl = 0.0
        pnl_detail = {}
        
        for leg in self.positions:
            option = chain.get_option(leg.strike, leg.expiration_days, leg.option_type)
            if option is None:
                continue
            
            # Use mid price for P&L calculation
            current_price = option.price
            leg_pnl = leg.quantity * (leg.entry_price - current_price)  # short = -qty, so sign flips
            pnl += leg_pnl
            
            pnl_detail[leg.name] = {
                'entry_price': leg.entry_price,
                'current_price': current_price,
                'quantity': leg.quantity,
                'leg_pnl': leg_pnl
            }
        
        return pnl, pnl_detail
    
    def get_greeks(self, chain: OptionChain):
        """Aggregate Greeks across all legs"""
        greeks = {'delta': 0, 'gamma': 0, 'theta': 0, 'vega': 0}
        
        for leg in self.positions:
            option = chain.get_option(leg.strike, leg.expiration_days, leg.option_type)
            if option is None:
                continue
            
            greeks['delta'] += leg.quantity * option.delta
            greeks['gamma'] += leg.quantity * option.gamma
            greeks['theta'] += leg.quantity * option.theta
            greeks['vega'] += leg.quantity * option.vega
        
        return greeks


# ============================================================================
# TRADING SCENARIOS AND BACKTESTS
# ============================================================================

def scenario_1_calendar_spread(initial_chain: OptionChain):
    """
    CALENDAR SPREAD ARBITRAGE
    
    Entry: Sell 30 DTE call, buy 60 DTE call at same strike.
    Thesis: Term structure will normalize (30 DTE vol falls relative to 60 DTE vol).
    Duration: 2 days
    """
    
    strike = 5430
    
    # Entry: Sell near-term (30 DTE), buy far-term (60 DTE)
    call_30 = initial_chain.get_option(strike, 30, 'call')
    call_60 = initial_chain.get_option(strike, 60, 'call')
    
    trade = Trade('calendar_spread', 'Calendar Spread: 5430 Call (30 vs 60 DTE)')
    trade.add_leg('Sell 30 DTE Call', strike, 30, 'call', -1, call_30.ask, initial_chain.timestamp)
    trade.add_leg('Buy 60 DTE Call', strike, 60, 'call', +1, call_60.bid, initial_chain.timestamp)
    
    print("\n" + "="*70)
    print("TRADE 1: CALENDAR SPREAD ARBITRAGE")
    print("="*70)
    print(f"Entry time: {initial_chain.timestamp}")
    print(f"Underlying: SPX = {initial_chain.spot}")
    print(f"\nLegs:")
    print(f"  SELL 30 DTE 5430 Call @ {call_30.ask:.2f} IV={call_30.iv:.1%}")
    print(f"  BUY  60 DTE 5430 Call @ {call_60.bid:.2f} IV={call_60.iv:.1%}")
    print(f"\nNet Cost: ${trade.entry_cost:.2f}")
    print(f"Term Structure Skew: {(call_30.iv - call_60.iv)*100:.0f} bps (30 DTE > 60 DTE)")
    print(f"\nGreeks at Entry:")
    greeks = trade.get_greeks(initial_chain)
    print(f"  Delta: {greeks['delta']:.3f}")
    print(f"  Gamma: {greeks['gamma']:.5f}")
    print(f"  Theta:  {greeks['theta']:.4f} per day")
    print(f"  Vega:  {greeks['vega']:.4f}")
    
    return trade


def scenario_2_butterfly(initial_chain: OptionChain):
    """
    BUTTERFLY ARBITRAGE
    
    Entry: Buy 5430 call, sell 2x 5460 call, sell 1x 5490 call.
    Thesis: Smile curvature is too steep; curve will flatten.
    Duration: 1 day
    """
    
    call_5430 = initial_chain.get_option(5430, 30, 'call')
    call_5460 = initial_chain.get_option(5460, 30, 'call')
    call_5490 = initial_chain.get_option(5490, 30, 'call')
    
    trade = Trade('butterfly', 'Butterfly Spread: 5430/5460/5490 (1:2:1)')
    trade.add_leg('Buy 5430 Call', 5430, 30, 'call', +1, call_5430.bid, initial_chain.timestamp)
    trade.add_leg('Sell 5460 Call', 5460, 30, 'call', -2, call_5460.ask, initial_chain.timestamp)
    trade.add_leg('Sell 5490 Call', 5490, 30, 'call', -1, call_5490.ask, initial_chain.timestamp)
    
    print("\n" + "="*70)
    print("TRADE 2: BUTTERFLY ARBITRAGE")
    print("="*70)
    print(f"Entry time: {initial_chain.timestamp}")
    print(f"Underlying: SPX = {initial_chain.spot}")
    print(f"\nLegs (1:2:1 ratio):")
    print(f"  BUY  1x 5430 Call @ {call_5430.bid:.2f} IV={call_5430.iv:.1%}")
    print(f"  SELL 2x 5460 Call @ {call_5460.ask:.2f} IV={call_5460.iv:.1%}")
    print(f"  SELL 1x 5490 Call @ {call_5490.ask:.2f} IV={call_5490.iv:.1%}")
    print(f"\nNet Cost: ${trade.entry_cost:.2f}")
    print(f"Smile Curvature: IV increases {(call_5460.iv - call_5430.iv)*100:.0f} bps per 30 strike")
    print(f"\nGreeks at Entry:")
    greeks = trade.get_greeks(initial_chain)
    print(f"  Delta: {greeks['delta']:.3f}")
    print(f"  Gamma: {greeks['gamma']:.5f}")
    print(f"  Theta:  {greeks['theta']:.4f} per day")
    print(f"  Vega:  {greeks['vega']:.4f}")
    
    return trade


def scenario_3_skew_straddle(initial_chain: OptionChain):
    """
    SKEW-BASED STRADDLE BUY
    
    Entry: Buy ATM straddle (call + put at same strike).
    Thesis: Skew is widening (jump risk signal); vol will expand.
    Duration: 1 day
    """
    
    strike = 5430
    call_atm = initial_chain.get_option(strike, 30, 'call')
    put_atm = initial_chain.get_option(strike, 30, 'put')
    
    trade = Trade('straddle', 'Long Straddle: 5430 (Buy Call + Put)')
    trade.add_leg('Buy 5430 Call', strike, 30, 'call', +1, call_atm.ask, initial_chain.timestamp)
    trade.add_leg('Buy 5430 Put', strike, 30, 'put', +1, put_atm.ask, initial_chain.timestamp)
    
    print("\n" + "="*70)
    print("TRADE 3: SKEW-BASED STRADDLE BUY")
    print("="*70)
    print(f"Entry time: {initial_chain.timestamp}")
    print(f"Underlying: SPX = {initial_chain.spot}")
    print(f"\nLegs:")
    print(f"  BUY 5430 Call @ {call_atm.ask:.2f} (Delta: {call_atm.delta:.3f})")
    print(f"  BUY 5430 Put  @ {put_atm.ask:.2f} (Delta: {put_atm.delta:.3f})")
    print(f"\nStraddle Cost: ${trade.entry_cost:.2f}")
    print(f"Straddle IV: {call_atm.iv:.1%}")
    print(f"\nGreeks at Entry:")
    greeks = trade.get_greeks(initial_chain)
    print(f"  Delta: {greeks['delta']:.3f} (should be ~0)")
    print(f"  Gamma: {greeks['gamma']:.5f}")
    print(f"  Theta:  {greeks['theta']:.4f} per day (negative = works against us)")
    print(f"  Vega:  {greeks['vega']:.4f}")
    
    return trade


def scenario_4_0dte_theta(initial_chain: OptionChain):
    """
    0DTE THETA HARVEST
    
    Entry: Sell ATM 0DTE straddle.
    Thesis: Collect massive theta decay in final hours.
    Duration: 1-2 hours (last hour of trading day)
    """
    
    strike = 5430
    
    # Simulate 0DTE options (very low time value)
    T_0dte = 1 / 365  # 1 day
    iv_0dte = 0.16  # Vol is lower on 0DTE
    
    call_0dte_price = call_price(initial_chain.spot, strike, T_0dte, 0.045, iv_0dte)
    put_0dte_price = put_price(initial_chain.spot, strike, T_0dte, 0.045, iv_0dte)
    
    call_0dte_theta = theta_call(initial_chain.spot, strike, T_0dte, 0.045, iv_0dte)
    put_0dte_theta = theta_put(initial_chain.spot, strike, T_0dte, 0.045, iv_0dte)
    
    trade = Trade('0dte_theta', 'Short 0DTE Straddle: 5430 Theta Harvest')
    trade.add_leg('Sell 0DTE 5430 Call', strike, 0, 'call', -1, call_0dte_price * 1.005, initial_chain.timestamp)
    trade.add_leg('Sell 0DTE 5430 Put', strike, 0, 'put', -1, put_0dte_price * 1.005, initial_chain.timestamp)
    
    print("\n" + "="*70)
    print("TRADE 4: 0DTE THETA HARVEST")
    print("="*70)
    print(f"Entry time: {initial_chain.timestamp}")
    print(f"Underlying: SPX = {initial_chain.spot}")
    print(f"\nLegs (0DTE expires today at 16:00 ET):")
    print(f"  SELL 0DTE 5430 Call @ {call_0dte_price*1.005:.2f}")
    print(f"  SELL 0DTE 5430 Put  @ {put_0dte_price*1.005:.2f}")
    print(f"\nStraddle Credit: ${trade.entry_cost:.2f}")
    print(f"0DTE Theta per hour:")
    print(f"  Call: ${call_0dte_theta * 24:.4f}")
    print(f"  Put:  ${put_0dte_theta * 24:.4f}")
    print(f"  Total: ${(call_0dte_theta + put_0dte_theta) * 24:.4f} / hour")
    print(f"\nGreeks at Entry:")
    greeks = trade.get_greeks(initial_chain)
    print(f"  Delta: {greeks['delta']:.3f}")
    print(f"  Gamma: {greeks['gamma']:.5f} (VERY HIGH - needs hedging)")
    print(f"  Theta:  {greeks['theta']:.4f} per day (extremely positive for short straddle)")
    print(f"  Vega:  {greeks['vega']:.4f}")
    
    return trade


# ============================================================================
# MAIN BACKTEST
# ============================================================================

def run_backtest():
    """
    Run a full day of trading with 4 concurrent positions.
    Simulates market movements and shows P&L evolution.
    """
    
    print("\n" + "="*70)
    print("VOLATILITY SURFACE TRADER - APRIL 8, 2026 BACKTEST")
    print("="*70)
    
    # Base parameters
    spot_initial = 5432.10
    r = 0.045
    
    # Create initial volatility surface (normal market)
    vol_surface = VolatilitySurface(atm_iv_30dte=0.173, term_slope=0.01, smile_curvature=0.05)
    
    # Generate initial chain
    timestamp = datetime(2026, 4, 8, 10, 0, 0)  # 10:00 AM
    chain_initial = OptionChain(spot_initial, timestamp, vol_surface, r)
    chain_initial.generate_chain(
        strikes_range=(5350, 5500, 10),
        expirations=(0, 7, 30, 60)  # 0 DTE is today
    )
    
    print(f"\nInitial Market Conditions:")
    print(f"  Time: {timestamp}")
    print(f"  SPX: {spot_initial:.2f}")
    print(f"  ATM IV (30 DTE): {vol_surface.atm_iv_30dte:.1%}")
    
    # ========================================================================
    # ENTER ALL FOUR TRADES AT 10:00 AM
    # ========================================================================
    
    trades = [
        scenario_1_calendar_spread(chain_initial),
        scenario_2_butterfly(chain_initial),
        scenario_3_skew_straddle(chain_initial),
        scenario_4_0dte_theta(chain_initial)
    ]
    
    # ========================================================================
    # SIMULATE MARKET EVOLUTION
    # ========================================================================
    
    results = {
        'timestamps': [],
        'spot': [],
        'trades_pnl': {i: [] for i in range(4)},
        'trades_greeks': {i: {'delta': [], 'gamma': [], 'theta': [], 'vega': []} for i in range(4)}
    }
    
    # Scenario 1: Calendar Spread
    # Over 2 days, term structure normalizes
    time_points_calendar = [
        (datetime(2026, 4, 8, 10, 0, 0), 5432.10, 'initial'),
        (datetime(2026, 4, 8, 15, 0, 0), 5434.50, '+240 min: spot up, theta helping'),
        (datetime(2026, 4, 9, 10, 0, 0), 5431.00, '+24h: term structure starts normalizing'),
        (datetime(2026, 4, 9, 16, 0, 0), 5430.00, '+30h: term structure fully normalized'),
    ]
    
    # Scenario 2: Butterfly
    # Over 1 day, smile flattens
    time_points_butterfly = [
        (datetime(2026, 4, 8, 10, 0, 0), 5432.10, 'initial'),
        (datetime(2026, 4, 8, 14, 0, 0), 5433.00, '+4h: smile still steep'),
        (datetime(2026, 4, 8, 15, 0, 0), 5431.50, '+5h: smile flattens'),
    ]
    
    # Scenario 3: Straddle
    # Over 1 day, vol expands (skew widens, spot drops)
    time_points_straddle = [
        (datetime(2026, 4, 8, 10, 0, 0), 5432.10, 'initial'),
        (datetime(2026, 4, 8, 12, 0, 0), 5428.00, '+2h: spot drops, vol starting to expand'),
        (datetime(2026, 4, 8, 15, 0, 0), 5415.00, '+5h: major vol expansion'),
    ]
    
    # Scenario 4: 0DTE
    # Over 2 hours (14:00 to 16:00), massive theta decay
    time_points_0dte = [
        (datetime(2026, 4, 8, 14, 0, 0), 5432.10, 'entry: 2 hours to close'),
        (datetime(2026, 4, 8, 15, 0, 0), 5433.00, '+1h: spot up slightly, but theta kills value'),
        (datetime(2026, 4, 8, 15, 45, 0), 5431.50, '+1h45m: 15 min to close'),
    ]
    
    print("\n" + "="*70)
    print("TRADE EVOLUTION AND P&L")
    print("="*70)
    
    # ========================================================================
    # CALENDAR SPREAD P&L EVOLUTION
    # ========================================================================
    
    print("\n--- CALENDAR SPREAD (Trade 1) ---")
    for i, (ts, spot, desc) in enumerate(time_points_calendar):
        
        # Update vol surface
        vol_surface_t = VolatilitySurface(atm_iv_30dte=0.173, term_slope=0.01, smile_curvature=0.05)
        
        # Scenario: First day term structure is inverted, second day normalizes
        if i == 0:
            vol_surface_t.term_slope = 0.01  # Normal: far-term > near-term
        elif i == 1:
            vol_surface_t.term_slope = 0.01  # Still inverted
        elif i >= 2:
            vol_surface_t.term_slope = 0.005  # Normalizing: gap narrows
        
        chain_t = OptionChain(spot, ts, vol_surface_t, r)
        chain_t.generate_chain(strikes_range=(5350, 5500, 10), expirations=(0, 7, 30, 60))
        
        pnl, detail = trades[0].calculate_pnl(chain_t)
        greeks = trades[0].get_greeks(chain_t)
        
        print(f"\n{ts.strftime('%Y-%m-%d %H:%M')} (SPX = {spot:.2f}) - {desc}")
        print(f"  P&L: ${pnl:+.2f}")
        print(f"  Greeks: Δ={greeks['delta']:+.3f}, Γ={greeks['gamma']:+.5f}, Θ={greeks['theta']:+.4f}, ν={greeks['vega']:+.4f}")
    
    # ========================================================================
    # BUTTERFLY P&L EVOLUTION
    # ========================================================================
    
    print("\n--- BUTTERFLY SPREAD (Trade 2) ---")
    for i, (ts, spot, desc) in enumerate(time_points_butterfly):
        
        vol_surface_t = VolatilitySurface(atm_iv_30dte=0.173, term_slope=0.01, smile_curvature=0.05)
        
        # Scenario: Smile flattens (curvature decreases)
        if i == 0:
            vol_surface_t.smile_curvature = 0.05  # Initial smile
        elif i == 1:
            vol_surface_t.smile_curvature = 0.04  # Flattening
        else:
            vol_surface_t.smile_curvature = 0.02  # Much flatter
        
        chain_t = OptionChain(spot, ts, vol_surface_t, r)
        chain_t.generate_chain(strikes_range=(5350, 5500, 10), expirations=(0, 7, 30, 60))
        
        pnl, detail = trades[1].calculate_pnl(chain_t)
        greeks = trades[1].get_greeks(chain_t)
        
        print(f"\n{ts.strftime('%Y-%m-%d %H:%M')} (SPX = {spot:.2f}) - {desc}")
        print(f"  P&L: ${pnl:+.2f}")
        print(f"  Greeks: Δ={greeks['delta']:+.3f}, Γ={greeks['gamma']:+.5f}, Θ={greeks['theta']:+.4f}, ν={greeks['vega']:+.4f}")
    
    # ========================================================================
    # STRADDLE P&L EVOLUTION
    # ========================================================================
    
    print("\n--- LONG STRADDLE (Trade 3) ---")
    for i, (ts, spot, desc) in enumerate(time_points_straddle):
        
        vol_surface_t = VolatilitySurface(atm_iv_30dte=0.173, term_slope=0.01, smile_curvature=0.05)
        
        # Scenario: Vol expands (ATM IV increases)
        if i == 0:
            vol_surface_t.atm_iv_30dte = 0.173  # Initial
        elif i == 1:
            vol_surface_t.atm_iv_30dte = 0.185  # Expansion
        else:
            vol_surface_t.atm_iv_30dte = 0.215  # Major expansion
        
        chain_t = OptionChain(spot, ts, vol_surface_t, r)
        chain_t.generate_chain(strikes_range=(5350, 5500, 10), expirations=(0, 7, 30, 60))
        
        pnl, detail = trades[2].calculate_pnl(chain_t)
        greeks = trades[2].get_greeks(chain_t)
        
        print(f"\n{ts.strftime('%Y-%m-%d %H:%M')} (SPX = {spot:.2f}) - {desc}")
        print(f"  P&L: ${pnl:+.2f}")
        print(f"  Greeks: Δ={greeks['delta']:+.3f}, Γ={greeks['gamma']:+.5f}, Θ={greeks['theta']:+.4f}, ν={greeks['vega']:+.4f}")
    
    # ========================================================================
    # 0DTE P&L EVOLUTION
    # ========================================================================
    
    print("\n--- 0DTE SHORT STRADDLE (Trade 4) ---")
    for i, (ts, spot, desc) in enumerate(time_points_0dte):
        
        vol_surface_t = VolatilitySurface(atm_iv_30dte=0.160, term_slope=0.01, smile_curvature=0.05)
        
        chain_t = OptionChain(spot, ts, vol_surface_t, r)
        chain_t.generate_chain(strikes_range=(5350, 5500, 10), expirations=(0, 7, 30, 60))
        
        pnl, detail = trades[3].calculate_pnl(chain_t)
        greeks = trades[3].get_greeks(chain_t)
        
        print(f"\n{ts.strftime('%Y-%m-%d %H:%M')} (SPX = {spot:.2f}) - {desc}")
        print(f"  P&L: ${pnl:+.2f}")
        print(f"  Greeks: Δ={greeks['delta']:+.3f}, Γ={greeks['gamma']:+.5f}, Θ={greeks['theta']:+.4f}, ν={greeks['vega']:+.4f}")
    
    # ========================================================================
    # SUMMARY
    # ========================================================================
    
    print("\n" + "="*70)
    print("END OF DAY SUMMARY (April 8, 2026, 16:00 ET)")
    print("="*70)
    
    # Final chain
    vol_surface_final = VolatilitySurface(atm_iv_30dte=0.173, term_slope=0.005, smile_curvature=0.03)
    chain_final = OptionChain(5431.50, datetime(2026, 4, 8, 16, 0, 0), vol_surface_final, r)
    chain_final.generate_chain(strikes_range=(5350, 5500, 10), expirations=(0, 7, 30, 60))
    
    print(f"\nFinal Spot: 5431.50")
    
    for i, trade in enumerate(trades, 1):
        pnl, _ = trade.calculate_pnl(chain_final)
        greeks = trade.get_greeks(chain_final)
        
        print(f"\nTrade {i}: {trade.description}")
        print(f"  Entry Cost: ${trade.entry_cost:+.2f}")
        print(f"  Final P&L: ${pnl:+.2f}")
        print(f"  Return: {(pnl / abs(trade.entry_cost) * 100):+.1f}%")
        print(f"  Final Greeks: Δ={greeks['delta']:+.3f}, Θ={greeks['theta']:+.4f}/day")


if __name__ == '__main__':
    run_backtest()
