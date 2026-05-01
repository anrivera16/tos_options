"""
IV Term Structure — query + chart.

Shows how implied volatility changes across expirations for a given
strike / delta bucket.  Useful for:
  - identifying expensive vs cheap expirations (sell the rich, buy the cheap)
  - spotting term-structure inversions (near-term IV > far-term = fear)
  - choosing optimal DTE for credit spreads (higher IV = more credit)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DB = "postgresql://trader:changeme@localhost:5433/options"


def _connect(db_path: str):
    from gex.storage import get_connection
    return get_connection(db_path)


def _q(conn, sql: str, params: tuple = ()):
    """Execute a query and return list of dicts."""
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


# ── Core queries ──────────────────────────────────────────────────

def get_spot(conn, symbol: str) -> float | None:
    rows = _q(conn, """
        SELECT underlying_price AS spot
        FROM snapshots
        WHERE symbol LIKE %s
        ORDER BY captured_at DESC
        LIMIT 1
    """, (f"{symbol}%",))
    return rows[0]["spot"] if rows else None


def resolve_strike(conn, symbol: str, strike: float | None,
                   delta_target: float | None, put_call: str,
                   spot: float) -> float | None:
    """Resolve the actual strike to use. Returns a single strike."""
    if strike is not None:
        return strike

    if delta_target is not None:
        # For puts, delta is negative (e.g. -0.20). User passes 0.20, we match -0.20.
        # For calls, delta is positive.
        target_delta = delta_target if put_call == "CALL" else -abs(delta_target)
        rows = _q(conn, """
            SELECT oc.strike
            FROM option_contracts oc
            JOIN snapshots s ON oc.snapshot_id = s.id
            WHERE s.symbol LIKE %s
              AND oc.put_call = %s
              AND oc.delta IS NOT NULL
              AND s.captured_at = (
                  SELECT MAX(captured_at) FROM snapshots WHERE symbol LIKE %s
              )
            ORDER BY ABS(oc.delta - %s), oc.dte
            LIMIT 1
        """, (f"{symbol}%", put_call, f"{symbol}%", target_delta))
        return float(rows[0]["strike"]) if rows else None

    # ATM — round to nearest strike
    return round(spot)


def get_iv_term_structure(conn, symbol: str, strike: float,
                          put_call: str, snapshot_filter: str = "latest"):
    """
    Return IV across all available DTE for a given strike.
    One row per DTE.
    """
    sym = f"{symbol}%"

    if snapshot_filter == "latest":
        filter_sql = """
            AND s.captured_at = (
                SELECT MAX(captured_at)
                FROM snapshots WHERE symbol LIKE %s
            )
        """
        filter_params = (sym,)
    else:
        # avg_today: average across all snapshots from the most recent trading day
        # Uses MAX date to avoid CURRENT_DATE timezone issues (DB is UTC)
        filter_sql = """
            AND DATE(s.captured_at) = (
                SELECT DATE(MAX(captured_at))
                FROM snapshots WHERE symbol LIKE %s
            )
        """
        filter_params = (sym,)

    sql = f"""
        SELECT
            oc.dte,
            MIN(oc.expiration_date) AS expiration_date,
            ROUND(AVG(oc.volatility)::numeric, 2) AS avg_iv,
            ROUND(MIN(oc.volatility)::numeric, 2) AS min_iv,
            ROUND(MAX(oc.volatility)::numeric, 2) AS max_iv,
            SUM(oc.open_interest) AS total_oi,
            SUM(oc.total_volume) AS total_vol
        FROM option_contracts oc
        JOIN snapshots s ON oc.snapshot_id = s.id
        WHERE s.symbol LIKE %s
          AND oc.put_call = %s
          AND oc.strike = %s
          {filter_sql}
        GROUP BY oc.dte
        ORDER BY oc.dte
    """

    params = (sym, put_call, strike) + filter_params
    return _q(conn, sql, params)


# ── Chart ─────────────────────────────────────────────────────────

def render_iv_term_chart(
    data: list[dict],
    symbol: str,
    put_call: str,
    strike: float,
    spot: float | None,
    snapshot_filter: str,
    output: str,
):
    """Render and save IV term structure chart."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

    if not data:
        print("No data to chart.")
        return

    dtes = [r["dte"] for r in data]
    avg_ivs = [float(r["avg_iv"]) for r in data]
    min_ivs = [float(r["min_iv"]) for r in data]
    max_ivs = [float(r["max_iv"]) for r in data]
    ois = [r["total_oi"] or 0 for r in data]

    fig, (ax_iv, ax_oi) = plt.subplots(
        2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )

    # ── Top panel: IV by DTE ──
    # Range band (min-max)
    ax_iv.fill_between(dtes, min_ivs, max_ivs, alpha=0.12, color="#3498db", label="IV range (min-max)")

    # Average IV line
    ax_iv.plot(dtes, avg_ivs, "o-", color="#2c3e50", linewidth=2.5, markersize=8, zorder=5, label="Avg IV")

    # Annotate each point
    for d, iv in zip(dtes, avg_ivs):
        ax_iv.annotate(f"{iv:.1f}%", (d, iv), textcoords="offset points",
                        xytext=(0, 12), ha="center", fontsize=9, fontweight="bold")

    # Highlight inversions
    for i in range(1, len(avg_ivs)):
        if avg_ivs[i] > avg_ivs[i - 1]:
            ax_iv.axvspan(dtes[i - 1], dtes[i], alpha=0.10, color="red", zorder=0)
            mid_dte = (dtes[i - 1] + dtes[i]) / 2
            mid_iv = (avg_ivs[i - 1] + avg_ivs[i]) / 2
            ax_iv.annotate("inversion", (mid_dte, mid_iv), fontsize=8,
                           color="red", ha="center", style="italic",
                           xytext=(0, -18), textcoords="offset points")

    ax_iv.set_ylabel("Implied Volatility (%)", fontsize=12)
    ax_iv.grid(True, alpha=0.3)
    ax_iv.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax_iv.legend(loc="upper right", fontsize=10)

    filter_desc = "avg today" if snapshot_filter == "avg_today" else "latest snapshot"
    ax_iv.set_title(
        f"{symbol} {put_call} {strike:.0f}-strike IV Term Structure\n"
        f"Spot: {spot:.2f} | {filter_desc}",
        fontsize=14, fontweight="bold",
    )

    # ── Bottom panel: OI by DTE ──
    colors = ["#3498db" if o > 0 else "#bdc3c7" for o in ois]
    ax_oi.bar(dtes, ois, color=colors, alpha=0.7, width=0.8)
    ax_oi.set_ylabel("Open Interest", fontsize=12)
    ax_oi.set_xlabel("Days to Expiration (DTE)", fontsize=12)
    ax_oi.grid(True, alpha=0.3, axis="y")
    ax_oi.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda x, _: f"{x / 1e6:.1f}M" if x >= 1e6 else f"{x / 1e3:.0f}K" if x >= 1e3 else f"{x:.0f}"
    ))

    plt.tight_layout()
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nChart saved: {output}")


