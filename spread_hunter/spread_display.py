"""
Spread Display — terminal tables and Discord formatting for spread hunter results.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from spread_hunter.spread_types import (
    AnySpread,
    CalendarSpread,
    IronCondor,
    IronFly,
    SPREAD_TYPE_NAMES,
    VerticalSpread,
)

ET = ZoneInfo("US/Eastern")


# ---------------------------------------------------------------------------
# Terminal formatting
# ---------------------------------------------------------------------------

def format_vertical_table(spreads: list[VerticalSpread], label: str) -> str:
    """Format vertical spreads as ASCII table."""
    if not spreads:
        return f"  {label}: no candidates"

    lines = []
    lines.append("")
    lines.append(f"  {label} — {len(spreads)} candidates")
    lines.append(f"  {'=' * 110}")
    lines.append(
        f"  {'Sym':<5} {'Short':>7} {'Long':>7} {'Exp':>12} {'DTE':>3} "
        f"{'Prem':>6} {'MaxL':>6} {'BE':>8} {'ROI%':>5} "
        f"{'dNet':>6} {'tNet':>6} {'OI':>7} {'Spd%':>5} {'Score':>6}"
    )
    lines.append(f"  {'-' * 110}")

    for s in spreads[:15]:
        exp_short = s.expiration_date[:10] if s.expiration_date else "???"
        theta_str = f"{s.net_theta:>+.3f}" if s.net_theta is not None else "    n/a"
        delta_str = f"{s.net_delta:>+.3f}" if s.net_delta is not None else "    n/a"

        lines.append(
            f"  {s.underlying:<5} {s.short_leg.strike:>7.1f} {s.long_leg.strike:>7.1f} "
            f"{exp_short:>12} {s.dte:>3} "
            f"{s.net_premium:>6.2f} {s.max_loss:>6.2f} {s.breakeven:>8.2f} "
            f"{s.roi_pct:>5.1f} "
            f"{delta_str} {theta_str} "
            f"{s.min_oi:>7,} {s.max_spread_pct:>5.1f} {s.score:>6.3f}"
        )

    lines.append(f"  {'-' * 110}")
    return "\n".join(lines)


def format_iron_condor_table(ics: list[IronCondor]) -> str:
    """Format iron condors as ASCII table."""
    if not ics:
        return "  Iron Condor: no candidates"

    lines = []
    lines.append("")
    lines.append(f"  Iron Condor — {len(ics)} candidates")
    lines.append(f"  {'=' * 115}")
    lines.append(
        f"  {'Sym':<5} {'PShort':>7} {'PLong':>7} {'CShort':>7} {'CLong':>7} "
        f"{'DTE':>3} {'Credit':>7} {'MaxL':>6} {'BE-Lo':>8} {'BE-Hi':>8} "
        f"{'ROI%':>5} {'OI':>7} {'Score':>6}"
    )
    lines.append(f"  {'-' * 115}")

    for ic in ics[:15]:
        ps = ic.put_short.strike if ic.put_short else 0
        pl = ic.put_long.strike if ic.put_long else 0
        cs = ic.call_short.strike if ic.call_short else 0
        cl = ic.call_long.strike if ic.call_long else 0

        lines.append(
            f"  {ic.underlying:<5} {ps:>7.1f} {pl:>7.1f} {cs:>7.1f} {cl:>7.1f} "
            f"{ic.dte:>3} {ic.total_credit:>7.2f} {ic.max_loss:>6.2f} "
            f"{ic.breakeven_low:>8.2f} {ic.breakeven_high:>8.2f} "
            f"{ic.roi_pct:>5.1f} {ic.min_oi:>7,} {ic.score:>6.3f}"
        )

    lines.append(f"  {'-' * 115}")
    return "\n".join(lines)


def format_iron_fly_table(flys: list[IronFly]) -> str:
    """Format iron flys as ASCII table."""
    if not flys:
        return "  Iron Fly: no candidates"

    lines = []
    lines.append("")
    lines.append(f"  Iron Fly — {len(flys)} candidates")
    lines.append(f"  {'=' * 105}")
    lines.append(
        f"  {'Sym':<5} {'Center':>7} {'PWin':>6} {'CWin':>6} "
        f"{'DTE':>3} {'Credit':>7} {'MaxL':>6} {'BE-Lo':>8} {'BE-Hi':>8} "
        f"{'ROI%':>5} {'OI':>7} {'Score':>6}"
    )
    lines.append(f"  {'-' * 105}")

    for fly in flys[:15]:
        lines.append(
            f"  {fly.underlying:<5} {fly.center_strike:>7.1f} "
            f"{fly.put_width:>6.1f} {fly.call_width:>6.1f} "
            f"{fly.dte:>3} {fly.total_credit:>7.2f} {fly.max_loss:>6.2f} "
            f"{fly.breakeven_low:>8.2f} {fly.breakeven_high:>8.2f} "
            f"{fly.roi_pct:>5.1f} {fly.min_oi:>7,} {fly.score:>6.3f}"
        )

    lines.append(f"  {'-' * 105}")
    return "\n".join(lines)


def format_calendar_table(cals: list[CalendarSpread]) -> str:
    """Format calendar spreads as ASCII table."""
    if not cals:
        return "  Calendar: no candidates"

    lines = []
    lines.append("")
    lines.append(f"  Calendar Spread — {len(cals)} candidates")
    lines.append(f"  {'=' * 110}")
    lines.append(
        f"  {'Sym':<5} {'Strike':>7} {'NearDTE':>7} {'FarDTE':>7} "
        f"{'Gap':>3} {'Debit':>6} {'nIV':>5} {'fIV':>5} {'dIV':>5} "
        f"{'dNet':>6} {'tNet':>6} {'OI':>7} {'Score':>6}"
    )
    lines.append(f"  {'-' * 110}")

    for cal in cals[:15]:
        niv = f"{cal.near_iv:.1f}" if cal.near_iv is not None else "  n/a"
        fiv = f"{cal.far_iv:.1f}" if cal.far_iv is not None else "  n/a"
        div = f"{cal.iv_diff:>+.1f}" if cal.iv_diff is not None else "  n/a"
        delta_str = f"{cal.net_delta:>+.3f}" if cal.net_delta is not None else "    n/a"
        theta_str = f"{cal.net_theta:>+.3f}" if cal.net_theta is not None else "    n/a"
        gap = cal.far_dte - cal.near_dte

        lines.append(
            f"  {cal.underlying:<5} {cal.strike:>7.1f} {cal.near_dte:>7} {cal.far_dte:>7} "
            f"{gap:>3} {cal.debit:>6.2f} {niv} {fiv} {div} "
            f"{delta_str} {theta_str} "
            f"{cal.min_oi:>7,} {cal.score:>6.3f}"
        )

    lines.append(f"  {'-' * 110}")
    return "\n".join(lines)


def format_all_results(
    results: dict[str, list[AnySpread]],
    now_str: str | None = None,
) -> str:
    """Format all spread results for terminal output."""
    if now_str is None:
        now_str = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")

    total = sum(len(v) for v in results.values())

    parts: list[str] = []
    parts.append(f"\n{'#' * 70}")
    parts.append(f"  SPREAD HUNTER — {now_str}")
    parts.append(f"  Total candidates: {total}")
    parts.append(f"{'#' * 70}")

    # Verticals
    for vtype in ["bull_put_credit", "bear_call_credit"]:
        spreads = [s for s in results.get(vtype, []) if isinstance(s, VerticalSpread)]
        label = SPREAD_TYPE_NAMES.get(vtype, vtype)
        parts.append(format_vertical_table(spreads, label))

    # Iron condors
    ics = [s for s in results.get("iron_condor", []) if isinstance(s, IronCondor)]
    parts.append(format_iron_condor_table(ics))

    # Iron flys
    flys = [s for s in results.get("iron_fly", []) if isinstance(s, IronFly)]
    parts.append(format_iron_fly_table(flys))

    # Calendars
    cals = [s for s in results.get("calendar", []) if isinstance(s, CalendarSpread)]
    parts.append(format_calendar_table(cals))

    parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Discord formatting
# ---------------------------------------------------------------------------

def format_discord_message(
    results: dict[str, list[AnySpread]],
    now_str: str | None = None,
) -> str:
    """Format results for Discord (compact, 2000 char limit)."""
    if now_str is None:
        now_str = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")

    total = sum(len(v) for v in results.values())
    if total == 0:
        return f"**Spread Hunter** {now_str}\nNo candidates found."

    lines: list[str] = []
    lines.append(f"**Spread Hunter** {now_str}")
    lines.append(f"Found **{total}** candidates```")

    # Verticals
    for vtype in ["bull_put_credit", "bear_call_credit"]:
        spreads = [s for s in results.get(vtype, []) if isinstance(s, VerticalSpread)]
        if not spreads:
            continue
        label = SPREAD_TYPE_NAMES.get(vtype, vtype)
        lines.append(f"--- {label} ({len(spreads)}) ---")
        lines.append(
            f"{'Sym':<4} {'Sell':>5} {'Buy':>5} {'DTE':>3} "
            f"{'$':>5} {'Risk':>5} {'ROI':>4} {'OI':>5} {'Scr':>4}"
        )
        for s in spreads[:5]:
            lines.append(
                f"{s.underlying:<4} {s.short_leg.strike:>5.0f} "
                f"{s.long_leg.strike:>5.0f} {s.dte:>3} "
                f"{s.net_premium:>5.2f} {s.max_loss:>5.2f} "
                f"{s.roi_pct:>3.0f}% {s.min_oi:>5} {s.score:>4.2f}"
            )
        lines.append("")

    # Iron condors
    ics = [s for s in results.get("iron_condor", []) if isinstance(s, IronCondor)]
    if ics:
        lines.append(f"--- Iron Condor ({len(ics)}) ---")
        lines.append(
            f"{'Sym':<4} {'PS':>5} {'CS':>5} {'DTE':>3} "
            f"{'$':>5} {'Risk':>5} {'ROI':>4} {'Scr':>4}"
        )
        for ic in ics[:5]:
            ps = ic.put_short.strike if ic.put_short else 0
            cs = ic.call_short.strike if ic.call_short else 0
            lines.append(
                f"{ic.underlying:<4} {ps:>5.0f} {cs:>5.0f} {ic.dte:>3} "
                f"{ic.total_credit:>5.2f} {ic.max_loss:>5.2f} "
                f"{ic.roi_pct:>3.0f}% {ic.score:>4.2f}"
            )
        lines.append("")

    # Iron flys
    flys = [s for s in results.get("iron_fly", []) if isinstance(s, IronFly)]
    if flys:
        lines.append(f"--- Iron Fly ({len(flys)}) ---")
        lines.append(
            f"{'Sym':<4} {'Ctr':>5} {'DTE':>3} "
            f"{'$':>5} {'Risk':>5} {'ROI':>4} {'Scr':>4}"
        )
        for fly in flys[:5]:
            lines.append(
                f"{fly.underlying:<4} {fly.center_strike:>5.0f} {fly.dte:>3} "
                f"{fly.total_credit:>5.2f} {fly.max_loss:>5.2f} "
                f"{fly.roi_pct:>3.0f}% {fly.score:>4.2f}"
            )
        lines.append("")

    # Calendars
    cals = [s for s in results.get("calendar", []) if isinstance(s, CalendarSpread)]
    if cals:
        lines.append(f"--- Calendar ({len(cals)}) ---")
        lines.append(
            f"{'Sym':<4} {'K':>5} {'nD':>2} {'fD':>2} "
            f"{'Deb':>5} {'dIV':>5} {'OI':>5} {'Scr':>4}"
        )
        for cal in cals[:5]:
            div_str = f"{cal.iv_diff:>+.1f}" if cal.iv_diff is not None else "  n/a"
            lines.append(
                f"{cal.underlying:<4} {cal.strike:>5.0f} "
                f"{cal.near_dte:>2} {cal.far_dte:>2} "
                f"{cal.debit:>5.2f} {div_str} "
                f"{cal.min_oi:>5} {cal.score:>4.2f}"
            )
        lines.append("")

    lines.append("```")

    msg = "\n".join(lines)
    if len(msg) > 1900:
        msg = msg[:1890] + "\n...truncated```"

    return msg
