#!/usr/bin/env python3
"""Backtest 5-7 DTE bull put credit spreads using Polygon day agg data.

Uses strategy.py for all core logic (tested in test_strategy.py).

Usage:
    python backtest.py                          # default: SPY, $5 wide, 15 delta
    python backtest.py --ticker QQQ --width 2 --delta 20
    python backtest.py --dte-min 5 --dte-max 7
"""

import argparse
from pathlib import Path

import pandas as pd

from strategy import compute_pnl, select_spread

PARQUET_DIR = Path(__file__).parent / "parquet"


def load_data(ticker):
    """Load all Parquet files for the given ticker."""
    files = sorted(PARQUET_DIR.glob(f"{ticker}_*.parquet"))
    if not files:
        print(f"No Parquet files found for {ticker}. Run ingest.py first.")
        raise SystemExit(1)

    frames = [pd.read_parquet(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["expiry"] = pd.to_datetime(df["expiry"]).dt.date
    return df


def main():
    parser = argparse.ArgumentParser(description="Backtest 5-7 DTE bull put credit spreads")
    parser.add_argument("--ticker", default="SPY", help="Underlier (default: SPY)")
    parser.add_argument("--width", type=float, default=5.0, help="Spread width in $ (default: 5)")
    parser.add_argument("--delta", type=float, default=15.0, help="Short leg delta proxy (default: 15)")
    parser.add_argument("--dte-min", type=int, default=5, help="Min DTE (default: 5)")
    parser.add_argument("--dte-max", type=int, default=7, help="Max DTE (default: 7)")
    parser.add_argument(
        "--capital", type=float, default=20000, help="Bankroll for sizing (default: $20,000)"
    )
    args = parser.parse_args()

    print(f"Loading {args.ticker} data...")
    df = load_data(args.ticker)
    print(f"  {len(df):,} option-day rows loaded")
    print(f"  Dates: {df['date'].min()} to {df['date'].max()}\n")

    print("=" * 70)
    print("BACKTEST: Bull Put Credit Spreads")
    print(f"  Ticker:  {args.ticker}")
    print(f"  Width:   ${args.width}")
    print(f"  Delta:   ~{args.delta}")
    print(f"  DTE:     {args.dte_min}-{args.dte_max}")
    print(f"  Capital: ${args.capital:,.0f}")
    print("=" * 70 + "\n")

    trading_days = sorted(df["date"].unique())
    puts = df[df["option_type"] == "P"].copy()

    trades = []
    anomaly_count = 0

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

        # Get expiry data for closing prices
        expiry_data = df[df["date"] == trade["expiry"]]

        if expiry_data.empty:
            trades.append({
                "entry_date": day,
                **trade,
                "credit": round(trade["short_premium"] - trade["long_premium"], 3),
                "pnl_per_contract": None,
                "max_loss": round((trade["actual_width"] - (trade["short_premium"] - trade["long_premium"])) * 100, 2),
                "result": "NO_EXPIRY_DATA",
                "short_close": None,
                "long_close": None,
                "anomalous": False,
            })
            continue

        pnl = compute_pnl(trade, expiry_data)

        if pnl.get("anomalous"):
            anomaly_count += 1

        trades.append({
            "entry_date": day,
            **trade,
            **pnl,
        })

    if not trades:
        print("No trades generated. Try adjusting DTE range or delta.")
        return

    trades_df = pd.DataFrame(trades)

    # Filter to trades with known outcomes
    closed = trades_df[~trades_df["result"].isin(["NO_EXPIRY_DATA", "MISSING_DATA"])].copy()

    print(f"Total signals:  {len(trades_df)}")
    print(f"Closed trades:  {len(closed)}")
    print(f"Missing data:   {len(trades_df) - len(closed)}")
    print(f"Anomalous data: {anomaly_count} (P&L bounded to theoretical limits)\n")

    if closed.empty:
        print("No closed trades to analyze.")
        return

    # Results summary
    wins = closed[closed["pnl_per_contract"] > 0]
    losses = closed[closed["pnl_per_contract"] < 0]
    pushes = closed[closed["pnl_per_contract"] == 0]

    total_pnl = closed["pnl_per_contract"].sum()
    avg_win = wins["pnl_per_contract"].mean() if len(wins) else 0
    avg_loss = losses["pnl_per_contract"].mean() if len(losses) else 0

    print("-" * 70)
    print("RESULTS")
    print("-" * 70)
    print(f"  Win rate:            {len(wins)}/{len(closed)} ({len(wins)/len(closed)*100:.1f}%)")
    if len(pushes) > 0:
        print(f"  Pushes:              {len(pushes)}")
    print(f"  Total P&L:           ${total_pnl:,.2f} (per contract)")
    print(f"  Avg winning trade:   ${avg_win:,.2f}")
    print(f"  Avg losing trade:    ${avg_loss:,.2f}")
    print(f"  Avg credit received: ${closed['credit'].mean():.3f} (${closed['credit'].mean()*100:.2f})")
    print(f"  Avg DTE:             {closed['dte'].mean():.1f}")

    # Outcome breakdown
    print(f"\n  Outcome breakdown:")
    for outcome in ["FULL_WIN", "PARTIAL_WIN", "PUSH", "PARTIAL_LOSS", "MAX_LOSS"]:
        count = len(closed[closed["result"] == outcome])
        if count > 0:
            avg_pnl = closed[closed["result"] == outcome]["pnl_per_contract"].mean()
            print(f"    {outcome:<16} {count:>3} trades  (avg ${avg_pnl:>8,.2f})")

    # Monthly breakdown
    closed["entry_month"] = pd.to_datetime(closed["entry_date"]).dt.to_period("M")
    print(f"\n  Monthly P&L:")
    for month, mdf in closed.groupby("entry_month"):
        mpnl = mdf["pnl_per_contract"].sum()
        wins_m = len(mdf[mdf["pnl_per_contract"] > 0])
        total_m = len(mdf)
        wr = wins_m / total_m * 100
        print(f"    {month}: ${mpnl:>8,.2f}  ({wins_m}/{total_m} wins, {wr:.0f}%)")

    # Save trades to CSV
    out_path = Path(__file__).parent / "backtest_results.csv"
    closed.to_csv(out_path, index=False)
    print(f"\n  Trade log saved to: {out_path}")

    # Expectancy
    if len(wins) > 0 and len(losses) > 0:
        win_rate = len(wins) / len(closed)
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
        print(f"\n  Expectancy per trade: ${expectancy:,.2f}")

        annual_trades = 52
        print(f"  Projected annual ({annual_trades} trades): ${expectancy * annual_trades:,.2f}")

        # Risk metrics
        avg_credit = closed["credit"].mean() * 100
        avg_max_loss = closed["max_loss"].mean()
        print(f"\n  Avg credit/max risk:  ${avg_credit:.0f} / ${avg_max_loss:.0f} = {avg_credit/avg_max_loss:.2f}x")


if __name__ == "__main__":
    main()
