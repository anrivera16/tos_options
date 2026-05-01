#!/usr/bin/env python3
"""
Premium Decay Visualizer
Plots how option mark prices decay throughout the trading day.
"""

import subprocess
import sys
import os
from pathlib import Path

# Ensure matplotlib backend works headless in Docker
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

def run_query(query):
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "db", "psql", "-U", "trader", "-d", "options", "-c", query],
        capture_output=True, text=True, check=True
    )
    return result.stdout

def query_decay_data(symbol, strike, put_call, dte):
    """Get mark price at each snapshot throughout the day for a specific contract."""
    q = f"""
    SELECT 
        s.captured_at AS ts,
        oc.mark,
        oc.bid,
        oc.ask,
        oc.delta,
        oc.theta,
        oc.volatility,
        s.underlying_price AS spot
    FROM option_contracts oc
    JOIN snapshots s ON oc.snapshot_id = s.id
    WHERE oc.symbol LIKE '{symbol}%'
      AND oc.strike = {strike}
      AND oc.put_call = '{put_call}'
      AND oc.dte = {dte}
      AND s.captured_at >= '2026-04-21'
    ORDER BY s.captured_at;
    """
    raw = run_query(q)
    rows = []
    for line in raw.strip().split("\n"):
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 8 and parts[0] and parts[0][:4] == "2026":
            try:
                rows.append({
                    "ts": parts[0],
                    "mark": float(parts[1]) if parts[1] else None,
                    "bid": float(parts[2]) if parts[2] else None,
                    "ask": float(parts[3]) if parts[3] else None,
                    "delta": float(parts[4]) if parts[4] else None,
                    "theta": float(parts[5]) if parts[5] else None,
                    "volatility": float(parts[6]) if parts[6] else None,
                    "spot": float(parts[7]) if parts[7] else None,
                })
            except (ValueError, IndexError):
                continue
    return rows

def plot_premium_decay():
    """Main visualization."""
    from datetime import datetime

    # ── Contracts to plot: SPY puts near the money, different DTEs ──
    # Spot was ~706.80, so 700-706 puts are OTM (bull put spread territory)
    contracts = [
        {"symbol": "SPY", "strike": 703, "put_call": "PUT", "dte": 0,  "color": "#e74c3c", "label": "703P 0DTE"},
        {"symbol": "SPY", "strike": 705, "put_call": "PUT", "dte": 0,  "color": "#e67e22", "label": "705P 0DTE"},
        {"symbol": "SPY", "strike": 703, "put_call": "PUT", "dte": 1,  "color": "#3498db", "label": "703P 1DTE"},
        {"symbol": "SPY", "strike": 705, "put_call": "PUT", "dte": 1,  "color": "#2ecc71", "label": "705P 1DTE"},
        {"symbol": "SPY", "strike": 703, "put_call": "PUT", "dte": 7,  "color": "#9b59b6", "label": "703P 7DTE"},
        {"symbol": "SPY", "strike": 705, "put_call": "PUT", "dte": 7,  "color": "#1abc9c", "label": "705P 7DTE"},
    ]

    # Collect data
    all_data = {}
    for c in contracts:
        rows = query_decay_data(c["symbol"], c["strike"], c["put_call"], c["dte"])
        all_data[c["label"]] = {"rows": rows, "color": c["color"]}
        print(f"  {c['label']}: {len(rows)} data points")

    # ── Create figure with 2 subplots ──
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={"height_ratios": [3, 1]})
    fig.suptitle("SPY Put Premium Decay — April 21, 2026", fontsize=16, fontweight="bold", y=0.98)

    # ── Plot 1: Mark Price over time ──
    for label, data in all_data.items():
        rows = data["rows"]
        if not rows:
            continue
        times = [datetime.strptime(r["ts"][:19], "%Y-%m-%d %H:%M:%S") for r in rows if r["mark"]]
        marks = [r["mark"] for r in rows if r["mark"]]
        if times:
            ax1.plot(times, marks, color=data["color"], linewidth=2, label=label, alpha=0.9)

    ax1.set_ylabel("Mark Price ($)", fontsize=12)
    ax1.set_title("Mark Price Throughout Day", fontsize=13)
    ax1.legend(loc="upper right", fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax1.set_xlabel("")

    # ── Plot 2: Spot price ──
    # Use the first contract's spot as reference
    for label, data in all_data.items():
        rows = data["rows"]
        if rows:
            times = [datetime.strptime(r["ts"][:19], "%Y-%m-%d %H:%M:%S") for r in rows if r["spot"]]
            spots = [r["spot"] for r in rows if r["spot"]]
            if times:
                ax2.plot(times, spots, color="#2c3e50", linewidth=2, label="SPY Spot")
                # Draw strike reference lines
                ax2.axhline(y=703, color="#3498db", linestyle="--", alpha=0.5, linewidth=1, label="703 strike")
                ax2.axhline(y=705, color="#e74c3c", linestyle="--", alpha=0.5, linewidth=1, label="705 strike")
            break

    ax2.set_ylabel("SPY Price ($)", fontsize=12)
    ax2.set_title("Underlying Price", fontsize=13)
    ax2.legend(loc="upper right", fontsize=10)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax2.set_xlabel("Time (ET)", fontsize=12)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    
    out_path = Path(__file__).parent.parent / "out" / "premium_decay_apr21.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    print(f"\nSaved to: {out_path}")
    
    # Also save a CSV with the raw data
    csv_path = out_path.with_suffix(".csv")
    with open(csv_path, "w") as f:
        f.write("time,contract,mark,bid,ask,delta,theta,iv,spot\n")
        for label, data in all_data.items():
            for r in data["rows"]:
                if r["mark"]:
                    f.write(f'{r["ts"]},{label},{r["mark"]},{r["bid"]},{r["ask"]},'
                            f'{r["delta"]},{r["theta"]},{r["volatility"]},{r["spot"]}\n')
    print(f"CSV saved to: {csv_path}")

    # ── Print summary ──
    print("\n" + "=" * 70)
    print("PREMIUM DECAY SUMMARY — SPY Puts, April 21, 2026")
    print("=" * 70)
    print(f"{'Contract':<15} {'Open':>8} {'Close':>8} {'Decay':>8} {'Decay%':>8} {'Theta':>8}")
    print("-" * 70)
    for label, data in all_data.items():
        rows = data["rows"]
        if not rows:
            continue
        marks = [r["mark"] for r in rows if r["mark"]]
        thetas = [r["theta"] for r in rows if r["theta"]]
        if marks and len(marks) > 1:
            open_price = marks[0]
            close_price = marks[-1]
            decay = open_price - close_price
            decay_pct = (decay / open_price * 100) if open_price > 0 else 0
            avg_theta = sum(thetas) / len(thetas) if thetas else 0
            print(f"{label:<15} {open_price:>8.2f} {close_price:>8.2f} {decay:>8.2f} {decay_pct:>7.1f}% {avg_theta:>8.3f}")

if __name__ == "__main__":
    plot_premium_decay()
