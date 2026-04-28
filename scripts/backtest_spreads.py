"""
Backtest SPY credit spreads using Polygon flat file data.

Supports bull put AND bear call credit spreads with:
  - Stop-loss: close if spread cost exceeds X% of max loss
  - Profit target: close if spread value drops to Y% of credit
  - Hold-to-expiry: original mode, resolve at expiry
  - OCC symbols for TOS manual entry
  - CSV export for trade verification

Usage:
    python3 scripts/backtest_spreads.py                          # default: $5w, 1.5% OTM, 7 DTE
    python3 scripts/backtest_spreads.py --otm 1.0                # closer to money
    python3 scripts/backtest_spreads.py --otm 2.5                # further OTM
    python3 scripts/backtest_spreads.py --stop-loss 50           # stop out at 50% of max loss
    python3 scripts/backtest_spreads.py --profit-target 50       # take profit at 50% of credit
    python3 scripts/backtest_spreads.py --bear-call              # bear call spreads instead
    python3 scripts/backtest_spreads.py --both                   # run both sides
    python3 scripts/backtest_spreads.py --compare                # run multiple OTM configs
    python3 scripts/backtest_spreads.py --months 6               # longer period
    python3 scripts/backtest_spreads.py --csv trades.csv         # export to CSV
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

PARQUET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "options-backtest", "parquet",
)


@dataclass
class Trade:
    entry_date: date
    exit_date: date          # actual exit (may be before expiry with stop/target)
    expiry_date: date        # original expiry
    spread_type: str         # "bull_put" or "bear_call"
    sell_strike: float
    buy_strike: float
    width: float
    dte_entry: int
    credit: float
    max_loss: float
    roc_pct: float
    otm_pct: float
    atm_at_entry: float
    sell_entry: float
    buy_entry: float
    sell_exit: float = 0.0
    buy_exit: float = 0.0
    pnl: float = 0.0
    result: str = ""         # win / partial / loss / stopped / target
    exit_reason: str = ""    # "expiry" / "stop_loss" / "profit_target"
    exit_day_dte: int = 0    # DTE when we actually exited
    max_adverse: float = 0.0 # worst intraday spread cost during hold
    max_favorable: float = 0.0  # best intraday spread credit during hold
    occ_sell: str = ""
    occ_buy: str = ""


def build_occ(symbol: str, expiry: date, option_type: str, strike: float) -> str:
    """Build OCC option symbol: SPY   251208P00670000"""
    # OCC format: 6 char symbol padded + YYMMDD + C/P + 8 digit strike * 1000
    sym = symbol.ljust(6)
    exp_str = expiry.strftime("%y%m%d")
    cp = "C" if option_type == "call" else "P"
    strike_str = f"{int(strike * 1000):08d}"
    return f"{sym}{exp_str}{cp}{strike_str}"


def estimate_atm(options: pd.DataFrame, opt_type: str) -> float | None:
    """Estimate ATM from DTE-matched options. Find the $1.50-$4.00 transition."""
    if options.empty:
        return None
    for _, r in options.sort_values("strike", ascending=(opt_type == "C")).iterrows():
        if 1.50 < r["close"] < 4.00:
            return float(r["strike"])
    # Fallback: highest-volume
    vol = options[options["volume"] > 0]
    if not vol.empty:
        return float(vol.loc[vol["volume"].idxmax(), "strike"])
    return float(options["strike"].median())


def pick_spread(
    options: pd.DataFrame,
    atm: float,
    width: float,
    otm_pct: float,
    opt_type: str,  # "P" for bull put, "C" for bear call
    min_credit: float = 0.05,
) -> Trade | None:
    """Pick the best credit spread at target OTM distance."""
    if opt_type == "P":
        # Bull put: sell strike below ATM, buy strike further below
        target_sell = atm * (1 - otm_pct / 100.0)
        target_buy = target_sell - width
    else:
        # Bear call: sell strike above ATM, buy strike further above
        target_sell = atm * (1 + otm_pct / 100.0)
        target_buy = target_sell + width

    strikes = sorted(options["strike"].unique())

    # Find closest sell strike
    sell_k = min(strikes, key=lambda s: abs(s - target_sell))

    if opt_type == "P":
        buy_k = sell_k - width
    else:
        buy_k = sell_k + width

    # Verify both strikes exist, scan for nearest valid pair if not
    if buy_k not in strikes:
        best = None
        best_dist = 999
        for s in strikes:
            b = s - width if opt_type == "P" else s + width
            if b in strikes:
                dist = abs(s - target_sell)
                if dist < best_dist:
                    best_dist = dist
                    best = (s, b)
        if best is None:
            return None
        sell_k, buy_k = best

    sell_row = options[options["strike"] == sell_k].iloc[0]
    buy_row = options[options["strike"] == buy_k].iloc[0]

    sell_px = float(sell_row["close"])
    buy_px = float(buy_row["close"])

    # Credit = premium received from sell - premium paid for buy
    if opt_type == "P":
        credit = sell_px - buy_px  # both are positive, sell > buy for OTM
    else:
        credit = sell_px - buy_px  # sell call premium > buy call for OTM

    if credit < min_credit:
        return None

    if opt_type == "P":
        actual_otm = (atm - sell_k) / atm * 100.0
    else:
        actual_otm = (sell_k - atm) / atm * 100.0

    risk = width - credit
    roc = credit / risk * 100.0 if risk > 0 else 0

    entry = sell_row["date"]
    expiry = sell_row["expiry"]
    if isinstance(entry, pd.Timestamp):
        entry = entry.date() if hasattr(entry, 'date') else entry
    if isinstance(expiry, pd.Timestamp):
        expiry = expiry.date() if hasattr(expiry, 'date') else expiry

    spread_type = "bull_put" if opt_type == "P" else "bear_call"
    opt_name = "put" if opt_type == "P" else "call"

    occ_sell = build_occ("SPY", expiry, opt_name, sell_k)
    occ_buy = build_occ("SPY", expiry, opt_name, buy_k)

    return Trade(
        entry_date=entry,
        exit_date=expiry,
        expiry_date=expiry,
        spread_type=spread_type,
        sell_strike=sell_k,
        buy_strike=buy_k,
        width=width,
        dte_entry=0,  # filled by caller
        credit=round(credit, 2),
        max_loss=round(risk, 2),
        roc_pct=round(roc, 1),
        otm_pct=round(actual_otm, 1),
        atm_at_entry=round(atm, 1),
        sell_entry=round(sell_px, 2),
        buy_entry=round(buy_px, 2),
        occ_sell=occ_sell,
        occ_buy=occ_buy,
    )


def track_daily(
    trade: Trade,
    df: pd.DataFrame,
    stop_loss_pct: float | None = None,
    profit_target_pct: float | None = None,
) -> Trade:
    """
    Track a trade day by day looking for stop-loss or profit-target exits.
    Also records max adverse/favorable excursion.
    """
    opt_type = "P" if trade.spread_type == "bull_put" else "C"
    expiry = trade.expiry_date

    # Get all days for this contract pair
    trading_days = sorted(df["date"].unique())

    for day in trading_days:
        if day < trade.entry_date or day > expiry:
            continue

        day_pool = df[df["date"] == day]
        sell_rows = day_pool[
            (day_pool["strike"] == trade.sell_strike) &
            (day_pool["option_type"] == opt_type) &
            (day_pool["expiry"] == expiry)
        ]
        buy_rows = day_pool[
            (day_pool["strike"] == trade.buy_strike) &
            (day_pool["option_type"] == opt_type) &
            (day_pool["expiry"] == expiry)
        ]

        if sell_rows.empty or buy_rows.empty:
            continue

        sell_px = float(sell_rows.iloc[0]["close"])
        buy_px = float(buy_rows.iloc[0]["close"])
        current_spread = sell_px - buy_px  # cost to close
        dte_row = int(sell_rows.iloc[0]["dte"])

        # P&L if we closed here
        unrealized = trade.credit - current_spread

        # Track excursions (in spread-cost terms)
        # Adverse = spread widened (cost us more to close)
        trade.max_adverse = max(trade.max_adverse, current_spread)
        # Favorable = spread narrowed (cheap to close = profit)
        trade.max_favorable = max(trade.max_favorable, unrealized)

        # Skip entry day for exit decisions
        if day == trade.entry_date:
            continue

        # Check stop-loss: close if current loss exceeds X% of max loss
        if stop_loss_pct is not None and unrealized < 0:
            stop_line = -(trade.max_loss * stop_loss_pct / 100.0)
            if unrealized <= stop_line:
                trade.sell_exit = sell_px
                trade.buy_exit = buy_px
                trade.pnl = round(unrealized, 2)
                trade.exit_date = day
                trade.exit_day_dte = dte_row
                trade.exit_reason = "stop_loss"
                trade.result = "stopped"
                return trade

        # Check profit target: close if we've captured X% of credit
        if profit_target_pct is not None:
            target_line = trade.credit * profit_target_pct / 100.0
            if unrealized >= target_line:
                trade.sell_exit = sell_px
                trade.buy_exit = buy_px
                trade.pnl = round(unrealized, 2)
                trade.exit_date = day
                trade.exit_day_dte = dte_row
                trade.exit_reason = "profit_target"
                trade.result = "target"
                return trade

    return trade


def resolve_at_expiry(trade: Trade, df: pd.DataFrame) -> Trade:
    """Resolve a trade at its expiry date."""
    opt_type = "P" if trade.spread_type == "bull_put" else "C"
    pool = df[(df["date"] == trade.expiry_date) & (df["dte"] == 0)]

    sell = pool[(pool["strike"] == trade.sell_strike) & (pool["option_type"] == opt_type)]
    buy = pool[(pool["strike"] == trade.buy_strike) & (pool["option_type"] == opt_type)]

    if len(sell) > 0 and len(buy) > 0:
        trade.sell_exit = float(sell.iloc[0]["close"])
        trade.buy_exit = float(buy.iloc[0]["close"])
        spread_at_expiry = trade.sell_exit - trade.buy_exit
        trade.pnl = round(trade.credit - spread_at_expiry, 2)
    else:
        # Infer from nearby strikes
        if opt_type == "P":
            deeper = pool[(pool["strike"] >= trade.sell_strike) & (pool["strike"] <= trade.sell_strike + 5)]
        else:
            deeper = pool[(pool["strike"] <= trade.sell_strike) & (pool["strike"] >= trade.sell_strike - 5)]
        if not deeper.empty and deeper["close"].max() > 0.50:
            trade.pnl = -trade.max_loss
            trade.sell_exit = trade.width
            trade.buy_exit = 0
        else:
            trade.pnl = trade.credit
            trade.sell_exit = 0
            trade.buy_exit = 0

    trade.exit_date = trade.expiry_date
    trade.exit_reason = "expiry"
    trade.exit_day_dte = 0

    if trade.pnl >= trade.credit * 0.5:
        trade.result = "win"
    elif trade.pnl > 0:
        trade.result = "partial"
    else:
        trade.result = "loss"

    return trade


def run_backtest(
    months: int = 3,
    width: float = 5.0,
    otm_pct: float = 1.5,
    dte: int = 7,
    min_credit: float = 0.05,
    allow_overlap: bool = False,
    stop_loss_pct: float | None = None,
    profit_target_pct: float | None = None,
    spread_types: list[str] | None = None,  # ["bull_put"], ["bear_call"], or both
) -> list[Trade]:
    if spread_types is None:
        spread_types = ["bull_put"]

    files = sorted(glob.glob(os.path.join(PARQUET_DIR, "SPY_*.parquet")))
    if not files:
        print("No SPY parquet files found in", PARQUET_DIR)
        return []
    dfs = [pd.read_parquet(f) for f in files[-months:]]
    df = pd.concat(dfs, ignore_index=True)

    trading_days = sorted(df["date"].unique())
    open_expiry: set = set()
    trades: list[Trade] = []

    for day in trading_days:
        # Expire passed positions
        open_expiry = {e for e in open_expiry if e > day}

        day_df = df[df["date"] == day]

        for stype in spread_types:
            opt_type = "P" if stype == "bull_put" else "C"
            pool = day_df[(day_df["option_type"] == opt_type) & (day_df["dte"] == dte)]
            if pool.empty:
                continue

            atm = estimate_atm(pool, opt_type)
            if atm is None:
                continue

            t = pick_spread(pool, atm, width, otm_pct, opt_type, min_credit)
            if t is None:
                continue

            t.dte_entry = dte

            # Check overlap
            if not allow_overlap and open_expiry:
                continue

            open_expiry.add(t.expiry_date)

            # Track day by day for stops/targets
            if stop_loss_pct is not None or profit_target_pct is not None:
                t = track_daily(t, df, stop_loss_pct, profit_target_pct)

            # If not stopped/targeted, resolve at expiry
            if t.exit_reason == "":
                # Find expiry data in df
                expiry_df = df[df["date"] == t.expiry_date]
                if expiry_df.empty:
                    later = [d for d in trading_days if d > t.expiry_date]
                    if later:
                        expiry_df = df[df["date"] == later[0]]
                if not expiry_df.empty:
                    t = resolve_at_expiry(t, expiry_df)
                else:
                    # No data for expiry -- assume win (expired worthless)
                    t.pnl = t.credit
                    t.result = "win"
                    t.exit_reason = "expiry"
                    t.exit_day_dte = 0

            trades.append(t)

    return trades


def fmt_report(trades: list[Trade], label: str = "") -> str:
    if not trades:
        return "  No trades."

    L: list[str] = []
    sep = "=" * 78
    dash = "-" * 78

    L.append("")
    L.append(f"  {sep}")
    tag = f"  {label}" if label else ""
    L.append(f"{tag}  CREDIT SPREAD BACKTEST")
    first, last = trades[0], trades[-1]
    L.append(f"  {first.entry_date} -> {last.entry_date}  |  {len(trades)} trades")
    L.append(f"  ${first.width:.0f}w  DTE {first.dte_entry}  ~{first.otm_pct:.1f}% OTM")

    # Show exit mode
    stop_trades = [t for t in trades if t.exit_reason == "stop_loss"]
    target_trades = [t for t in trades if t.exit_reason == "profit_target"]
    expiry_trades = [t for t in trades if t.exit_reason == "expiry"]
    exit_mode_parts = [f"{len(expiry_trades)} hold"]
    if stop_trades:
        exit_mode_parts.append(f"{len(stop_trades)} stopped")
    if target_trades:
        exit_mode_parts.append(f"{len(target_trades)} targeted")
    L.append(f"  Exit: {', '.join(exit_mode_parts)}")
    L.append(f"  {sep}")

    # Overall stats
    wins = [t for t in trades if t.result in ("win", "partial", "target")]
    losses = [t for t in trades if t.result in ("loss", "stopped")]
    pnl = sum(t.pnl for t in trades)
    avg_cr = sum(t.credit for t in trades) / len(trades)
    avg_roc = sum(t.roc_pct for t in trades) / len(trades)
    wr = len(wins) / len(trades) * 100

    gw = sum(t.pnl for t in trades if t.pnl > 0)
    gl = abs(sum(t.pnl for t in trades if t.pnl < 0))
    pf = gw / gl if gl else float("inf")

    L.append(f"")
    L.append(f"  OVERALL")
    L.append(f"  {dash}")
    L.append(f"  Win rate   {wr:>5.0f}%  ({len(wins)}W {len(losses)}L)")
    L.append(f"  Total P&L  ${pnl:>8,.2f}")
    L.append(f"  Avg credit ${avg_cr:>6.2f}   Avg ROC {avg_roc:>5.0f}%")
    L.append(f"  Profit fac {pf:>5.2f}   (wins ${gw:,.2f} / losses ${gl:,.2f})")

    # Exit breakdown
    if stop_trades or target_trades:
        L.append(f"")
        L.append(f"  EXIT BREAKDOWN")
        L.append(f"  {dash}")
        if expiry_trades:
            ew = [t for t in expiry_trades if t.pnl >= 0]
            el = [t for t in expiry_trades if t.pnl < 0]
            epnl = sum(t.pnl for t in expiry_trades)
            L.append(f"  Hold-to-expiry  {len(expiry_trades):>3}  ({len(ew)}W {len(el)}L)  P&L ${epnl:>8,.2f}")
        if stop_trades:
            sw = [t for t in stop_trades if t.pnl >= 0]
            sl = [t for t in stop_trades if t.pnl < 0]
            spnl = sum(t.pnl for t in stop_trades)
            avg_stop_dte = sum(t.exit_day_dte for t in stop_trades) / len(stop_trades) if stop_trades else 0
            L.append(f"  Stopped out     {len(stop_trades):>3}  ({len(sw)}W {len(sl)}L)  P&L ${spnl:>8,.2f}  avg exit DTE {avg_stop_dte:.1f}")
        if target_trades:
            tpnl = sum(t.pnl for t in target_trades)
            avg_tgt_dte = sum(t.exit_day_dte for t in target_trades) / len(target_trades) if target_trades else 0
            L.append(f"  Profit target   {len(target_trades):>3}              P&L ${tpnl:>8,.2f}  avg exit DTE {avg_tgt_dte:.1f}")

    # Monthly
    by_month: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        by_month[str(t.entry_date)[:7]].append(t)

    L.append(f"")
    L.append(f"  MONTHLY")
    L.append(f"  {dash}")
    L.append(f"  {'Month':<9} {'#':>3} {'W':>3} {'L':>3} {'Win%':>6} {'P&L':>9} {'AvgCr':>6} {'PF':>6}")
    L.append(f"  {dash}")

    for m in sorted(by_month):
        mt = by_month[m]
        mw = [t for t in mt if t.result in ("win", "partial", "target")]
        ml = [t for t in mt if t.result in ("loss", "stopped")]
        mpnl = sum(t.pnl for t in mt)
        mcr = sum(t.credit for t in mt) / len(mt)
        mwr = len(mw) / len(mt) * 100
        mgw = sum(t.pnl for t in mt if t.pnl > 0)
        mgl = abs(sum(t.pnl for t in mt if t.pnl < 0))
        mpf = f"{mgw/mgl:.1f}" if mgl else "INF"
        L.append(f"  {m:<9} {len(mt):>3} {len(mw):>3} {len(ml):>3} {mwr:>5.0f}% ${mpnl:>8,.2f} ${mcr:>5.2f} {mpf:>6}")

    L.append(f"  {dash}")

    # All trades
    L.append(f"")
    L.append(f"  ALL TRADES")
    L.append(f"  {dash}")
    L.append(f"  {'Entry':<12}{'Exit':<12}{'Type':<5}{'ATM':>6}{'Sell':>6}{'Buy':>6}{'Cr':>6}{'P&L':>7}{'ROC':>5}{'OTM':>6}{'ExDTE':>5}{'Reason':<9}{'R':>2}")
    L.append(f"  {dash}")

    for t in trades:
        tag = "W" if t.result in ("win", "partial", "target") else "L"
        tp = "BP" if t.spread_type == "bull_put" else "BC"
        reason = t.exit_reason[:8] if t.exit_reason else "?"
        L.append(
            f"  {str(t.entry_date):<12}{str(t.exit_date):<12}"
            f"{tp:<5}{t.atm_at_entry:>6.0f}{t.sell_strike:>6.0f}{t.buy_strike:>6.0f}"
            f"${t.credit:>5.2f}${t.pnl:>6.2f}{t.roc_pct:>4.0f}%"
            f"{t.otm_pct:>5.1f}%{t.exit_day_dte:>5}{reason:<9}{tag:>2}"
        )

    L.append(f"  {dash}")

    # Worst losses
    worst = sorted(trades, key=lambda t: t.pnl)[:5]
    if any(t.pnl < 0 for t in worst):
        L.append(f"")
        L.append(f"  WORST TRADES")
        L.append(f"  {dash}")
        for t in worst:
            if t.pnl < 0:
                tp = "BP" if t.spread_type == "bull_put" else "BC"
                L.append(
                    f"  {t.entry_date}  {tp} {t.sell_strike:.0f}/{t.buy_strike:.0f}  "
                    f"cr=${t.credit:.2f}  P&L=${t.pnl:.2f}  exit={t.exit_reason} DTE={t.exit_day_dte}"
                )

    # Drawdown
    cumul, peak, max_dd = 0.0, 0.0, 0.0
    for t in trades:
        cumul += t.pnl
        peak = max(peak, cumul)
        max_dd = max(max_dd, peak - cumul)

    # Avg hold days
    avg_hold = 0
    if trades:
        holds = []
        for t in trades:
            if isinstance(t.entry_date, date) and isinstance(t.exit_date, date):
                holds.append((t.exit_date - t.entry_date).days)
            avg_hold = sum(holds) / len(holds) if holds else dte_default(trades)

    L.append(f"")
    L.append(f"  Max drawdown:   ${max_dd:.2f}")
    L.append(f"  Cumulative P&L: ${cumul:.2f}")
    L.append(f"  Avg hold:       {avg_hold:.1f} days")
    L.append(f"  {sep}")
    L.append("")

    return "\n".join(L)


def dte_default(trades: list[Trade]) -> float:
    if trades:
        return float(trades[0].dte_entry)
    return 7.0


def export_csv(trades: list[Trade], path: str) -> None:
    """Export trades to CSV for manual TOS verification."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "entry_date", "exit_date", "expiry_date", "spread_type",
            "sell_strike", "buy_strike", "width",
            "credit", "max_loss", "roc_pct", "otm_pct", "atm_at_entry",
            "sell_entry_px", "buy_entry_px", "sell_exit_px", "buy_exit_px",
            "pnl", "result", "exit_reason", "exit_dte",
            "max_adverse", "max_favorable",
            "occ_sell", "occ_buy",
        ])
        for t in trades:
            w.writerow([
                t.entry_date, t.exit_date, t.expiry_date, t.spread_type,
                t.sell_strike, t.buy_strike, t.width,
                t.credit, t.max_loss, t.roc_pct, t.otm_pct, t.atm_at_entry,
                t.sell_entry, t.buy_entry, t.sell_exit, t.buy_exit,
                t.pnl, t.result, t.exit_reason, t.exit_day_dte,
                round(t.max_adverse, 2), round(t.max_favorable, 2),
                t.occ_sell, t.occ_buy,
            ])
    print(f"  Exported {len(trades)} trades to {path}")


