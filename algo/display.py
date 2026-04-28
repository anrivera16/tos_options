"""
Console display for the algo pipeline.

Formats PipelineResult as clean terminal output showing each stage,
filter decisions, and final trade recommendations.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from algo.types import CandidateSpread, OIWall, PipelineResult

ET = ZoneInfo("US/Eastern")


def format_pipeline_report(
    result: PipelineResult,
    walls: list[OIWall] | None = None,
    trend_info: dict[str, Any] | None = None,
    iv_info: dict[str, Any] | None = None,
) -> str:
    """
    Format a full pipeline run report for the console.

    Args:
        result: PipelineResult from a single run
        walls: Detected OI walls
        trend_info: {direction, sma, price, sma_pct}
        iv_info: {current_iv, rank, historical_min, historical_max}
    """
    lines: list[str] = []
    now = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")

    # ── Header ──────────────────────────────────────────────
    lines.append("")
    lines.append(f"  CREDIT SPREAD SCANNER  {now}")
    lines.append(f"  {result.underlying} ${result.underlying_price:.2f}")
    lines.append(f"  {'─' * 58}")

    # ── Market Context ──────────────────────────────────────
    lines.append("")
    lines.append("  MARKET CONTEXT")

    if trend_info:
        d = trend_info.get("direction", "?").upper()
        icon = {"BULLISH": "▲", "BEARISH": "▼", "NEUTRAL": "◆"}.get(d, "?")
        sma = trend_info.get("sma", 0)
        pct = trend_info.get("sma_pct", 0)
        if sma:
            lines.append(f"  Trend    {icon} {d:<10s}  SMA(20) ${sma:.2f} ({pct:+.1f}%)")
        else:
            lines.append(f"  Trend    {icon} {d:<10s}  (insufficient history)")

    if iv_info:
        iv = iv_info.get("current_iv", 0)
        rank = iv_info.get("rank")
        lo = iv_info.get("historical_min", 0)
        hi = iv_info.get("historical_max", 0)
        days = iv_info.get("days", 0)
        dte = iv_info.get("dte", "?")
        rank_str = f"{rank:.0f}%" if rank is not None else "n/a"
        iv_min = iv_info.get("iv_rank_min", 30)
        iv_max = iv_info.get("iv_rank_max", 95)
        gate = "OPEN" if rank is not None and iv_min <= rank <= iv_max else "CLOSED"
        gate_icon = "●" if gate == "OPEN" else "○"
        lines.append(f"  IV Rank  {gate_icon} {rank_str:<10s}  IV {iv:.1f}% (range {lo:.1f}-{hi:.1f}%)")
        lines.append(f"  IV Gate  {gate}")
        conf = "LOW" if days < 20 else ("MED" if days < 252 else "FULL")
        lines.append(f"  IV Data  {days} days at DTE {dte}  confidence: {conf}")

    if walls:
        lines.append(f"  OI Walls {len(walls)} detected")
        for w in walls[:3]:
            icon = "━" if w.wall_type == "support" else "─"
            lines.append(
                f"    {icon} {w.wall_type:<12s} ${w.strike:.0f}  "
                f"OI={w.total_oi:>8,}  score={w.wall_score:.2f}"
            )

    # ── Pipeline Flow ───────────────────────────────────────
    lines.append("")
    lines.append("  PIPELINE")
    lines.append(f"  {'─' * 58}")

    stages = [
        ("Raw Signals  ", result.raw_candidates),
        ("Trend Filter ", result.post_trend),
        ("IV Rank Gate ", result.post_iv_rank),
        ("Earnings     ", result.post_earnings),
        ("Wall Prox.   ", result.post_proximity),
    ]
    if result.walls_detected:
        lines.append(f"  OI Walls      {result.walls_detected} detected")

    for i, (name, count) in enumerate(stages):
        prev = stages[i - 1][1] if i > 0 else count
        if i == 0:
            arrow = "→"
        elif count < prev:
            arrow = f"✗ {prev - count} rejected"
        elif count == prev:
            arrow = "= all pass"
        else:
            arrow = "→"
        lines.append(f"  {i+1}. {name}  {count:>3}  {arrow}")

    lines.append(f"  {'─' * 58}")

    ranked = result.ranked
    if ranked:
        lines.append(f"  Ranked      {len(ranked):>3}  scored & sorted")
    else:
        lines.append(f"  Final         0  no candidates survived")

    # ── Rejection Summary ───────────────────────────────────
    if result.rejected:
        lines.append("")
        lines.append("  REJECTIONS")
        by_module: dict[str, int] = {}
        for c in result.rejected:
            for reason in c.rejection_reasons:
                module = reason.split(":")[0]
                by_module[module] = by_module.get(module, 0) + 1
        for module, count in sorted(by_module.items(), key=lambda x: -x[1]):
            # Show first rejection reason for each module
            example = ""
            for c in result.rejected:
                for reason in c.rejection_reasons:
                    if reason.startswith(module + ":"):
                        example = reason.split(":", 1)[1].strip()
                        break
                if example:
                    break
            lines.append(f"  ○ {module:<12s} {count:>2} rejected  ({example})")

    # ── Top Candidates ──────────────────────────────────────
    if ranked:
        lines.append("")
        lines.append("  TOP CANDIDATES")
        lines.append(
            f"  {'#':>2}  {'Type':<8} {'Sell':>5} {'Buy':>5} "
            f"{'DTE':>3} {'Δ':>5} {'Credit':>6} {'Risk':>6} "
            f"{'ROC':>4} {'Score':>5}"
        )
        lines.append(f"  {'─' * 58}")

        for i, c in enumerate(ranked[:8]):
            stype_short = "BULL PUT" if c.spread_type == "bull_put_credit" else "BER CALL"
            delta_str = f"{abs(c.short_delta):.3f}" if c.short_delta else "  n/a"

            lines.append(
                f"  {i+1:>2}  {stype_short:<8} {c.short_strike:>5.0f} {c.long_strike:>5.0f} "
                f"{c.dte:>3} {delta_str:>5} ${c.credit:>5.2f} ${c.max_loss:>5.2f} "
                f"{c.roc_pct:>3.0f}% {c.composite_score:>5.3f}"
            )
        lines.append(f"  {'─' * 58}")

    # ── Best Trade ──────────────────────────────────────────
    best = result.best
    if best:
        lines.append("")
        stype_full = "BULL PUT CREDIT" if best.spread_type == "bull_put_credit" else "BEAR CALL CREDIT"
        lines.append(f"  ★ BEST TRADE: {stype_full}")
        lines.append(f"    Sell {best.short_strike:.0f} / Buy {best.long_strike:.0f}  "
                     f"exp {best.expiration_date[:10]}  DTE {best.dte}")
        lines.append(f"    Credit ${best.credit:.2f}  Max Loss ${best.max_loss:.2f}  "
                     f"ROC {best.roc_pct:.0f}%")
        lines.append(f"    Breakeven ${best.breakeven:.2f}  "
                     f"Distance OTM {best.distance_otm_pct:.1f}%")
        if best.short_delta:
            lines.append(f"    Short Δ {abs(best.short_delta):.3f}  "
                         f"Score {best.composite_score:.3f}")
    elif not ranked:
        lines.append("")
        lines.append("  ○ No trade signal this cycle.")

    lines.append("")
    lines.append(f"  {'─' * 58}")
    lines.append("")
    return "\n".join(lines)


def format_backtest_summary(results: list[dict]) -> str:
    """
    Format a backtest comparison table for the console.

    Each dict should have config_name, total_trades, win_rate, avg_roc,
    total_pnl, max_drawdown, profit_factor.
    """
    lines: list[str] = []
    lines.append("")
    lines.append("  BACKTEST COMPARISON")
    lines.append(f"  {'─' * 78}")
    lines.append(
        f"  {'Config':<16} {'Trades':>6} {'Win%':>6} {'AvgROC':>7} "
        f"{'P&L':>10} {'MaxDD':>8} {'PF':>5}"
    )
    lines.append(f"  {'─' * 78}")

    for r in results:
        pf = r.get("profit_factor", 0)
        pf_str = f"{pf:.2f}" if pf < 100 else "INF"
        pnl = r.get("total_pnl", 0)
        pnl_str = f"${pnl:,.0f}" if pnl >= 0 else f"-${abs(pnl):,.0f}"

        lines.append(
            f"  {r.get('config_name', '?'):<16} "
            f"{r.get('total_trades', 0):>6} "
            f"{r.get('win_rate', 0):>5.0f}% "
            f"{r.get('avg_roc', 0):>6.1f}% "
            f"{pnl_str:>10} "
            f"${r.get('max_drawdown', 0):>7,.0f} "
            f"{pf_str:>5}"
        )

    lines.append(f"  {'─' * 78}")
    lines.append("")
    return "\n".join(lines)
