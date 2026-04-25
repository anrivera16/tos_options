"""
Spread type dataclasses for Spread Hunter.

All spread candidates are constructed from individual option legs
already stored in the DB by the options scraper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union


@dataclass
class Leg:
    """One option leg in a spread."""

    symbol: str  # underlying symbol
    strike: float
    put_call: str  # "CALL" or "PUT"
    expiration_date: str
    dte: int
    bid: float | None
    ask: float | None
    mark: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    iv: float | None
    volume: int | None
    open_interest: int | None

    def bid_ask_spread_pct(self) -> float:
        """Return bid-ask spread as % of mid. 999.0 if missing."""
        bid = self.bid or 0
        ask = self.ask or 0
        mid = (bid + ask) / 2.0
        if mid <= 0:
            return 999.0
        return ((ask - bid) / mid) * 100.0


@dataclass
class VerticalSpread:
    """
    Two-leg vertical spread (credit or debit).

    Naming convention:
      - short_leg: the option you SELL (higher premium)
      - long_leg: the option you BUY (lower premium)

    For credit spreads: you receive net premium (short > long)
    For debit spreads: you pay net premium (long > short)
    """

    spread_type: str  # "bull_put_credit", "bear_call_credit",
                       # "bull_call_debit", "bear_put_debit"
    underlying: str
    underlying_price: float

    short_leg: Leg
    long_leg: Leg

    strike_width: float  # abs(short_strike - long_strike)
    expiration_date: str
    dte: int

    # Pricing (all per-share, multiply by 100 for per-contract)
    net_premium: float  # positive = credit received, negative = debit paid
    max_profit: float  # best case P&L per share
    max_loss: float  # worst case P&L per share
    breakeven: float  # underlying price at breakeven
    roi_pct: float  # max_profit / abs(max_loss) * 100

    # Net greeks
    net_delta: float | None
    net_theta: float | None
    net_vega: float | None

    # Liquidity (worst leg)
    min_oi: int
    min_volume: int
    max_spread_pct: float  # worst bid-ask spread across legs

    # Scoring
    score: float = 0.0
    tags: list[str] = field(default_factory=list)

    @property
    def is_credit(self) -> bool:
        return self.net_premium > 0

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


@dataclass
class IronCondor:
    """Iron condor: bull put credit + bear call credit, same expiration."""

    spread_type: str = "iron_condor"
    underlying: str = ""
    underlying_price: float = 0.0

    put_short: Leg | None = None  # sold put (higher strike)
    put_long: Leg | None = None  # bought put (lower strike)
    call_short: Leg | None = None  # sold call (lower strike)
    call_long: Leg | None = None  # bought call (higher strike)

    expiration_date: str = ""
    dte: int = 0

    put_width: float = 0.0
    call_width: float = 0.0

    # Pricing (per share)
    put_credit: float = 0.0
    call_credit: float = 0.0
    total_credit: float = 0.0
    max_loss: float = 0.0  # max(width_put, width_call) - total_credit
    breakeven_low: float = 0.0  # put_short_strike - total_credit
    breakeven_high: float = 0.0  # call_short_strike + total_credit
    roi_pct: float = 0.0  # total_credit / max_loss * 100

    # Net greeks
    net_delta: float | None = None
    net_theta: float | None = None
    net_vega: float | None = None

    # Liquidity
    min_oi: int = 0
    min_volume: int = 0

    # Scoring
    score: float = 0.0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


@dataclass
class IronFly:
    """Iron butterfly: sell ATM straddle + buy OTM strangle, same expiration."""

    spread_type: str = "iron_fly"
    underlying: str = ""
    underlying_price: float = 0.0

    put_short: Leg | None = None  # ATM put (sold)
    call_short: Leg | None = None  # ATM call (sold)
    put_long: Leg | None = None  # OTM put (bought)
    call_long: Leg | None = None  # OTM call (bought)

    center_strike: float = 0.0
    put_width: float = 0.0
    call_width: float = 0.0

    expiration_date: str = ""
    dte: int = 0

    # Pricing (per share)
    total_credit: float = 0.0
    max_loss: float = 0.0  # max(width_put, width_call) - total_credit
    breakeven_low: float = 0.0
    breakeven_high: float = 0.0
    roi_pct: float = 0.0

    # Net greeks
    net_delta: float | None = None
    net_theta: float | None = None
    net_vega: float | None = None

    # Liquidity
    min_oi: int = 0
    min_volume: int = 0

    # Scoring
    score: float = 0.0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


@dataclass
class CalendarSpread:
    """Calendar spread: same strike, sell near-term / buy far-term."""

    spread_type: str = "calendar"
    underlying: str = ""
    underlying_price: float = 0.0

    near_leg: Leg | None = None  # sold (short DTE)
    far_leg: Leg | None = None  # bought (long DTE)

    strike: float = 0.0
    near_dte: int = 0
    far_dte: int = 0

    # Pricing (per share)
    debit: float = 0.0  # far premium - near premium
    max_loss: float = 0.0  # = debit paid
    max_profit_est: float = 0.0  # rough estimate

    # Net greeks
    net_delta: float | None = None
    net_theta: float | None = None  # ideally positive (near decays faster)
    net_vega: float | None = None  # ideally positive (long vol)

    # IV term structure
    near_iv: float | None = None
    far_iv: float | None = None
    iv_diff: float | None = None  # near_iv - far_iv (positive = contango, good)

    # Liquidity
    min_oi: int = 0
    min_volume: int = 0

    # Scoring
    score: float = 0.0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


# Type alias for any spread result
AnySpread = Union[VerticalSpread, IronCondor, IronFly, CalendarSpread]

# The 5 spread types we hunt
SPREAD_TYPE_NAMES = {
    "bull_put_credit": "Bull Put Credit",
    "bear_call_credit": "Bear Call Credit",
    "iron_condor": "Iron Condor",
    "iron_fly": "Iron Fly",
    "calendar": "Calendar",
}


@dataclass
class SignalFilter:
    """
    Hard gate filters -- ALL must pass before a trade signal fires.
    Every parameter is tunable. Defaults are conservative starting points.
    """

    # --- Delta filter (real greeks from Schwab) ---
    delta_min: float = 0.10       # short leg abs(delta) must be >= this
    delta_max: float = 0.25       # short leg abs(delta) must be <= this

    # --- IV filter (percentile rank) ---
    iv_rank_min: float = 30.0     # only trade when IV rank >= 30th percentile
    iv_rank_max: float = 95.0     # skip extreme IV (tail risk)
    iv_lookback_days: int = 30    # rolling window for IV rank calc

    # --- Trend filter (SMA) ---
    trend_sma_periods: int = 20        # number of snapshots for SMA
    trend_require_above_sma: bool = True  # for bull puts, price must be above SMA

    # --- Volume / OI filter (per leg) ---
    min_oi: int = 100             # minimum open interest per leg
    min_volume: int = 50          # minimum daily volume per leg

    # --- Support/Resistance (high-OI strikes) ---
    support_oi_threshold: float = 3.0  # strikes with OI > this * avg are "major"
    support_buffer_pct: float = 1.0    # don't sell puts within this % of support

    # --- Spread structure ---
    min_dte: int = 5
    max_dte: int = 9
    min_strike_width: float = 5.0
    max_strike_width: float = 15.0
    min_roi_pct: float = 15.0

    def with_wide_delta(self) -> "SignalFilter":
        """Return a copy with widened delta range for pre-filtering.
        
        The tight delta range (0.10-0.25) is meant for the SHORT leg only.
        During pre-filtering we use a wider band (0.02-0.40) so the LONG
        leg of a spread also survives to be paired.
        """
        from dataclasses import dataclass, fields
        kwargs = {f.name: getattr(self, f.name) for f in fields(self)}
        kwargs["delta_min"] = 0.02
        kwargs["delta_max"] = 0.40
        return SignalFilter(**kwargs)
