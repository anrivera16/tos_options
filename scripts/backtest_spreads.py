"""
Backtest SPY bull put credit spreads using Polygon flat file data.

Strategy: Sell $5-wide bull put spreads, hold to expiry.
Each trading day, enter ONE spread at the target OTM distance.
No overlapping positions (one at a time).

Usage:
    python3 scripts/backtest_spreads.py                      # default: 5w, 1.5% OTM, 7 DTE
    python3 scripts/backtest_spreads.py --otm 1.0             # closer to money
    python3 scripts/backtest_spreads.py --otm 2.5             # further OTM
    python3 scripts/backtest_spreads.py --width 10            # $10 wide
    python3 scripts/backtest_spreads.py --dte 14              # 14 DTE
    python3 scripts/backtest_spreads.py --compare             # run multiple configs
    python3 scripts/backtest_spreads.py --months 6            # longer period
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import pandas as pd

PARQUET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "options-backtest", "parquet",
)


@dataclass
class Trade:
    entry_date: date
    exit_date: date
    sell_strike: float
    buy_strike: float
    width: float
    dte: int
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
    result: str = ""  # win / partial / loss


def estimate_atm(puts: pd.DataFrame) -> float | None:
    """Estimate ATM from DTE-matched puts. Find the $1.50-$4.00 transition."""
    if puts.empty:
        return None
    for _, r in puts.sort_values("strike", ascending=False).iterrows():
        if 1.50 < r["close"] < 4.00:
            return float(r["strike"])
    # Fallback: highest-volume put
    vol = puts[puts["volume"] > 0]
    if not vol.empty:
        return float(vol.loc[vol["volume"].idxmax(), "strike"])
    return float(puts["strike"].median())


def pick_spread(
    puts: pd.DataFrame,
    atm: float,
    width: float,
    otm_pct: float,
    dte: int,
    min_credit: float = 0.05,
) -> Trade | None:
    """Pick the best bull put spread at target OTM distance."""
    target_sell = atm * (1 - otm_pct / 100.0)
    target_buy = target_sell - width

    strikes = sorted(puts["strike"].unique())

    # Find closest sell strike
    sell_k = min(strikes, key=lambda s: abs(s - target_sell))
    buy_k = sell_k - width

    # Verify both strikes exist
    if buy_k not in strikes:
        # Scan for any valid $width-apart pair near target
        best = None
        best_dist = 999
        for s in strikes:
            b = s - width
            if b in strikes:
                dist = abs(s - target_sell)
                if dist < best_dist:
                    best_dist = dist
                    best = (s, b)
        if best is None:
            return None
        sell_k, buy_k = best

    sell_row = puts[puts["strike"] == sell_k].iloc[0]
    buy_row = puts[puts["strike"] == buy_k].iloc[0]

    sell_px = float(sell_row["close"])
    buy_px = float(buy_row["close"])
    credit = sell_px - buy_px

    if credit < min_credit:
        return None

    actual_otm = (atm - sell_k) / atm * 100.0
    risk = width - credit
    roc = credit / risk * 100.0 if risk > 0 else 0

    entry = sell_row["date"]
    expiry = sell_row["expiry"]
    if isinstance(entry, pd.Timestamp):
        entry = entry.date()
    if isinstance(expiry, pd.Timestamp):
        expiry = expiry.date()

    return Trade(
        entry_date=entry,
        exit_date=expiry,
        sell_strike=sell_k,
        buy_strike=buy_k,
        width=width,
        dte=dte,
        credit=round(credit, 2),
        max_loss=round(risk, 2),
        roc_pct=round(roc, 1),
        otm_pct=round(actual_otm, 1),
        atm_at_entry=round(atm, 1),
        sell_entry=round(sell_px, 2),
        buy_entry=round(buy_px, 2),
    )


def resolve(trade: Trade, expiry_day: pd.DataFrame) -> Trade:
    """Resolve a trade on its expiry date."""
    pool = expiry_day[expiry_day["dte"] == 0]
    puts = pool[pool["option_type"] == "P"]

    sell = puts[puts["strike"] == trade.sell_strike]
    buy = puts[puts["strike"] == trade.buy_strike]

    if len(sell) > 0 and len(buy) > 0:
        trade.sell_exit = float(sell.iloc[0]["close"])
        trade.buy_exit = float(buy.iloc[0]["close"])
        spread_at_expiry = trade.sell_exit - trade.buy_exit
        trade.pnl = round(trade.credit - spread_at_expiry, 2)
    else:
        # Infer from nearby strikes
        # If we can't find the exact contract, check if SPY closed above sell strike
        # by looking at whether any ITM put near sell strike has value
        deeper = puts[(puts["strike"] >= trade.sell_strike) & (puts["strike"] <= trade.sell_strike + 5)]
        if not deeper.empty and deeper["close"].max() > 0.50:
            # SPY likely closed below sell strike -> loss
            trade.pnl = -trade.max_loss
            trade.sell_exit = trade.width
            trade.buy_exit = 0
        else:
            # Probably expired worthless
            trade.pnl = trade.credit
            trade.sell_exit = 0
            trade.buy_exit = 0

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
) -> list[Trade]:
    files = sorted(glob.glob(os.path.join(PARQUET_DIR, "SPY_*.parquet")))
    if not files:
        print("No SPY parquet files found.")
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
        puts = day_df[(day_df["option_type"] == "P") & (day_df["dte"] == dte)]
        if puts.empty:
            continue

        atm = estimate_atm(puts)
        if atm is None:
            continue

        t = pick_spread(puts, atm, width, otm_pct, dte, min_credit)
        if t is None:
            continue

        # Check overlap
        if not allow_overlap and open_expiry:
            continue

        open_expiry.add(t.exit_date)

        # Resolve at expiry
        expiry_df = df[df["date"] == t.exit_date]
        if expiry_df.empty:
            # Try next day after expiry
            later = [d for d in trading_days if d > t.exit_date]
            if later:
                expiry_df = df[df["date"] == later[0]]
        if not expiry_df.empty:
            t = resolve(t, expiry_df)

        trades.append(t)

    return trades


def fmt_report(trades: list[Trade], label: str = "") -> str:
    if not trades:
        return "  No trades."

    L: list[str] = []
    sep = "=" * 70
    dash = "-" * 70

    L.append("")
    L.append(f"  {sep}")
    tag = f"  {label}" if label else ""
    L.append(f"{tag}  CREDIT SPREAD BACKTEST")
    L.append(f"  {trades[0].entry_date} -> {trades[-1].entry_date}  |  {len(trades)} trades")
    L.append(f"  Width ${trades[0].width:.0f}  DTE {trades[0].dte}  ~{trades[0].otm_pct:.1f}% OTM")
    L.append(f"  {sep}")

    # Overall
    wins = [t for t in trades if t.result in ("win", "partial")]
    losses = [t for t in trades if t.result == "loss"]
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
        mw = [t for t in mt if t.result in ("win", "partial")]
        ml = [t for t in mt if t.result == "loss"]
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
    L.append(f"  {'Entry':<12}{'Expiry':<12}{'ATM':>6}{'Sell':>6}{'Buy':>6}{'Cr':>6}{'P&L':>7}{'ROC':>6}{'OTM':>6}{'R':>3}")
    L.append(f"  {dash}")

    for t in trades:
        tag = "W" if t.result in ("win", "partial") else "L"
        L.append(
            f"  {str(t.entry_date):<12}{str(t.exit_date):<12}"
            f"{t.atm_at_entry:>6.0f}{t.sell_strike:>6.0f}{t.buy_strike:>6.0f}"
            f"${t.credit:>5.2f}${t.pnl:>6.2f}{t.roc_pct:>5.0f}%"
            f"{t.otm_pct:>5.1f}%{tag:>3}"
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
                L.append(
                    f"  {t.entry_date}  {t.sell_strike:.0f}/{t.buy_strike:.0f}  "
                    f"cr=${t.credit:.2f}  P&L=${t.pnl:.2f}  ({t.roc_pct}% ROC)"
                )

    # Drawdown
    cumul, peak, max_dd = 0.0, 0.0, 0.0
    for t in trades:
        cumul += t.pnl
        peak = max(peak, cumul)
        max_dd = max(max_dd, peak - cumul)

    L.append(f"")
    L.append(f"  Max drawdown: ${max_dd:.2f}")
    L.append(f"  Cumulative P&L: ${cumul:.2f}")
    L.append(f"  {sep}")
    L.append("")

    return "\n".join(L)


def main():
    p = argparse.ArgumentParser(description="Backtest SPY bull put credit spreads")
    p.add_argument("--months", type=int, default=3)
    p.add_argument("--width", type=float, default=5.0, help="Strike width ($)")
    p.add_argument("--otm", type=float, default=1.5, help="Target %% OTM from ATM")
    p.add_argument("--dte", type=int, default=7, help="Days to expiry")
    p.add_argument("--min-credit", type=float, default=0.05, help="Min credit ($)")
    p.add_argument("--overlap", action="store_true", help="Allow overlapping positions")
    p.add_argument("--compare", action="store_true", help="Run multiple configs side-by-side")
    args = p.parse_args()

    if args.compare:
        configs = [
            ("Conservative 1% OTM", dict(otm_pct=1.0)),
            ("Standard 1.5% OTM",   dict(otm_pct=1.5)),
            ("Wide 2.5% OTM",       dict(otm_pct=2.5)),
            ("Far 3.5% OTM",        dict(otm_pct=3.5)),
        ]
        for label, kw in configs:
            trades = run_backtest(
                months=args.months, width=args.width, dte=args.dte,
                min_credit=args.min_credit, allow_overlap=args.overlap, **kw,
            )
            print(fmt_report(trades, label=f"[{label}] "))
    else:
        trades = run_backtest(
            months=args.months, width=args.width, otm_pct=args.otm,
            dte=args.dte, min_credit=args.min_credit, allow_overlap=args.overlap,
        )
        print(fmt_report(trades))


if __name__ == "__main__":
    main()