# ── Text output ───────────────────────────────────────────────────

def print_iv_term_table(data: list[dict], symbol: str, put_call: str,
                        strike: float, spot: float | None):
    """Print a formatted IV term structure table."""
    if not data:
        print("No data found.")
        return

    print(f"\n{symbol} {put_call} {strike:.0f}-strike IV Term Structure")
    print(f"Spot: {spot:.2f}")
    print("=" * 72)
    print(f"{'DTE':>5}  {'Expiration':>12}  {'Avg IV':>7}  {'Min IV':>7}  {'Max IV':>7}  {'OI':>10}  {'Volume':>10}")
    print("-" * 72)

    prev_iv = None
    for r in data:
        avg = float(r["avg_iv"])
        mn = float(r["min_iv"])
        mx = float(r["max_iv"])
        oi = r["total_oi"] or 0
        vol = r["total_vol"] or 0
        exp = r["expiration_date"][:10] if r["expiration_date"] else "N/A"

        marker = ""
        if prev_iv is not None and avg > prev_iv:
            marker = " <- inversion"

        oi_str = f"{oi / 1e6:.1f}M" if oi >= 1e6 else f"{oi / 1e3:.0f}K"
        vol_str = f"{vol / 1e6:.1f}M" if vol >= 1e6 else f"{vol / 1e3:.0f}K"

        print(f"{r['dte']:>5}  {exp:>12}  {avg:>6.1f}%  {mn:>6.1f}%  {mx:>6.1f}%  {oi_str:>10}  {vol_str:>10}{marker}")
        prev_iv = avg

    print("=" * 72)

    if len(data) >= 2:
        ivs = [float(r["avg_iv"]) for r in data]
        print(f"\n  Near-term (DTE={data[0]['dte']}): {ivs[0]:.1f}%")
        print(f"  Far-term  (DTE={data[-1]['dte']}): {ivs[-1]:.1f}%")
        spread = ivs[0] - ivs[-1]
        if spread > 0:
            print(f"  Contango: +{spread:.1f}%  <- normal (near-term richer, good for selling)")
        else:
            print(f"  Backwardation: {spread:.1f}%  <- near-term cheaper (unusual, possible opportunity)")

        best = max(data, key=lambda r: float(r["avg_iv"]))
        worst = min(data, key=lambda r: float(r["avg_iv"]))
        print(f"\n  Highest IV: DTE={best['dte']} at {float(best['avg_iv']):.1f}%  <- best DTE to sell premium")
        print(f"  Lowest IV:  DTE={worst['dte']} at {float(worst['avg_iv']):.1f}%")


