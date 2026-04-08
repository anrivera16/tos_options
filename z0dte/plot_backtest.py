"""
Plot volatility surface backtest results
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# Load backtest data
df_calendar = pd.read_csv('backtest_calendar_spread.csv')
df_butterfly = pd.read_csv('backtest_butterfly.csv')
df_straddle = pd.read_csv('backtest_straddle.csv')
df_0dte = pd.read_csv('backtest_0dte.csv')

# Convert timestamps
for df in [df_calendar, df_butterfly, df_straddle, df_0dte]:
    df['timestamp'] = pd.to_datetime(df['timestamp'])

# Create figure with 4 subplots
fig, axes = plt.subplots(2, 2, figsize=(16, 10))
fig.suptitle('Volatility Surface Trading Strategies - April 8, 2026', fontsize=16, fontweight='bold')

# Plot 1: Calendar Spread P&L
ax = axes[0, 0]
ax.plot(df_calendar['timestamp'], df_calendar['pnl'], 'b-o', linewidth=2, markersize=6, label='P&L')
ax.axhline(y=0, color='k', linestyle='--', alpha=0.3)
ax.fill_between(df_calendar['timestamp'], 0, df_calendar['pnl'], alpha=0.3)
ax.set_title('Calendar Spread: Sell 30DTE / Buy 60DTE\n(Entry Cost: $54.72)', fontweight='bold')
ax.set_ylabel('P&L ($)', fontweight='bold')
ax.grid(True, alpha=0.3)
ax.legend()
ax2 = ax.twinx()
ax2.plot(df_calendar['timestamp'], df_calendar['spot'], 'r--', linewidth=1.5, alpha=0.7, label='SPX')
ax2.set_ylabel('Spot Price (SPX)', color='r', fontweight='bold')
ax2.tick_params(axis='y', labelcolor='r')

# Plot 2: Butterfly P&L
ax = axes[0, 1]
ax.plot(df_butterfly['timestamp'], df_butterfly['pnl'], 'g-o', linewidth=2, markersize=6, label='P&L')
ax.axhline(y=0, color='k', linestyle='--', alpha=0.3)
ax.fill_between(df_butterfly['timestamp'], 0, df_butterfly['pnl'], alpha=0.3, color='green')
ax.set_title('Butterfly: Buy 5430 / Sell 2x5460 / Sell 5490\n(Entry Credit: $180.91)', fontweight='bold')
ax.set_ylabel('P&L ($)', fontweight='bold')
ax.grid(True, alpha=0.3)
ax.legend()
ax2 = ax.twinx()
ax2.plot(df_butterfly['timestamp'], df_butterfly['spot'], 'r--', linewidth=1.5, alpha=0.7, label='SPX')
ax2.set_ylabel('Spot Price (SPX)', color='r', fontweight='bold')
ax2.tick_params(axis='y', labelcolor='r')

# Plot 3: Straddle P&L
ax = axes[1, 0]
ax.plot(df_straddle['timestamp'], df_straddle['pnl'], 'purple', marker='o', linewidth=2, markersize=6, label='P&L')
ax.axhline(y=0, color='k', linestyle='--', alpha=0.3)
ax.fill_between(df_straddle['timestamp'], 0, df_straddle['pnl'], alpha=0.3, color='purple')
ax.set_title('Long Straddle: Buy 5430 Call + Put\n(Entry Cost: $216.31)', fontweight='bold')
ax.set_ylabel('P&L ($)', fontweight='bold')
ax.set_xlabel('Time', fontweight='bold')
ax.grid(True, alpha=0.3)
ax.legend()
ax2 = ax.twinx()
ax2.plot(df_straddle['timestamp'], df_straddle['spot'], 'r--', linewidth=1.5, alpha=0.7, label='SPX')
ax2.set_ylabel('Spot Price (SPX)', color='r', fontweight='bold')
ax2.tick_params(axis='y', labelcolor='r')

# Plot 4: 0DTE P&L
ax = axes[1, 1]
ax.plot(df_0dte['timestamp'], df_0dte['pnl'], 'orange', marker='o', linewidth=2, markersize=6, label='P&L')
ax.axhline(y=0, color='k', linestyle='--', alpha=0.3)
ax.fill_between(df_0dte['timestamp'], 0, df_0dte['pnl'], alpha=0.3, color='orange')
ax.set_title('Short 0DTE Straddle: Theta Harvest\n(Entry Credit: $36.54)', fontweight='bold')
ax.set_ylabel('P&L ($)', fontweight='bold')
ax.set_xlabel('Time', fontweight='bold')
ax.grid(True, alpha=0.3)
ax.legend()
ax2 = ax.twinx()
ax2.plot(df_0dte['timestamp'], df_0dte['spot'], 'r--', linewidth=1.5, alpha=0.7, label='SPX')
ax2.set_ylabel('Spot Price (SPX)', color='r', fontweight='bold')
ax2.tick_params(axis='y', labelcolor='r')

# Format all x-axes
for ax in axes.flat:
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.tick_params(axis='x', rotation=45)

plt.tight_layout()
plt.savefig('/Users/arivera/projects/tos_options/outputs/backtest_visualization.png', dpi=150, bbox_inches='tight')
print("✓ Saved backtest_visualization.png")

# Create a second figure with Greeks evolution
fig, axes = plt.subplots(2, 2, figsize=(16, 10))
fig.suptitle('Greeks Evolution During Trades', fontsize=16, fontweight='bold')

# Plot Delta evolution
ax = axes[0, 0]
ax.plot(df_calendar['timestamp'], df_calendar['delta'], label='Calendar Spread', linewidth=2)
ax.plot(df_butterfly['timestamp'], df_butterfly['delta'], label='Butterfly', linewidth=2)
ax.plot(df_straddle['timestamp'], df_straddle['delta'], label='Straddle', linewidth=2)
ax.plot(df_0dte['timestamp'], df_0dte['delta'], label='0DTE', linewidth=2)
ax.axhline(y=0, color='k', linestyle='--', alpha=0.3)
ax.set_title('Delta (Directional Exposure)', fontweight='bold')
ax.set_ylabel('Delta', fontweight='bold')
ax.legend()
ax.grid(True, alpha=0.3)

# Plot Gamma evolution
ax = axes[0, 1]
ax.plot(df_calendar['timestamp'], df_calendar['gamma'], label='Calendar Spread', linewidth=2)
ax.plot(df_butterfly['timestamp'], df_butterfly['gamma'], label='Butterfly', linewidth=2)
ax.plot(df_straddle['timestamp'], df_straddle['gamma'], label='Straddle', linewidth=2)
ax.axhline(y=0, color='k', linestyle='--', alpha=0.3)
ax.set_title('Gamma (Spot Move P&L)', fontweight='bold')
ax.set_ylabel('Gamma', fontweight='bold')
ax.legend()
ax.grid(True, alpha=0.3)

# Plot Theta evolution
ax = axes[1, 0]
ax.plot(df_calendar['timestamp'], df_calendar['theta'], label='Calendar Spread', linewidth=2)
ax.plot(df_butterfly['timestamp'], df_butterfly['theta'], label='Butterfly', linewidth=2)
ax.plot(df_straddle['timestamp'], df_straddle['theta'], label='Straddle', linewidth=2)
ax.plot(df_0dte['timestamp'], df_0dte['theta'], label='0DTE', linewidth=2)
ax.axhline(y=0, color='k', linestyle='--', alpha=0.3)
ax.set_title('Theta (Time Decay/Hour)', fontweight='bold')
ax.set_ylabel('Theta ($/day)', fontweight='bold')
ax.set_xlabel('Time', fontweight='bold')
ax.legend()
ax.grid(True, alpha=0.3)

# Plot Vega evolution
ax = axes[1, 1]
ax.plot(df_calendar['timestamp'], df_calendar['vega'], label='Calendar Spread', linewidth=2)
ax.plot(df_butterfly['timestamp'], df_butterfly['vega'], label='Butterfly', linewidth=2)
ax.plot(df_straddle['timestamp'], df_straddle['vega'], label='Straddle', linewidth=2)
ax.axhline(y=0, color='k', linestyle='--', alpha=0.3)
ax.set_title('Vega (Vol Sensitivity)', fontweight='bold')
ax.set_ylabel('Vega ($/1% IV)', fontweight='bold')
ax.set_xlabel('Time', fontweight='bold')
ax.legend()
ax.grid(True, alpha=0.3)

# Format x-axes
for ax in axes.flat:
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.tick_params(axis='x', rotation=45)

plt.tight_layout()
plt.savefig('/Users/arivera/projects/tos_options/outputs/greeks_evolution.png', dpi=150, bbox_inches='tight')
print("✓ Saved greeks_evolution.png")

print("\nVisualization complete!")
print("\nTo view:")
print("  open /Users/arivera/projects/tos_options/outputs/backtest_visualization.png")
print("  open /Users/arivera/projects/tos_options/outputs/greeks_evolution.png")