def main():
    p = argparse.ArgumentParser(
        description="Backtest SPY credit spreads with stop-loss and profit targets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--months", type=int, default=6)
    p.add_argument("--width", type=float, default=5.0, help="Strike width ($)")
    p.add_argument("--otm", type=float, default=1.5, help="Target %% OTM from ATM")
    p.add_argument("--dte", type=int, default=7, help="Days to expiry at entry")
    p.add_argument("--min-credit", type=float, default=0.05, help="Min credit ($)")
    p.add_argument("--overlap", action="store_true", help="Allow overlapping positions")
    p.add_argument("--stop-loss", type=float, default=None,
                   help="Stop out when loss reaches X%% of max loss (e.g. 50 = stop at half max loss)")
    p.add_argument("--profit-target", type=float, default=None,
                   help="Take profit when P&L reaches X%% of credit (e.g. 50 = take at 50%% of credit)")
    p.add_argument("--bear-call", action="store_true", help="Bear call spreads instead of bull puts")
    p.add_argument("--both", action="store_true", help="Run both bull puts and bear calls")
    p.add_argument("--compare", action="store_true", help="Run multiple OTM configs side-by-side")
    p.add_argument("--compare-exits", action="store_true",
                   help="Compare hold-to-expiry vs stop/target exits")
    p.add_argument("--csv", type=str, default=None, help="Export trades to CSV file")

    args = p.parse_args()

    # Determine spread types
    if args.both:
        spread_types = ["bull_put", "bear_call"]
    elif args.bear_call:
        spread_types = ["bear_call"]
    else:
        spread_types = ["bull_put"]

    if args.compare_exits:
        # Compare hold vs stop/target at different levels
        configs = [
            ("Hold to expiry", dict(stop_loss_pct=None, profit_target_pct=None)),
            ("Stop 75% loss",  dict(stop_loss_pct=75, profit_target_pct=None)),
            ("Stop 50% loss",  dict(stop_loss_pct=50, profit_target_pct=None)),
            ("Target 75% cr",  dict(stop_loss_pct=None, profit_target_pct=75)),
            ("Target 50% cr",  dict(stop_loss_pct=None, profit_target_pct=50)),
            ("Stop50 + Tgt75", dict(stop_loss_pct=50, profit_target_pct=75)),
        ]
        for label, kw in configs:
            trades = run_backtest(
                months=args.months, width=args.width, otm_pct=args.otm,
                dte=args.dte, min_credit=args.min_credit,
                allow_overlap=args.overlap, spread_types=spread_types,
                **kw,
            )
            print(fmt_report(trades, label=f"[{label}] "))
            if args.csv:
                base, ext = os.path.splitext(args.csv)
                csv_path = f"{base}_{label.replace(' ', '_').replace('+', 'plus')}{ext}"
                export_csv(trades, csv_path)
    elif args.compare:
        configs = [
            ("Conservative 1% OTM", dict(otm_pct=1.0)),
            ("Standard 1.5% OTM",   dict(otm_pct=1.5)),
            ("Wide 2.5% OTM",       dict(otm_pct=2.5)),
            ("Far 3.5% OTM",        dict(otm_pct=3.5)),
        ]
        for label, kw in configs:
            trades = run_backtest(
                months=args.months, width=args.width, dte=args.dte,
                min_credit=args.min_credit, allow_overlap=args.overlap,
                stop_loss_pct=args.stop_loss, profit_target_pct=args.profit_target,
                spread_types=spread_types, **kw,
            )
            print(fmt_report(trades, label=f"[{label}] "))
            if args.csv:
                base, ext = os.path.splitext(args.csv)
                csv_path = f"{base}_{label.replace(' ', '_')}{ext}"
                export_csv(trades, csv_path)
    else:
        trades = run_backtest(
            months=args.months, width=args.width, otm_pct=args.otm,
            dte=args.dte, min_credit=args.min_credit,
            allow_overlap=args.overlap, spread_types=spread_types,
            stop_loss_pct=args.stop_loss, profit_target_pct=args.profit_target,
        )
        print(fmt_report(trades))
        if args.csv:
            export_csv(trades, args.csv)


if __name__ == "__main__":
    main()