# ── Multi-strike matrix ───────────────────────────────────────────

def get_iv_matrix(conn, symbol: str, put_call: str,
                  spot: float, num_strikes: int = 8,
                  snapshot_filter: str = "latest"):
    """
    Fetch IV for multiple strikes across all DTEs in ONE query.
    Returns list of dicts: {strike, dte, avg_iv, total_oi, total_vol}
    """
    sym = f"{symbol}%"

    if snapshot_filter == "latest":
        filter_sql = """
            AND s.captured_at = (
                SELECT MAX(captured_at)
                FROM snapshots WHERE symbol LIKE %s
            )
        """
        filter_params = (sym,)
    else:
        # avg_today: average across all snapshots from the most recent trading day
        # Uses MAX date to avoid CURRENT_DATE timezone issues (DB is UTC)
        filter_sql = """
            AND DATE(s.captured_at) = (
                SELECT DATE(MAX(captured_at))
                FROM snapshots WHERE symbol LIKE %s
            )
        """
        filter_params = (sym,)

    # Pick strikes: OTM strikes weighted by OI so we include the liquid ones.

    # Get top N strikes by OI within a range around spot
    strike_range = spot * 0.10  # 10% range
    strikes_sql = """
        SELECT oc.strike
        FROM option_contracts oc
        JOIN snapshots s ON oc.snapshot_id = s.id
        WHERE s.symbol LIKE %s
          AND oc.put_call = %s
          AND oc.strike <= %s
          AND ABS(oc.strike - %s) <= %s
          {snap_filter}
        GROUP BY oc.strike
        ORDER BY SUM(oc.open_interest) DESC
        LIMIT %s
    """.format(snap_filter=filter_sql)
    # For puts: strikes below spot. For calls: strikes above spot.
    bound = spot if put_call == "PUT" else 99999
    strike_rows = _q(conn, strikes_sql,
                     (sym, put_call, bound, spot, strike_range) + filter_params + (num_strikes,))
    if not strike_rows:
        return [], [], []

    strikes = sorted([float(r["strike"]) for r in strike_rows], reverse=(put_call == "PUT"))

    # Now fetch IV for these strikes across all DTEs -- ONE query
    placeholders = ",".join(["%s"] * len(strikes))
    matrix_sql = f"""
        SELECT
            oc.strike,
            oc.dte,
            ROUND(AVG(oc.volatility)::numeric, 2) AS avg_iv,
            SUM(oc.open_interest) AS total_oi,
            SUM(oc.total_volume) AS total_vol
        FROM option_contracts oc
        JOIN snapshots s ON oc.snapshot_id = s.id
        WHERE s.symbol LIKE %s
          AND oc.put_call = %s
          AND oc.strike IN ({placeholders})
          {filter_sql}
        GROUP BY oc.strike, oc.dte
        ORDER BY oc.strike, oc.dte
    """
    params = (sym, put_call) + tuple(strikes) + filter_params
    raw = _q(conn, matrix_sql, params)

    # Get ordered DTE list from the data
    all_dtes = sorted(set(r["dte"] for r in raw))
    return raw, strikes, all_dtes


