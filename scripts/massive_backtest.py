#!/usr/bin/env python3
"""
Calendar Spread Backtest using Massive API (Polygon.io)

Uses the Price/sqrt(DTE) ratio method to identify calendar spread opportunities.
The ratio compares front-month vs back-month option prices adjusted for time.

Signal: front_price / sqrt(front_DTE) > back_price / sqrt(back_DTE) * 1.10
"""

import requests
from datetime import datetime, timedelta
import json

# API Configuration
API_KEY = "eAOickvOvgp6jaSFQ9TNpiMdHqP6tVbt"
BASE_URL = "https://api.massive.com"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}

# Backtest Configuration
RATIO_THRESHOLD = 1.10  # Front must be 10% more expensive relative to time
PROFIT_TARGET = 0.50  # 50% profit target
STOP_LOSS = 0.50  # 50% stop loss
MIN_DTE_FRONT = 3  # Minimum front month DTE
MIN_DTE_BACK = 14  # Minimum back month DTE


def get_daily_summary(ticker: str, date: str) -> dict | None:
    """Fetch daily OHLCV summary for an options ticker"""
    url = f"{BASE_URL}/v1/open-close/{ticker}/{date}"
    response = requests.get(url, headers=HEADERS, timeout=30)
    if response.status_code == 200:
        return response.json()
    return None


def get_spy_price(date: str) -> float | None:
    """Get SPY closing price for a date"""
    url = f"{BASE_URL}/v2/aggs/ticker/SPY/range/1/day/{date}/{date}"
    response = requests.get(url, headers=HEADERS, timeout=30)
    if response.status_code == 200:
        bars = response.json().get("results", [])
        if bars:
            return bars[0]["c"]
    return None


def make_ticker(symbol: str, date_str: str, strike: float, option_type: str) -> str:
    """Make options ticker: O:SPY251205C00685000"""
    exp = datetime.strptime(date_str, "%Y-%m-%d")
    exp_code = exp.strftime("%y%m%d")
    strike_int = int(strike)
    return f"O:{symbol}{exp_code}{option_type.upper()}{strike_int:05d}000"


def calc_dte(from_date: str, to_exp: str) -> int:
    """Calculate DTE from entry date to expiration"""
    exp = datetime.strptime(to_exp, "%Y-%m-%d")
    entry = datetime.strptime(from_date, "%Y-%m-%d")
    return max(1, (exp - entry).days)


