#!/usr/bin/env python3
"""
Sector correlation analysis for options trading bot watchlist.
Fetches historical data via yfinance, computes pairwise correlations,
and identifies redundant vs diversified signals.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os

# ── Ticker Groups ──────────────────────────────────────────────────────────
SECTORS = {
    "Market Indexes":       ["SPY", "QQQ"],
    "Mega-Cap Tech":        ["AAPL", "MSFT", "GOOGL", "META", "AMZN"],
    "Semiconductors":       ["NVDA", "AMD", "AVGO"],
    "Fintech/Crypto":       ["MSTR", "COIN", "HOOD", "MARA"],
    "Consumer/Retail":      ["TSLA", "UBER", "LULU", "CMG"],
    "Healthcare/Biotech":   ["TMO", "REGN", "VRTX"],
    "Industrials/Energy":   ["GE", "CAT", "XOM"],
    "Growth/Tech":          ["PLTR", "PANW", "SNOW"],
    "Semiconductors Extended": ["QCOM", "MU", "INTC"],
}

ALL_TICKERS = []
for tickers in SECTORS.values():
    ALL_TICKERS.extend(tickers)

# ── Fetch Data ─────────────────────────────────────────────────────────────
print("Fetching historical data...")
end_date = datetime.now()
start_date = end_date - timedelta(days=365 * 2)  # 2 years of daily data

try:
    df = yf.download(ALL_TICKERS, start=start_date, end=end_date, progress=False, auto_adjust=True)
    # Handle single-ticker vs multi-ticker column structure
    if isinstance(df.columns, pd.MultiIndex):
        prices = df['Close'].dropna(axis=1, how='all')
    else:
        prices = df[['Close']].dropna(axis=1, how='all') if 'Close' in df.columns else df.dropna(axis=1, how='all')
    print(f"  Downloaded {len(prices)} trading days for {prices.shape[1]} tickers")
except Exception as e:
    print(f"  yfinance error: {e}")
    # Fallback: try with fewer tickers
    print("  Retrying with batched downloads...")
    frames = {}
    for sector, tickers in SECTORS.items():
        for t in tickers:
            try:
                tmp = yf.download(t, start=start_date, end=end_date, progress=False, auto_adjust=True)
                if isinstance(tmp.columns, pd.MultiIndex):
                    frames[t] = tmp['Close']
                else:
                    frames[t] = tmp['Close'] if 'Close' in tmp.columns else tmp.iloc[:, 0]
            except Exception as e2:
                print(f"  Failed to download {t}: {e2}")
    prices = pd.DataFrame(frames).dropna(axis=1, how='all')
    print(f"  Batched download: {len(prices)} trading days for {prices.shape[1]} tickers")

# ── Compute Returns ────────────────────────────────────────────────────────
daily_returns = prices.pct_change().dropna()

# ── Compute Full Correlation Matrix ────────────────────────────────────────
corr_matrix = daily_returns.corr()

# ── Helper Functions ───────────────────────────────────────────────────────
def get_sector(ticker):
    for sector, tickers in SECTORS.items():
        if ticker in tickers:
            return sector
    return "Unknown"

def analyze_within_sector():
    """Find high and low correlations within each sector."""
    results = {}
    for sector, tickers in SECTORS.items():
        if len(tickers) < 2:
            continue
        sub = corr_matrix.loc[tickers, tickers]
        pairs = []
        for i, t1 in enumerate(tickers):
            for j, t2 in enumerate(tickers):
                if i < j:
                    r = sub.loc[t1, t2]
                    pairs.append((t1, t2, r))
        
        high_corr = [(t1, t2, r) for t1, t2, r in pairs if r > 0.80]
        low_corr = [(t1, t2, r) for t1, t2, r in pairs if r < 0.50]
        avg_corr = np.mean([r for _, _, r in pairs])
        
        # For each ticker, find max correlation with others in sector
        ticker_max_corr = {}
        for t in tickers:
            others = [r for t1, t2, r in pairs if t1 == t or t2 == t]
            ticker_max_corr[t] = max(others) if others else 0
        
        results[sector] = {
            "pairs": sorted(pairs, key=lambda x: -x[2]),
            "high_corr": sorted(high_corr, key=lambda x: -x[2]),
            "low_corr": sorted(low_corr, key=lambda x: x[2]),
            "avg_corr": avg_corr,
            "ticker_max_corr": ticker_max_corr,
        }
    return results

def find_unique_signals():
    """Find tickers with <0.50 correlation to ALL other tickers."""
    unique = {}
    for ticker in ALL_TICKERS:
        others = [t for t in ALL_TICKERS if t != ticker]
        corrs = corr_matrix.loc[ticker, others]
        max_corr = corrs.max()
        min_corr = corrs.min()
        avg_corr = corrs.mean()
        if max_corr < 0.50:
            unique[ticker] = {
                "max_corr_to_any": max_corr,
                "min_corr_to_any": min_corr,
                "avg_corr": avg_corr,
                "most_correlated": corrs.idxmax(),
                "least_correlated": corrs.idxmin(),
            }
    return unique

def analyze_cross_sector():
    """Compute average correlations between sectors."""
    sector_means = {}
    sector_tickers = {s: t for s, t in SECTORS.items()}
    for s1 in SECTORS:
        for s2 in SECTORS:
            if s1 >= s2:
                continue
            cross = corr_matrix.loc[sector_tickers[s1], sector_tickers[s2]].values
            avg = np.mean(cross)
            max_pair = None
            max_val = -999
            for t1 in sector_tickers[s1]:
                for t2 in sector_tickers[s2]:
                    if corr_matrix.loc[t1, t2] > max_val:
                        max_val = corr_matrix.loc[t1, t2]
                        max_pair = (t1, t2)
            sector_means[(s1, s2)] = {
                "avg_corr": avg,
                "max_pair": max_pair,
                "max_corr": max_val,
            }
    return sector_means

def analyze_extended_semi_merge():
    """Analyze whether Semiconductors and Semiconductors Extended should merge."""
    semi = ["NVDA", "AMD", "AVGO"]
    semi_ext = ["QCOM", "MU", "INTC"]
    
    # Within-group correlations
    within_semi = [corr_matrix.loc[t1, t2] for i, t1 in enumerate(semi) for j, t2 in enumerate(semi) if i < j]
    within_ext = [corr_matrix.loc[t1, t2] for i, t1 in enumerate(semi_ext) for j, t2 in enumerate(semi_ext) if i < j]
    
    # Cross-group correlations
    cross = [corr_matrix.loc[t1, t2] for t1 in semi for t2 in semi_ext]
    
    return {
        "within_semi_avg": np.mean(within_semi),
        "within_ext_avg": np.mean(within_ext),
        "cross_avg": np.mean(cross),
        "cross_matrix": {t1: {t2: float(corr_matrix.loc[t1, t2]) for t2 in semi_ext} for t1 in semi},
    }

# ── Run Analyses ───────────────────────────────────────────────────────────
print("\nRunning analyses...")
within_sector = analyze_within_sector()
unique_signals = find_unique_signals()
cross_sector = analyze_cross_sector()
semi_merge = analyze_extended_semi_merge()

# ── Print Summary ──────────────────────────────────────────────────────────
print("\n" + "="*80)
print("WITHIN-SECTOR CORRELATIONS")
print("="*80)
for sector, data in within_sector.items():
    print(f"\n--- {sector} (avg pairwise corr: {data['avg_corr']:.3f}) ---")
    for t1, t2, r in data['pairs']:
        flag = " *** HIGH" if r > 0.80 else (" *** LOW" if r < 0.50 else "")
        print(f"  {t1} <-> {t2}: {r:.3f}{flag}")

print("\n" + "="*80)
print("UNIQUE SIGNALS (<0.50 max correlation to any other ticker)")
print("="*80)
if unique_signals:
    for t, d in unique_signals.items():
        print(f"  {t}: max_corr={d['max_corr_to_any']:.3f} (with {d['most_correlated']})")
else:
    print("  None found — all tickers correlate >0.50 with at least one other ticker.")
    # Show the least correlated tickers
    min_corrs = []
    for ticker in ALL_TICKERS:
        others = [t for t in ALL_TICKERS if t != ticker]
        c = corr_matrix.loc[ticker, others].max()
        min_corrs.append((ticker, c))
    min_corrs.sort(key=lambda x: x[1])
    print("\n  Least correlated tickers (by max correlation to any other):")
    for t, c in min_corrs[:5]:
        others = [tt for tt in ALL_TICKERS if tt != t]
        best_match = corr_matrix.loc[t, others].idxmax()
        print(f"    {t}: max_corr={c:.3f} (most correlated with {best_match})")

print("\n" + "="*80)
print("CROSS-SECTOR CORRELATIONS (top 15)")
print("="*80)
sorted_cross = sorted(cross_sector.items(), key=lambda x: -x[1]['avg_corr'])
for (s1, s2), data in sorted_cross[:15]:
    print(f"  {s1} <-> {s2}: avg={data['avg_corr']:.3f}, max_pair={data['max_pair']} ({data['max_corr']:.3f})")

print("\n" + "="*80)
print("SEMICONDUCTOR MERGE ANALYSIS")
print("="*80)
print(f"  Within Semiconductors avg: {semi_merge['within_semi_avg']:.3f}")
print(f"  Within Semi Extended avg: {semi_merge['within_ext_avg']:.3f}")
print(f"  Cross-group avg:          {semi_merge['cross_avg']:.3f}")
print(f"\n  Cross-correlation matrix:")
for t1, row in semi_merge['cross_matrix'].items():
    for t2, v in row.items():
        flag = " *** HIGH" if v > 0.80 else ""
        print(f"    {t1} <-> {t2}: {v:.3f}{flag}")

# ── Save Full Correlation Matrix as CSV ────────────────────────────────────
csv_path = "/Users/arivera/projects/tos_options/buckets/correlation_matrix.csv"
corr_matrix.to_csv(csv_path)
print(f"\nCorrelation matrix saved to: {csv_path}")

# ── Save Results as JSON for the report generator ──────────────────────────
results = {
    "date_range": [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")],
    "num_trading_days": len(daily_returns),
    "tickers_analyzed": prices.shape[1],
    "within_sector": {},
    "unique_signals": unique_signals,
    "cross_sector": {},
    "semi_merge": semi_merge,
    "least_correlated": [],
    "full_corr_matrix": corr_matrix.round(3).to_dict(),
}

for sector, data in within_sector.items():
    results["within_sector"][sector] = {
        "pairs": [(t1, t2, round(float(r), 3)) for t1, t2, r in data['pairs']],
        "high_corr": [(t1, t2, round(float(r), 3)) for t1, t2, r in data['high_corr']],
        "low_corr": [(t1, t2, round(float(r), 3)) for t1, t2, r in data['low_corr']],
        "avg_corr": round(float(data['avg_corr']), 3),
        "ticker_max_corr": {t: round(float(v), 3) for t, v in data['ticker_max_corr'].items()},
    }

for (s1, s2), data in cross_sector.items():
    key = f"{s1} | {s2}"
    results["cross_sector"][key] = {
        "avg_corr": round(float(data['avg_corr']), 3),
        "max_pair": list(data['max_pair']),
        "max_corr": round(float(data['max_corr']), 3),
    }

# Least correlated tickers for the report
for ticker in ALL_TICKERS:
    others = [t for t in ALL_TICKERS if t != ticker]
    corrs = corr_matrix.loc[ticker, others]
    results["least_correlated"].append({
        "ticker": ticker,
        "max_corr_to_any": round(float(corrs.max()), 3),
        "most_correlated_with": corrs.idxmax(),
    })
results["least_correlated"].sort(key=lambda x: x['max_corr_to_any'])

json_path = "/Users/arivera/projects/tos_options/buckets/correlation_results.json"
with open(json_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f"Results JSON saved to: {json_path}")

print("\nDone.")