def print_iv_matrix(raw: list[dict], strikes: list[float],
                    all_dtes: list[int], symbol: str,
                    put_call: str, spot: float):
    """Print a strike x DTE matrix of IV values."""
    if not raw:
        print("No data found.")
        return

    # Build lookup: (strike, dte) -> iv
    iv_map = {}
    for r in raw:
        iv_map[(float(r["strike"]), r["dte"])] = {
            "iv": float(r["avg_iv"]) if r["avg_iv"] else None,
            "oi": r["total_oi"] or 0,
        }

    print(f"\n{symbol} {put_call} IV Term Structure Matrix")
    print(f"Spot: {spot:.2f}")
    print()

    # Header
    dte_header = "  ".join(f"{d:>5}" for d in all_dtes)
    print(f"{'Strike':>8}  {dte_header}")
    print("-" * (10 + 7 * len(all_dtes)))

    # Find global IV range for color-coding
    all_ivs = [v["iv"] for v in iv_map.values() if v["iv"] is not None]
    iv_min = min(all_ivs) if all_ivs else 0
    iv_max = max(all_ivs) if all_ivs else 100

    for strike in strikes:
        row_vals = []
        for dte in all_dtes:
            entry = iv_map.get((strike, dte))
            if entry and entry["iv"] is not None:
                iv = entry["iv"]
                # Flag inversions: IV higher than previous DTE
                row_vals.append(f"{iv:>5.1f}")
            else:
                row_vals.append(f"{'---':>5}")

        # Mark ATM
        atm_marker = " <-- ATM" if abs(strike - round(spot)) < 2 else ""
        dist = ((strike - spot) / spot) * 100
        print(f"{strike:>8.0f}  {'  '.join(row_vals)}  ({dist:+.1f}%){atm_marker}")

    print()
    print(f"  DTE columns: {', '.join(str(d) for d in all_dtes)}")

    # Find inversions per strike
    print("\n  Inversions (IV rises as DTE increases):")
    any_inv = False
    for strike in strikes:
        inv_dtes = []
        prev_iv = None
        for dte in all_dtes:
            entry = iv_map.get((strike, dte))
            iv = entry["iv"] if entry else None
            if prev_iv is not None and iv is not None and iv > prev_iv:
                inv_dtes.append(dte)
            prev_iv = iv
        if inv_dtes:
            any_inv = True
            print(f"    {strike:.0f}-strike: DTE {', '.join(str(d) for d in inv_dtes)}")
    if not any_inv:
        print("    None found -- smooth contango across all strikes")

    # Best strike/DTE to sell
    best = None
    for r in raw:
        iv = float(r["avg_iv"]) if r["avg_iv"] else 0
        if best is None or iv > best[1]:
            best = (r["strike"], iv, r["dte"])
    if best:
        print(f"\n  Highest IV: {best[0]:.0f}-strike @ DTE={best[2]} = {best[1]:.1f}%  <- sell here")