def run_backtest(
    symbols: list[str] = ["SPY"],
    start_date: str = "2025-12-01",
    end_date: str = "2025-12-31",
    calendar_pairs: list[tuple[str, str]] = None,
) -> dict:
    """
    Run calendar spread backtest using Massive API.

    Args:
        symbols: List of underlying symbols to test
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        calendar_pairs: List of (front_exp, back_exp) tuples

    Returns:
        dict with backtest results
    """
    if calendar_pairs is None:
        calendar_pairs = [
            ("2025-12-05", "2025-12-31"),
            ("2025-12-12", "2025-12-31"),
            ("2025-12-19", "2026-01-16"),
            ("2025-12-31", "2026-01-30"),
        ]

    # Generate trading dates
    dates = []
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    results = {"trades": [], "signals": [], "summary": {}}

    for symbol in symbols:
        print(f"\n{'=' * 70}")
        print(f"BACKTEST: {symbol}")
        print(f"Period: {start_date} to {end_date}")
        print(f"{'=' * 70}")

        for front_exp, back_exp in calendar_pairs:
            position_open = False
            entry = {}

            print(f"\n{front_exp} → {back_exp}")
            print(
                f"{'DATE':<12} {'SPY':>8} {'F_PRICE':>8} {'B_PRICE':>10} {'RATIO_DIFF':>10} {'ACTION'}"
            )
            print("-" * 80)

            for date in dates:
                spy = get_spy_price(date)
                if not spy:
                    continue

                strike = round(spy / 5) * 5
                front_ticker = make_ticker(symbol, front_exp, strike, "C")
                back_ticker = make_ticker(symbol, back_exp, strike, "C")

                front_data = get_daily_summary(front_ticker, date)
                back_data = get_daily_summary(back_ticker, date)

                if not (
                    front_data
                    and back_data
                    and front_data.get("close")
                    and back_data.get("close")
                ):
                    continue

                front_close = front_data["close"]
                back_close = back_data["close"]

                dte_front = calc_dte(date, front_exp)
                dte_back = calc_dte(date, back_exp)

                # Skip if DTEs too low
                if dte_front < MIN_DTE_FRONT or dte_back < MIN_DTE_BACK:
                    continue

                # Calculate ratios
                front_ratio = front_close / (dte_front**0.5)
                back_ratio = back_close / (dte_back**0.5)
                ratio = front_ratio / back_ratio if back_ratio > 0 else 0
                ratio_diff = (ratio - 1) * 100

                action = ""

                # Entry: ratio > threshold
                if not position_open and ratio > RATIO_THRESHOLD:
                    position_open = True
                    entry = {
                        "date": date,
                        "spy": spy,
                        "strike": strike,
                        "front_price": front_close,
                        "back_price": back_close,
                        "net_credit": front_close - back_close,
                        "front_ratio": front_ratio,
                        "back_ratio": back_ratio,
                        "dte_front": dte_front,
                        "dte_back": dte_back,
                    }
                    action = ">>> OPEN"
                    results["signals"].append(
                        {
                            "symbol": symbol,
                            "date": date,
                            "front_exp": front_exp,
                            "back_exp": back_exp,
                            "strike": strike,
                            "ratio_diff": ratio_diff,
                        }
                    )

                # Monitor/Exit
                elif position_open:
                    net = front_close - back_close
                    pnl = entry["net_credit"] - net
                    pnl_pct = (
                        (pnl / abs(entry["net_credit"])) * 100
                        if entry["net_credit"] != 0
                        else 0
                    )

                    # Exit conditions
                    if pnl_pct >= PROFIT_TARGET * 100:
                        action = f">>> CLOSE (Profit {pnl_pct:+.1f}%)"
                        results["trades"].append(
                            {
                                "symbol": symbol,
                                "entry_date": entry["date"],
                                "exit_date": date,
                                "front_exp": front_exp,
                                "back_exp": back_exp,
                                "strike": entry["strike"],
                                "entry_net": entry["net_credit"],
                                "exit_net": net,
                                "pnl": pnl,
                                "pnl_pct": pnl_pct,
                                "exit_reason": "PROFIT_TARGET",
                            }
                        )
                        position_open = False
                    elif pnl_pct <= -STOP_LOSS * 100:
                        action = f">>> CLOSE (Loss {pnl_pct:+.1f}%)"
                        results["trades"].append(
                            {
                                "symbol": symbol,
                                "entry_date": entry["date"],
                                "exit_date": date,
                                "front_exp": front_exp,
                                "back_exp": back_exp,
                                "strike": entry["strike"],
                                "entry_net": entry["net_credit"],
                                "exit_net": net,
                                "pnl": pnl,
                                "pnl_pct": pnl_pct,
                                "exit_reason": "STOP_LOSS",
                            }
                        )
                        position_open = False
                    elif dte_front <= 2:
                        action = f">>> CLOSE (Near Expiry)"
                        results["trades"].append(
                            {
                                "symbol": symbol,
                                "entry_date": entry["date"],
                                "exit_date": date,
                                "front_exp": front_exp,
                                "back_exp": back_exp,
                                "strike": entry["strike"],
                                "entry_net": entry["net_credit"],
                                "exit_net": net,
                                "pnl": pnl,
                                "pnl_pct": pnl_pct,
                                "exit_reason": "NEAR_EXPIRY",
                            }
                        )
                        position_open = False
                    else:
                        action = f"HOLD ({pnl_pct:+.1f}%)"

                if action or ratio > 1.0:
                    marker = "✓" if ratio > RATIO_THRESHOLD else ""
                    print(
                        f"{date:<12} ${spy:>7.2f} ${front_close:>7.2f} ${back_close:>9.2f} {ratio_diff:>+9.1f}% {action} {marker}"
                    )

    # Calculate summary
    trades = results["trades"]
    results["summary"] = {
        "total_trades": len(trades),
        "wins": sum(1 for t in trades if t["pnl"] > 0),
        "losses": sum(1 for t in trades if t["pnl"] <= 0),
        "total_pnl": sum(t["pnl"] for t in trades),
        "avg_pnl": sum(t["pnl"] for t in trades) / len(trades) if trades else 0,
        "signals": len(results["signals"]),
    }

    return results


def print_summary(results: dict):
    """Print backtest summary"""
    summary = results["summary"]

    print("\n" + "=" * 70)
    print("BACKTEST SUMMARY")
    print("=" * 70)

    print(f"\nSignals Generated: {summary['signals']}")
    print(f"Trades Executed: {summary['total_trades']}")
    print(f"Wins: {summary['wins']}")
    print(f"Losses: {summary['losses']}")

    if summary["total_trades"] > 0:
        win_rate = summary["wins"] / summary["total_trades"] * 100
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Total P&L: ${summary['total_pnl']:.2f}")
        print(f"Average P&L: ${summary['avg_pnl']:.2f}")

    print("\nTrade Details:")
    for trade in results["trades"]:
        print(
            f"  {trade['entry_date']} → {trade['exit_date']}: "
            f"${trade['pnl']:+.2f} ({trade['pnl_pct']:+.1f}%) "
            f"[{trade['exit_reason']}]"
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Calendar Spread Backtest using Massive API"
    )
    parser.add_argument("--start", default="2025-12-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2025-12-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--symbol", default="SPY", help="Symbol to test")
    parser.add_argument("--output", help="Output JSON file")

    args = parser.parse_args()

    results = run_backtest(
        symbols=[args.symbol], start_date=args.start, end_date=args.end
    )

    print_summary(results)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")
