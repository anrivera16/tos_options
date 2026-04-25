"""
algo/ — Modular credit spread pipeline for SPY.

Each module is independent and composable. Enable/disable any combination
to backtest each component's contribution to the edge.

Pipeline: Generator → Trend → IV Rank → Earnings → Walls → Proximity → Scoring → Risk
"""
