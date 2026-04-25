#!/usr/bin/env python3
"""Monthly trade report with full option details at open and close.

Usage:
    python report.py                  # all months
    python report.py --month 2025-09  # single month
"""

import argparse
from pathlib import Path

import pandas as pd

PARQUET_DIR = Path(__file__).parent / "parquet"
RESULTS_FILE = Path(__file__).parent / "backtest_results.csv"


def get_spy_price(df: pd.DataFrame, date, strike=None, option_type="P"):
    """Estimate SPY underlying price on a given date.
    
    Uses the highest-volume 0DTE put strike as proxy for where SPY was trading.
    0DTE options have the most liquidity and cluster around ATM.
    """
    day_data = df[df["date"] == date]
    if day_data.empty:
        return None
    
    # Look at 0DTE options (expiry == date) for best ATM estimate
    otdle = day_data[day_data["expiry"] == date]
    if not otdle.empty:
        puts = otdle[otdle["option_type"] == "P"]
        if not puts.empty:
            # Highest volume 0DTE put strike ≈ ATM
            atm = puts.nlargest(5, "volume")
            return atm.iloc[0]["strike"]
    
    # Fallback: use nearest-expiry high-volume puts
    puts = day_data[day_data["option_type"] == "P"]
    if puts.empty:
        return None
    
    # Group by expiry, pick nearest expiry with decent volume
    nearest_expiry = puts["expiry"].min()
    near_puts = puts[puts["expiry"] == nearest_expiry]
    top = near_puts.nlargest(10, "volume")
    
    # Among top-volume puts, the strike where premium ~ $1-3 is near ATM
    # Pick the put with the smallest open among top-volume (closest to OTM = ATM)
    atm_put = top.loc[top["open"].idxmin()]
    return atm_put["strike"]


