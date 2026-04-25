#!/usr/bin/env python3
"""
Generate a human-readable trade log from backtest data.
Outputs trades with full contract details for manual TOS verification.
"""
import argparse
from pathlib import Path
import pandas as pd
from strategy import compute_pnl, select_spread

PARQUET_DIR = Path(__file__).parent / "parquet"

def load_data(ticker):
    files = sorted(PARQUET_DIR.glob(f"{ticker}_*.parquet"))
    if not files:
        print(f"No Parquet files found for {ticker}. Run ingest.py first.")
        raise SystemExit(1)
    frames = [pd.read_parquet(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["expiry"] = pd.to_datetime(df["expiry"]).dt.date
    return df


def occ_symbol(ticker, expiry, put_call, strike):
    """Build OCC symbol like SPY260116P00580000"""
    from datetime import date
    yy = str(expiry.year)[2:]
    mm = f"{expiry.month:02d}"
    dd = f"{expiry.day:02d}"
    pc = "C" if put_call == "CALL" else "P"
    strike_int = int(strike * 1000)
    return f"{ticker}{yy}{mm}{dd}{pc}{strike_int:08d}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--width", type=float, default=5.0)
    parser.add_argument("--delta", type=float, default=15.0)
    parser.add_argument("--dte-min", type=int, default=5)
    parser.add_argument("--dte-max", type=int, default=7)
    args = parser.parse_args()

    df = load_data(args.ticker)
    trading_days = sorted(df["date"].unique())
    puts = df[df["option_type"] == "P"].copy()

    trades = []
    for day in trading_days:
        day_puts = puts[puts["date"] == day]
        if day_puts.empty:
            continue

        trade = select_spread(
            day_puts,
            dte_range=(args.dte_min, args.dte_max),
            width=args.width,
            delta_pct=args.delta,
        )
        if trade is None:
            continue

        expiry_data = df[df["date"] == trade["expiry"]]
        pnl = compute_pnl(trade, expiry_data) if not expiry_data.empty else {
            "credit": round(trade["short_premium"] - trade["long_premium"], 3),
            "pnl_per_contract": None,
            "max_loss": round((trade["actual_width"] - (trade["short_premium"] - trade["long_premium"])) * 100, 2),
            "result": "NO_EXPIRY_DATA",
            "short_close": None,
            "long_close": None,
            "anomalous": False,
        }
        trades.append({"entry_date": day, **trade, **pnl})

    # Build output
    lines = []
    sep = "=" * 100
    lines.append(sep)
    lines.append(f"BULL PUT CREDIT SPREAD TRADE LOG")
    lines.append(f"  Ticker: {args.ticker}  |  Width: ${args.width}  |  Delta: ~{args.delta}  |  DTE: {args.dte_min}-{args.dte_max}")
    lines.append(f"  Data: Polygon OPRA day aggs, {trading_days[0]} to {trading_days[-1]}")
    lines.append(sep)
    lines.append("")
    lines.append("HOW TO USE:")
    lines.append("  1. Open TOS -> Trade tab -> type SPY")
    lines.append("  2. Find the expiry date shown below")
    lines.append("  3. Right-click the SELL strike -> Sell to Open")
    lines.append("  4. Add the BUY strike as a leg -> Buy to Open")
    lines.append("  5. Send as a single spread order for the credit shown")
    lines.append("")
    lines.append(f"{'#':>3}  {'Entry Date':>12}  {'Expiry':>12}  {'DTE':>4}  "
                 f"{'SELL Strike':>11}  {'BUY Strike':>10}  {'Width':>6}  "
                 f"{'Entry Credit':>12}  {'Max Risk':>9}  "
                 f"{'Exit Date':>12}  {'Close Cost':>10}  {'P&L/Contract':>13}  {'Result':<15}")
    lines.append("-" * 140)

    wins = losses = 0
    total_pnl = 0

    for i, t in enumerate(trades, 1):
        credit = t["short_premium"] - t["long_premium"]
        max_risk = (t["actual_width"] - credit) * 100
        entry_credit = credit * 100

        close_cost = None
        if t.get("short_close") is not None and t.get("long_close") is not None:
            close_cost = (t["short_close"] - t["long_close"]) * 100

        pnl = t.get("pnl_per_contract")
        if pnl is not None:
            total_pnl += pnl
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1

        result = t.get("result", "?")
        exit_date = t["expiry"] if t.get("short_close") is not None else "N/A"

        # OCC symbols for TOS lookup
        short_occ = occ_symbol(args.ticker, t["expiry"], "PUT", t["short_strike"])
        long_occ = occ_symbol(args.ticker, t["expiry"], "PUT", t["long_strike"])

        close_str = f"${close_cost:>8.2f}" if close_cost is not None else "      N/A"
        pnl_str = f"${pnl:>10.2f}" if pnl is not None else "        N/A"

        lines.append(
            f"{i:>3}  {str(t['entry_date']):>12}  {str(t['expiry']):>12}  {t['dte']:>4}  "
            f"{t['short_strike']:>11.0f}  {t['long_strike']:>10.0f}  "
            f"${t['actual_width']:>4.0f}  "
            f"${entry_credit:>10.2f}  ${max_risk:>7.2f}  "
            f"{str(exit_date):>12}  {close_str}  {pnl_str}  {result:<15}"
        )

    closed = [t for t in trades if t.get("pnl_per_contract") is not None]
    total_closed = len(closed)

    lines.append("")
    lines.append(sep)
    lines.append("SUMMARY")
    lines.append(sep)
    if total_closed > 0:
        lines.append(f"  Total trades:    {len(trades)} ({total_closed} closed, {len(trades)-total_closed} missing data)")
        lines.append(f"  Win rate:        {wins}/{total_closed} ({wins/total_closed*100:.1f}%)")
        lines.append(f"  Total P&L:       ${total_pnl:,.2f} (per contract)")
        if wins > 0:
            avg_win = sum(t["pnl_per_contract"] for t in closed if t["pnl_per_contract"] > 0) / wins
            lines.append(f"  Avg winner:      ${avg_win:,.2f}")
        if losses > 0:
            avg_loss = sum(t["pnl_per_contract"] for t in closed if t["pnl_per_contract"] < 0) / losses
            lines.append(f"  Avg loser:       ${avg_loss:,.2f}")

    # Monthly breakdown
    lines.append("")
    lines.append(f"  {'Month':<10} {'Trades':>7} {'Wins':>5} {'WR%':>6} {'P&L':>12}")
    lines.append("  " + "-" * 45)
    from collections import defaultdict
    monthly = defaultdict(list)
    for t in closed:
        key = str(t["entry_date"])[:7]
        monthly[key].append(t)
    for month in sorted(monthly.keys()):
        m_trades = monthly[month]
        m_wins = sum(1 for t in m_trades if t["pnl_per_contract"] > 0)
        m_pnl = sum(t["pnl_per_contract"] for t in m_trades)
        lines.append(f"  {month:<10} {len(m_trades):>7} {m_wins:>5} {m_wins/len(m_trades)*100:>5.0f}% ${m_pnl:>10,.2f}")

    # Now append FULL DETAIL for each trade (for TOS manual entry)
    lines.append("")
    lines.append("")
    lines.append("=" * 100)
    lines.append("FULL TRADE DETAILS (for manual TOS entry)")
    lines.append("=" * 100)

    for i, t in enumerate(trades, 1):
        credit = t["short_premium"] - t["long_premium"]
        short_occ = occ_symbol(args.ticker, t["expiry"], "PUT", t["short_strike"])
        long_occ = occ_symbol(args.ticker, t["expiry"], "PUT", t["long_strike"])
        pnl = t.get("pnl_per_contract")

        lines.append("")
        lines.append(f"--- Trade #{i} ---")
        lines.append(f"  BULL PUT CREDIT SPREAD  (you want SPY to stay ABOVE the sold strike)")
        lines.append(f"  Entry: {t['entry_date']}    Expiry: {t['expiry']}    DTE: {t['dte']}")
        lines.append(f"  Width: ${t['actual_width']:.0f}")
        lines.append(f"")
        lines.append(f"  LEG 1:  SELL  {t['short_strike']:.0f} PUT   (you collect premium, this is your short)")
        lines.append(f"          {args.ticker} {t['expiry']} {t['short_strike']:.0f} PUT    ({short_occ})")
        lines.append(f"          Entry: ${t['short_premium']:.2f}")
        if t.get("short_close") is not None:
            lines.append(f"          Exit:  ${t['short_close']:.2f}")
        lines.append(f"")
        lines.append(f"  LEG 2:  BUY   {t['long_strike']:.0f} PUT   (this is your protection/cap)")
        lines.append(f"          {args.ticker} {t['expiry']} {t['long_strike']:.0f} PUT    ({long_occ})")
        lines.append(f"          Entry: ${t['long_premium']:.2f}")
        if t.get("long_close") is not None:
            lines.append(f"          Exit:  ${t['long_close']:.2f}")
        lines.append(f"")
        lines.append(f"  You SELL the {t['short_strike']:.0f} put and BUY the {t['long_strike']:.0f} put as one order.")
        lines.append(f"  Net Credit: ${credit:.2f}/share = ${credit*100:.0f}/contract (cash into your account)")
        lines.append(f"  Max Risk:   ${(t['actual_width']-credit)*100:.0f}/contract (you lose this if SPY drops below {t['long_strike']:.0f})")
        lines.append(f"  Breakeven:  {t['short_strike'] - credit:.2f} (SPY must stay above this)")
        if pnl is not None:
            lines.append(f"  Result:     {t.get('result','?')}  |  P&L: ${pnl:.2f}/contract")
        else:
            lines.append(f"  Result:     {t.get('result','NO DATA')}")

    outpath = Path(__file__).parent / "trade_log.txt"
    with open(outpath, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {len(trades)} trades to {outpath}")


if __name__ == "__main__":
    main()