def render_iv_heatmap(raw: list[dict], strikes: list[float],
                      all_dtes: list[int], symbol: str,
                      put_call: str, spot: float,
                      snapshot_filter: str, output: str):
    """Render a heatmap of IV across strikes and DTEs."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    if not raw:
        print("No data to chart.")
        return

    # Build matrix
    iv_map = {}
    for r in raw:
        iv_map[(float(r["strike"]), r["dte"])] = float(r["avg_iv"]) if r["avg_iv"] else np.nan

    matrix = np.full((len(strikes), len(all_dtes)), np.nan)
    for i, strike in enumerate(strikes):
        for j, dte in enumerate(all_dtes):
            val = iv_map.get((strike, dte))
            if val is not None:
                matrix[i, j] = val

    fig, ax = plt.subplots(figsize=(14, 8))

    im = ax.imshow(matrix, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    cbar = fig.colorbar(im, ax=ax, label="Implied Volatility (%)")

    # Labels
    ax.set_xticks(range(len(all_dtes)))
    ax.set_xticklabels([str(d) for d in all_dtes])
    ax.set_yticks(range(len(strikes)))
    ylabels = [f"{s:.0f}" for s in strikes]
    # Mark ATM
    for i, s in enumerate(strikes):
        if abs(s - round(spot)) < 2:
            ylabels[i] = f"{s:.0f} (ATM)"
    ax.set_yticklabels(ylabels)
    ax.set_xlabel("Days to Expiration (DTE)", fontsize=12)
    ax.set_ylabel("Strike", fontsize=12)

    # Annotate cells with IV values
    for i in range(len(strikes)):
        for j in range(len(all_dtes)):
            val = matrix[i, j]
            if not np.isnan(val):
                color = "white" if val > np.nanmedian(matrix) else "black"
                ax.text(j, i, f"{val:.1f}", ha="center", va="center",
                        fontsize=8, color=color, fontweight="bold")

    filter_desc = "avg today" if snapshot_filter == "avg_today" else "latest snapshot"
    ax.set_title(
        f"{symbol} {put_call} IV Term Structure Heatmap\n"
        f"Spot: {spot:.2f} | {filter_desc}",
        fontsize=14, fontweight="bold",
    )

    plt.tight_layout()
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Heatmap saved: {output}")


# ── CLI entry point ───────────────────────────────────────────────

def run_iv_term(args: argparse.Namespace) -> None:
    db_path = getattr(args, "db", DEFAULT_DB)
    conn = _connect(db_path)
    try:
        spot = get_spot(conn, args.symbol)
        if spot is None:
            print(f"No data found for {args.symbol}")
            return

        if getattr(args, "matrix", False):
            # Multi-strike matrix mode
            raw, strikes, all_dtes = get_iv_matrix(
                conn, args.symbol, args.put_call, spot,
                num_strikes=args.num_strikes,
                snapshot_filter=args.filter,
            )
            if not raw:
                print("No data found for matrix.")
                return
            print_iv_matrix(raw, strikes, all_dtes, args.symbol,
                            args.put_call, spot)

            if args.chart or args.output:
                out = args.output or f"out/iv_heatmap_{args.symbol}_{args.put_call}.png"
                render_iv_heatmap(raw, strikes, all_dtes, args.symbol,
                                  args.put_call, spot, args.filter, out)
        else:
            # Single-strike mode
            strike = resolve_strike(conn, args.symbol, args.strike,
                                    args.delta, args.put_call, spot)
            if strike is None:
                print("Could not resolve a strike. Try --strike explicitly.")
                return

            data = get_iv_term_structure(
                conn, args.symbol, strike, args.put_call, args.filter,
            )

            print_iv_term_table(data, args.symbol, args.put_call, strike, spot)

            if args.chart or args.output:
                out = args.output or f"out/iv_term_{args.symbol}_{args.put_call}_{strike:.0f}.png"
                render_iv_term_chart(
                    data, args.symbol, args.put_call, strike, spot,
                    args.filter, out,
                )
    finally:
        conn.close()


def register_parser(subparsers) -> None:
    """Wire this into the CLI's subparser tree."""
    iv_parser = subparsers.add_parser(
        "iv-term", help="IV term structure across expirations",
    )
    iv_parser.add_argument("--symbol", default="SPY", help="Underlying (default: SPY)")
    iv_parser.add_argument("--put-call", default="PUT", choices=["PUT", "CALL"],
                           help="PUT or CALL (default: PUT)")
    iv_parser.add_argument("--strike", type=float, default=None,
                           help="Specific strike (default: ATM)")
    iv_parser.add_argument("--delta", type=float, default=None,
                           help="Target delta instead of strike (e.g. 0.20)")
    iv_parser.add_argument("--filter", default="latest",
                           choices=["latest", "avg_today"],
                           help="Snapshot filter (default: latest)")
    iv_parser.add_argument("--chart", action="store_true", help="Generate PNG chart")
    iv_parser.add_argument("--output", default=None, help="Output path for chart")
    iv_parser.add_argument("--db", default=DEFAULT_DB, help="Database URL")
    # Matrix mode
    iv_parser.add_argument("--matrix", action="store_true",
                           help="Show IV matrix across multiple strikes")
    iv_parser.add_argument("--num-strikes", type=int, default=8,
                           help="Number of OTM strikes in matrix mode (default: 8)")
    iv_parser.set_defaults(func=run_iv_term)