def build_report(month_filter=None):
    # Load trade results
    trades = pd.read_csv(RESULTS_FILE)
    trades["entry_date"] = pd.to_datetime(trades["entry_date"]).dt.date
    trades["expiry"] = pd.to_datetime(trades["expiry"]).dt.date
    trades["entry_month"] = pd.to_datetime(trades["entry_date"]).dt.to_period("M")

    # Load SPY parquet for underlying price context
    parquet_files = sorted(PARQUET_DIR.glob("SPY_*.parquet"))
    if not parquet_files:
        print("No SPY parquet data found. Run ingest.py first.")
        return

    frames = [pd.read_parquet(f) for f in parquet_files]
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["expiry"] = pd.to_datetime(df["expiry"]).dt.date

    # Filter to month if requested
    if month_filter:
        trades = trades[trades["entry_month"] == pd.Period(month_filter, freq="M")]

    for month, mdf in trades.groupby("entry_month"):
        wins = mdf[mdf["pnl_per_contract"] > 0]
        losses = mdf[mdf["pnl_per_contract"] <= 0]
        total_pnl = mdf["pnl_per_contract"].sum()
        total_credit = (mdf["credit"] * 100).sum()
        total_risk = mdf["max_loss"].sum()
        win_rate = len(wins) / len(mdf) * 100

        print("=" * 100)
        print(f"  {month}  |  {len(mdf)} trades  |  {len(wins)}W {len(losses)}L  |  "
              f"Win rate: {win_rate:.0f}%  |  P&L: ${total_pnl:,.0f}  |  "
              f"Credits: ${total_credit:,.0f}  |  Capital at risk: ${total_risk:,.0f}")
        print("=" * 100)

        for i, (_, row) in enumerate(mdf.iterrows()):
            entry = row["entry_date"]
            expiry = row["expiry"]
            anomalous = row.get("anomalous", False)
            anom_tag = " *" if anomalous else ""

            # Get underlying approx price at entry and expiry
            spy_entry = get_spy_price(df, entry)
            spy_expiry = get_spy_price(df, expiry)

            spy_entry_str = f"{spy_entry:.0f}" if spy_entry else "N/A"
            spy_expiry_str = f"{spy_expiry:.0f}" if spy_expiry else "N/A"

            short_k = row["short_strike"]
            long_k = row["long_strike"]
            width = row["actual_width"]
            dte = int(row["dte"])
            credit = row["credit"]
            max_loss = row["max_loss"]
            pnl = row["pnl_per_contract"]
            result = row["result"]

            short_open = row["short_premium"]
            long_open = row["long_premium"]
            short_close = row["short_close"]
            long_close = row["long_close"]

            # Distance from underlying at entry
            if spy_entry:
                short_otm_pct = (spy_entry - short_k) / spy_entry * 100
                long_otm_pct = (spy_entry - long_k) / spy_entry * 100
                short_otm_str = f"{short_otm_pct:.1f}% OTM"
                long_otm_str = f"{long_otm_pct:.1f}% OTM"
            else:
                short_otm_str = "N/A"
                long_otm_str = "N/A"

            # Spread value at close
            if short_close is not None and long_close is not None:
                spread_close = short_close - long_close
                spread_close_str = f"${spread_close:.2f}"
            else:
                spread_close_str = "N/A"

            pnl_sign = "+" if pnl > 0 else ""
            result_str = f"{result}{anom_tag}"

            print()
            print(f"  Trade {i+1}: {entry} -> {expiry}  ({dte} DTE, ${width:.0f} wide)")
            print(f"  {'─' * 94}")
            print(f"  {'':30} {'OPEN (entry)':>14}  {'CLOSE (expiry)':>14}  {'':>10}")
            print(f"  {'':30} {'price':>14}  {'price':>14}  {'OTM':>10}")
            print(f"  {'Short put':30} {'$' + f'{short_open:.2f}':>14}  {'$' + f'{short_close:.2f}':>14}  {short_otm_str:>10}  K={short_k:.0f}")
            print(f"  {'Long put':30} {'$' + f'{long_open:.2f}':>14}  {'$' + f'{long_close:.2f}':>14}  {long_otm_str:>10}  K={long_k:.0f}")
            print(f"  {'─' * 94}")
            print(f"  {'Net credit (open)':30} {'$' + f'{credit:.2f}':>14}  {'':>14}  {'SPY open':>10}  ~{spy_entry_str}")
            print(f"  {'Net spread (close)':30} {spread_close_str:>14}  {'':>14}  {'SPY close':>10}  ~{spy_expiry_str}")
            print(f"  {'─' * 94}")
            print(f"  P&L: ${pnl_sign}{pnl:.0f} / contract   |   Max profit: ${credit * 100:.0f}   "
                  f"|   Max risk: ${max_loss:.0f}   |   R:R = 1:{max_loss / (credit * 100):.1f}   "
                  f"|   {result_str}")

        # Monthly summary
        print()
        print(f"  {'━' * 94}")
        print(f"  MONTHLY SUMMARY")
        print(f"  {'━' * 94}")

        for outcome in ["FULL_WIN", "PARTIAL_WIN", "PUSH", "PARTIAL_LOSS", "MAX_LOSS"]:
            odf = mdf[mdf["result"] == outcome]
            if not odf.empty:
                avg_pnl = odf["pnl_per_contract"].mean()
                total = odf["pnl_per_contract"].sum()
                avg_credit = odf["credit"].mean() * 100
                print(f"  {outcome:<16} {len(odf):>3} trades  |  "
                      f"Total P&L: ${total:>8,.0f}  |  "
                      f"Avg: ${avg_pnl:>7,.0f}/trade  |  "
                      f"Avg credit: ${avg_credit:>6,.0f}")

        avg_rr = mdf["max_loss"].mean() / (mdf["credit"].mean() * 100)
        print(f"\n  Avg risk:reward = 1:{avg_rr:.2f}")
        if total_risk > 0:
            print(f"  Return on risk = {total_pnl / total_risk * 100:.1f}%")
        print()


def main():
    parser = argparse.ArgumentParser(description="Monthly trade report")
    parser.add_argument("--month", help="Filter to single month (YYYY-MM)")
    args = parser.parse_args()
    build_report(args.month)


if __name__ == "__main__":
    main()
