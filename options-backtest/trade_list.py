#!/usr/bin/env python3
"""Print detailed trade list by month from backtest_results.csv."""

import pandas as pd

df = pd.read_csv("backtest_results.csv")
df["entry_date"] = pd.to_datetime(df["entry_date"])
df["expiry"] = pd.to_datetime(df["expiry"])

for month, mdf in df.groupby(df["entry_date"].dt.to_period("M")):
    trades = []
    for _, row in mdf.iterrows():
        trades.append({
            "entry": row["entry_date"].strftime("%m/%d"),
            "expiry": row["expiry"].strftime("%m/%d"),
            "dte": int(row["dte"]),
            "short_k": round(row["short_strike"], 1),
            "long_k": round(row["long_strike"], 1),
            "width": round(row["actual_width"], 1),
            "credit": round(row["credit"], 2),
            "pnl": round(row["pnl_per_contract"], 2),
            "result": row["result"],
            "short_close": round(row["short_close"], 3),
            "long_close": round(row["long_close"], 3),
        })

    wins = len([t for t in trades if t["pnl"] > 0])
    losses = len([t for t in trades if t["pnl"] <= 0])
    total_pnl = sum(t["pnl"] for t in trades)
    total_credit = sum(t["credit"] * 100 for t in trades)

    print(f"=== {month} === ({len(trades)} trades, {wins}W/{losses}L, P&L: ${total_pnl:,.2f}, Credits: ${total_credit:,.2f})")
    print(f"{'Entry':>6} {'Expiry':>6} {'DTE':>3} {'Short':>7} {'Long':>7} {'Width':>5} {'Credit':>7} {'P&L':>8} {'SClose':>7} {'LClose':>7}  Result")
    print("-" * 90)
    for t in trades:
        pnl_str = f"${t['pnl']:>7.2f}" if t['pnl'] >= 0 else f"-${abs(t['pnl']):>6.2f}"
        print(
            f"{t['entry']:>6} {t['expiry']:>6} {t['dte']:>3} "
            f"{t['short_k']:>7.1f} {t['long_k']:>7.1f} {t['width']:>5.1f} "
            f"{t['credit']:>7.2f} {pnl_str:>8} "
            f"{t['short_close']:>7.3f} {t['long_close']:>7.3f}  {t['result']}"
        )
    print()
