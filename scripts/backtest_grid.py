"""
Grid search backtest for SPY credit spreads -- optimized single-pass version.

Scans option chain once per (spread_type, otm, dte) combo, then splits results
by stop/target/dow/trend in memory. ~10x faster than naive grid.

Usage:
    python3 scripts/backtest_grid.py
    python3 scripts/backtest_grid.py --csv grid_results.csv
    python3 scripts/backtest_grid.py --top 20
    python3 scripts/backtest_grid.py --sort pf
    python3 scripts/backtest_grid.py --quick
    python3 scripts/backtest_grid.py --full
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import product

import pandas as pd

PARQUET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "options-backtest", "parquet",
)


@dataclass
class TradeRaw:
    """Minimal trade record for fast in-memory processing."""
    entry_date: date
    exit_date: date
    expiry_date: date
    spread_type: str
    sell_strike: float
    buy_strike: float
    width: float
    credit: float
    max_loss: float
    roc_pct: float
    otm_pct: float
    atm_at_entry: float
    sell_entry: float
    buy_entry: float
    sell_exit: float = 0.0
    buy_exit: float = 0.0
    pnl_expiry: float = 0.0       # P&L if held to expiry
    result_expiry: str = ""       # result if held to expiry
    daily_spread: dict = field(default_factory=dict)  # {date: spread_cost}
    occ_sell: str = ""
    occ_buy: str = ""


def build_occ(symbol: str, expiry: date, option_type: str, strike: float) -> str:
    sym = symbol.ljust(6)
    exp_str = expiry.strftime("%y%m%d")
    cp = "C" if option_type == "call" else "P"
    strike_str = f"{int(strike * 1000):08d}"
    return f"{sym}{exp_str}{cp}{strike_str}"


def estimate_atm(options: pd.DataFrame, opt_type: str) -> float | None:
    if options.empty:
        return None
    for _, r in options.sort_values("strike", ascending=(opt_type == "C")).iterrows():
        if 1.50 < r["close"] < 4.00:
            return float(r["strike"])
    vol = options[options["volume"] > 0]
    if not vol.empty:
        return float(vol.loc[vol["volume"].idxmax(), "strike"])
    return float(options["strike"].median())


def pick_raw_spread(
    options: pd.DataFrame, atm: float, width: float, otm_pct: float, opt_type: str,
    min_credit: float = 0.05,
) -> dict | None:
    if opt_type == "P":
        target_sell = atm * (1 - otm_pct / 100.0)
        target_buy = target_sell - width
    else:
        target_sell = atm * (1 + otm_pct / 100.0)
        target_buy = target_sell + width

    strikes = sorted(options["strike"].unique())
    sell_k = min(strikes, key=lambda s: abs(s - target_sell))
    buy_k = (sell_k - width) if opt_type == "P" else (sell_k + width)

    if buy_k not in strikes:
        best, best_dist = None, 999
        for s in strikes:
            b = (s - width) if opt_type == "P" else (s + width)
            if b in strikes:
                dist = abs(s - target_sell)
                if dist < best_dist:
                    best_dist, best = dist, (s, b)
        if best is None:
            return None
        sell_k, buy_k = best

    sell_row = options[options["strike"] == sell_k].iloc[0]
    buy_row = options[options["strike"] == buy_k].iloc[0]
    sell_px = float(sell_row["close"])
    buy_px = float(buy_row["close"])
    credit = sell_px - buy_px

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
        entry = entry.date()
    if isinstance(expiry, pd.Timestamp):
        expiry = expiry.date()

    spread_type = "bull_put" if opt_type == "P" else "bear_call"
    opt_name = "put" if opt_type == "P" else "call"

    return {
        "entry_date": entry, "expiry_date": expiry,
        "spread_type": spread_type, "opt_type": opt_type,
        "sell_strike": sell_k, "buy_strike": buy_k,
        "width": width, "credit": credit, "max_loss": risk,
        "roc_pct": roc, "otm_pct": actual_otm, "atm_at_entry": atm,
        "sell_entry": sell_px, "buy_entry": buy_px,
        "occ_sell": build_occ("SPY", expiry, opt_name, sell_k),
        "occ_buy": build_occ("SPY", expiry, opt_name, buy_k),
    }


def resolve_expiry_pnl(trade_info: dict, df: pd.DataFrame) -> tuple[float, str]:
    """Get P&L and result if held to expiry."""
    opt_type = trade_info["opt_type"]
    pool = df[(df["date"] == trade_info["expiry_date"]) & (df["dte"] == 0)]

    sell = pool[(pool["strike"] == trade_info["sell_strike"]) & (pool["option_type"] == opt_type)]
    buy = pool[(pool["strike"] == trade_info["buy_strike"]) & (pool["option_type"] == opt_type)]

    if len(sell) > 0 and len(buy) > 0:
        sell_exit = float(sell.iloc[0]["close"])
        buy_exit = float(buy.iloc[0]["close"])
        spread_at_exp = sell_exit - buy_exit
        pnl = trade_info["credit"] - spread_at_exp
    else:
        if opt_type == "P":
            deeper = pool[(pool["strike"] >= trade_info["sell_strike"]) & (pool["strike"] <= trade_info["sell_strike"] + 5)]
        else:
            deeper = pool[(pool["strike"] <= trade_info["sell_strike"]) & (pool["strike"] >= trade_info["sell_strike"] - 5)]
        if not deeper.empty and deeper["close"].max() > 0.50:
            pnl = -trade_info["max_loss"]
        else:
            pnl = trade_info["credit"]

    if pnl >= trade_info["credit"] * 0.5:
        return pnl, "win"
    elif pnl > 0:
        return pnl, "partial"
    else:
        return pnl, "loss"


def collect_daily_spread(trade_info: dict, df: pd.DataFrame) -> dict:
    """Collect daily spread cost for stop/target simulation."""
    opt_type = trade_info["opt_type"]
    expiry = trade_info["expiry_date"]
    entry = trade_info["entry_date"]

    days = {}
    for day in sorted(df["date"].unique()):
        if not isinstance(day, date):
            day = pd.Timestamp(day).date()
        if day < entry or day > expiry:
            continue

        day_pool = df[df["date"] == day]
        sell = day_pool[
            (day_pool["strike"] == trade_info["sell_strike"]) &
            (day_pool["option_type"] == opt_type) &
            (day_pool["expiry"] == expiry)
        ]
        buy = day_pool[
            (day_pool["strike"] == trade_info["buy_strike"]) &
            (day_pool["option_type"] == opt_type) &
            (day_pool["expiry"] == expiry)
        ]
        if sell.empty or buy.empty:
            continue
        spread_cost = float(sell.iloc[0]["close"]) - float(buy.iloc[0]["close"])
        dte = int(sell.iloc[0]["dte"])
        days[day] = {"spread_cost": spread_cost, "dte": dte}
    return days


def simulate_exit(trade_info: dict, daily: dict, pnl_expiry: float,
                  stop_pct: float | None, target_pct: float | None,
                  ) -> tuple[float, str, str, int, date]:
    """
    Simulate exit with stop/target. Returns (pnl, result, reason, exit_dte, exit_date).
    """
    credit = trade_info["credit"]
    max_loss = trade_info["max_loss"]
    entry = trade_info["entry_date"]

    sorted_days = sorted(daily.keys())

    for day in sorted_days:
        if day <= entry:
            continue
        info = daily[day]
        unrealized = credit - info["spread_cost"]

        # Stop-loss check
        if stop_pct is not None and unrealized < 0:
            stop_line = -(max_loss * stop_pct / 100.0)
            if unrealized <= stop_line:
                return unrealized, "stopped", "stop_loss", info["dte"], day

        # Profit target check
        if target_pct is not None:
            target_line = credit * target_pct / 100.0
            if unrealized >= target_line:
                return unrealized, "target", "profit_target", info["dte"], day

    # Held to expiry
    result = "win" if pnl_expiry >= credit * 0.5 else ("partial" if pnl_expiry > 0 else "loss")
    return pnl_expiry, result, "expiry", 0, trade_info["expiry_date"]


def build_spy_series(df: pd.DataFrame) -> pd.DataFrame:
    spy_daily = []
    for day in sorted(df["date"].unique()):
        atm_estimates = []
        for dte_val in [5, 7, 9, 14]:
            day_puts = df[(df["date"] == day) & (df["option_type"] == "P") & (df["dte"] == dte_val)]
            if day_puts.empty:
                continue
            cands = day_puts[(day_puts["close"] > 1.50) & (day_puts["close"] < 4.00)]
            if cands.empty:
                continue
            cands = cands.copy()
            cands["dist"] = abs(cands["close"] - 2.75)
            atm_estimates.append(float(cands.loc[cands["dist"].idxmin(), "strike"]))
        if not atm_estimates:
            continue

        if not isinstance(day, date):
            day = pd.Timestamp(day).date()
        spy_daily.append({
            "date": day,
            "spy_close": round(sum(atm_estimates) / len(atm_estimates), 1),
            "dow": day.weekday(),
        })

    sdf = pd.DataFrame(spy_daily).sort_values("date").reset_index(drop=True)
    sdf["sma_20"] = sdf["spy_close"].rolling(20).mean()
    sdf["trend"] = sdf.apply(
        lambda r: "bull" if pd.notna(r["sma_20"]) and r["spy_close"] > r["sma_20"]
        else ("bear" if pd.notna(r["sma_20"]) else "unknown"), axis=1,
    )
    return sdf


@dataclass
class GridResult:
    rank: int = 0
    spread_type: str = ""
    otm_pct: float = 0
    dte: int = 0
    stop_loss: float | None = None
    profit_target: float | None = None
    dow: str = ""
    trend: str = ""
    n_trades: int = 0
    win_rate: float = 0
    total_pnl: float = 0
    avg_credit: float = 0
    profit_factor: float = 0
    max_drawdown: float = 0
    sharpe: float = 0
    avg_hold: float = 0


def main():
    p = argparse.ArgumentParser(description="Grid search for optimal credit spread params")
    p.add_argument("--months", type=int, default=6)
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--sort", choices=["pf", "pnl", "wr", "sharpe"], default="sharpe")
    p.add_argument("--csv", type=str, default=None)
    p.add_argument("--quick", action="store_true")
    p.add_argument("--full", action="store_true")
    p.add_argument("--min-trades", type=int, default=10, help="Minimum trades for a valid result")
    args = p.parse_args()

    files = sorted(glob.glob(os.path.join(PARQUET_DIR, "SPY_*.parquet")))
    if not files:
        print("No SPY parquet files found")
        return
    dfs = [pd.read_parquet(f) for f in files[-args.months:]]
    df = pd.concat(dfs, ignore_index=True)
    spy_df = build_spy_series(df)

    # Build spy lookup
    spy_lookup = {}
    for _, row in spy_df.iterrows():
        d = row["date"] if isinstance(row["date"], date) else pd.Timestamp(row["date"]).date()
        spy_lookup[d] = {"dow": int(row["dow"]), "trend": row["trend"]}

    trading_days = sorted(df["date"].unique())
    print(f"Loaded {len(df):,} rows, {len(trading_days)} trading days")

    # Phase 1: Collect all trades per (spread_type, otm, dte) -- single pass
    if args.full:
        otm_range = [1.0, 1.5, 2.0, 2.5, 3.0]
        dte_range = [5, 7, 9, 14]
        types = ["bull_put", "bear_call"]
    elif args.quick:
        otm_range = [1.0, 1.5, 2.5]
        dte_range = [7]
        types = ["bull_put"]
    else:
        otm_range = [1.0, 1.5, 2.0, 2.5]
        dte_range = [5, 7, 9]
        types = ["bull_put", "bear_call"]

    base_combos = len(otm_range) * len(dte_range) * len(types)
    print(f"Phase 1: Scanning {base_combos} base combos...", flush=True)

    # Store: key=(spread_type, otm, dte) -> list of (trade_info, daily_spread, pnl_expiry, entry_date)
    all_trades: dict[tuple, list] = defaultdict(list)

    for stype in types:
        opt_type = "P" if stype == "bull_put" else "C"
        for otm in otm_range:
            for dte in dte_range:
                open_expiry: set = set()
                for day in trading_days:
                    if not isinstance(day, date):
                        day = pd.Timestamp(day).date()

                    open_expiry = {e for e in open_expiry if e > day}

                    day_df = df[df["date"] == day]
                    pool = day_df[(day_df["option_type"] == opt_type) & (day_df["dte"] == dte)]
                    if pool.empty:
                        continue

                    atm = estimate_atm(pool, opt_type)
                    if atm is None:
                        continue

                    info = pick_raw_spread(pool, atm, 5.0, otm, opt_type)
                    if info is None:
                        continue

                    if open_expiry:
                        continue

                    open_expiry.add(info["expiry_date"])

                    # Resolve at expiry
                    pnl_exp, result_exp = resolve_expiry_pnl(info, df)

                    # Collect daily spreads for stop/target sim
                    daily = collect_daily_spread(info, df)

                    all_trades[(stype, otm, dte)].append({
                        "info": info,
                        "daily": daily,
                        "pnl_expiry": pnl_exp,
                        "result_expiry": result_exp,
                        "entry_date": info["entry_date"],
                    })

    total_raw = sum(len(v) for v in all_trades.values())
    print(f"  Collected {total_raw} raw trades across {len(all_trades)} base combos")

    # Phase 2: For each base combo, simulate all (stop, target, dow, trend) combos in memory
    if args.full:
        stop_range = [None, 50, 75]
        target_range = [None, 50, 75]
        dow_range = ["all", "Mon", "Tue", "Wed", "Thu", "Fri"]
        trend_range = ["all", "bull", "bear"]
    elif args.quick:
        stop_range = [None, 50]
        target_range = [None, 75]
        dow_range = ["all"]
        trend_range = ["all"]
    else:
        stop_range = [None, 50, 75]
        target_range = [None, 75]
        dow_range = ["all", "Mon", "Tue", "Wed", "Thu", "Fri"]
        trend_range = ["all", "bull"]

    filter_combos = len(stop_range) * len(target_range) * len(dow_range) * len(trend_range)
    print(f"Phase 2: Simulating {filter_combos} filter combos x {len(all_trades)} bases = {filter_combos * len(all_trades)} total...", flush=True)

    DOW_MAP = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}
    results: list[GridResult] = []

    for (stype, otm, dte), trades in all_trades.items():
        for sl, pt, dow_f, trend_f in product(stop_range, target_range, dow_range, trend_range):
            pnls = []
            holds = []
            credits = []

            for t in trades:
                # Filter by DOW
                info_spy = spy_lookup.get(t["entry_date"])
                if info_spy is None:
                    continue
                if dow_f != "all" and info_spy["dow"] != DOW_MAP.get(dow_f, -1):
                    continue
                if trend_f != "all":
                    if info_spy["trend"] == "unknown":
                        continue
                    if trend_f != info_spy["trend"]:
                        continue

                # Simulate exit
                pnl, result, reason, exit_dte, exit_date = simulate_exit(
                    t["info"], t["daily"], t["pnl_expiry"], sl, pt
                )
                pnls.append(pnl)
                credits.append(t["info"]["credit"])
                if isinstance(t["entry_date"], date) and isinstance(exit_date, date):
                    holds.append((exit_date - t["entry_date"]).days)

            if len(pnls) < args.min_trades:
                continue

            wins = sum(1 for p in pnls if p >= 0)
            losses = sum(1 for p in pnls if p < 0)
            total_pnl = sum(pnls)
            gw = sum(p for p in pnls if p > 0)
            gl = abs(sum(p for p in pnls if p < 0))
            pf = gw / gl if gl else 999.0

            cumul, peak, max_dd = 0.0, 0.0, 0.0
            for p in pnls:
                cumul += p
                peak = max(peak, cumul)
                max_dd = max(max_dd, peak - cumul)

            results.append(GridResult(
                spread_type=stype, otm_pct=otm, dte=dte,
                stop_loss=sl, profit_target=pt,
                dow=dow_f, trend=trend_f,
                n_trades=len(pnls),
                win_rate=wins / len(pnls) * 100,
                total_pnl=round(total_pnl, 2),
                avg_credit=round(sum(credits) / len(credits), 2),
                profit_factor=round(pf, 2),
                max_drawdown=round(max_dd, 2),
                sharpe=round(total_pnl / max_dd, 2) if max_dd > 0 else 999.0,
                avg_hold=round(sum(holds) / len(holds), 1) if holds else 0,
            ))

    print(f"  {len(results)} valid results")

    # Sort
    sort_key = {
        "pf": lambda r: r.profit_factor,
        "pnl": lambda r: r.total_pnl,
        "wr": lambda r: r.win_rate,
        "sharpe": lambda r: r.sharpe,
    }
    results.sort(key=sort_key[args.sort], reverse=True)

    # Print
    sep = "-" * 115
    n = min(args.top, len(results))
    print(f"\n  TOP {n} CONFIGURATIONS (sorted by {args.sort})")
    print(f"  {sep}")
    print(f"  {'#':>3} {'Type':>4} {'OTM':>5} {'DTE':>4} {'Stop':>6} {'Tgt':>6} {'DOW':<5} {'Trend':<6} "
          f"{'#':>4} {'WR':>5} {'P&L':>8} {'PF':>6} {'MaxDD':>7} {'ShR':>6} {'Hold':>5} {'AvgCr':>6}")
    print(f"  {sep}")

    for i, r in enumerate(results[:n]):
        sl_s = f"{int(r.stop_loss)}%" if r.stop_loss else "---"
        pt_s = f"{int(r.profit_target)}%" if r.profit_target else "---"
        tp = "BP" if r.spread_type == "bull_put" else "BC"
        print(
            f"  {i+1:>3} {tp:>4} {r.otm_pct:>4.1f}% {r.dte:>4} {sl_s:>6} {pt_s:>6} "
            f"{r.dow:<5} {r.trend:<6} "
            f"{r.n_trades:>4} {r.win_rate:>4.0f}% ${r.total_pnl:>7.2f} "
            f"{r.profit_factor:>5.1f} ${r.max_drawdown:>6.2f} "
            f"{r.sharpe:>5.1f} {r.avg_hold:>4.1f}d ${r.avg_credit:>5.2f}"
        )
    print(f"  {sep}")

    # Day-of-week summary (aggregate across all configs)
    print(f"\n  DAY-OF-WEEK SUMMARY (all configs aggregated)")
    print(f"  {sep}")
    dow_agg = defaultdict(lambda: {"pnl": 0, "trades": 0, "wins": 0})
    for r in results:
        if r.dow != "all" and r.trend == "all" and r.stop_loss is None and r.profit_target is None:
            dow_agg[r.dow]["pnl"] += r.total_pnl
            dow_agg[r.dow]["trades"] += r.n_trades
            dow_agg[r.dow]["wins"] += int(r.n_trades * r.win_rate / 100)
    print(f"  {'Day':<6} {'#Trades':>8} {'Tot P&L':>10} {'Avg P&L':>10} {'WR':>6}")
    print(f"  {sep}")
    for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
        a = dow_agg[d]
        if a["trades"] > 0:
            wr = a["wins"] / a["trades"] * 100
            avg = a["pnl"] / (a["trades"] // max(1, a["trades"] // results_per_dow(results, d)))
            print(f"  {d:<6} {a['trades']:>8} ${a['pnl']:>9.2f} ${a['pnl']/max(a['trades'],1):>9.2f} {wr:>5.0f}%")
    print(f"  {sep}")

    # Trend summary
    print(f"\n  TREND SUMMARY")
    print(f"  {sep}")
    for tf in ["bull", "bear", "all"]:
        matching = [r for r in results if r.trend == tf and r.dow == "all"
                    and r.stop_loss is None and r.profit_target is None
                    and r.spread_type == "bull_put" and r.otm_pct == 1.5 and r.dte == 7]
        if matching:
            r = matching[0]
            print(f"  {tf:<6}: {r.n_trades:>3} trades, {r.win_rate:.0f}% WR, ${r.total_pnl:.2f} P&L, PF {r.profit_factor:.1f}")
    print(f"  {sep}")

    # CSV
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "rank", "type", "otm_pct", "dte", "stop_loss", "profit_target",
                "dow", "trend", "n_trades", "win_rate", "total_pnl",
                "avg_credit", "profit_factor", "max_drawdown", "sharpe", "avg_hold",
            ])
            for i, r in enumerate(results):
                w.writerow([
                    i+1, r.spread_type, r.otm_pct, r.dte, r.stop_loss, r.profit_target,
                    r.dow, r.trend, r.n_trades, round(r.win_rate, 1), r.total_pnl,
                    r.avg_credit, r.profit_factor, r.max_drawdown, r.sharpe, r.avg_hold,
                ])
        print(f"\n  Exported {len(results)} results to {args.csv}")


def results_per_dow(results, dow):
    """Count how many result rows for a given DOW."""
    return sum(1 for r in results if r.dow == dow and r.trend == "all" and r.stop_loss is None and r.profit_target is None)


if __name__ == "__main__":
    main()
