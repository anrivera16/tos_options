#!/usr/bin/env python3
"""Weekly review — the payoff. Turns the signal/outcome logs into edge.

Joins the signal ledger × forward-scored outcomes (× the trade journal, once it
carries signal_id) and answers the only questions that matter:

  • System edge   — hit-rate, avg realized move, avg contract return, by source.
  • Calibration   — does a higher signal score actually predict a better
                    outcome? (bucketed, with sample sizes shown — N is small,
                    so the counts are part of the answer.)

Reads research/signals/{signals,outcomes}.jsonl. Writes an HTML dashboard and
prints a text summary (good for a no_agent cron delivered to Discord).

Usage:
    python3 flow_dashboard/weekly_review.py
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signal_log as sl  # noqa: E402
import forward_scorer as fs  # noqa: E402
import decisions as dec  # noqa: E402

LOOKBACK_DAYS = 60   # how far back to include scored signals
OUT_PATH = os.path.expanduser("~/Desktop/weekly_review.html")

# Score buckets for the calibration table.
SCORE_BUCKETS = [(0, 40, "<40"), (40, 55, "40–55"), (55, 70, "55–70"),
                 (70, 101, "70+")]

# Decision-filter table order (the behavioral half of the loop).
DECISION_ORDER = ["promote", "pass", "undecided"]


def _card_id(row) -> str:
    """The decision key for an outcome: its parent thesis, else itself."""
    return row.get("parent_id") or row.get("signal_id") or ""


def _bucket(score) -> str:
    s = score if isinstance(score, (int, float)) else -1
    for lo, hi, label in SCORE_BUCKETS:
        if lo <= s < hi:
            return label
    return "n/a"


def _pct(x, places=1) -> str:
    return "—" if x is None else f"{x*100:+.{places}f}%"


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _rate(bools):
    bs = [b for b in bools if b is not None]
    return sum(1 for b in bs if b) / len(bs) if bs else None


# ─── Join + aggregate ─────────────────────────────────────────────

def build_rows(signals_path=None, outcomes_path=None, decisions_path=None,
               today=None):
    today = today or date.today()
    cutoff = today - timedelta(days=LOOKBACK_DAYS)
    sigs = {s["signal_id"]: s for s in sl.load_signals(signals_path)}
    decisions = dec.load_decisions(decisions_path)

    # outcomes (allow override path for tests)
    op = outcomes_path or fs.OUTCOMES_PATH
    _orig = fs.OUTCOMES_PATH
    fs.OUTCOMES_PATH = op  # type: ignore[assignment]
    outcomes = fs.load_outcomes()
    fs.OUTCOMES_PATH = _orig  # type: ignore[assignment]

    joined = []
    for sid, o in outcomes.items():
        sd = fs._parse_date(o.get("signal_date"))
        if sd and sd < cutoff:
            continue
        row = {**sigs.get(sid, {}), **o}  # outcome wins on shared keys
        # Tag with your nightly review call (joined on the card grain).
        row["_decision"] = decisions.get(_card_id(row), {}).get("decision",
                                                                 "undecided")
        joined.append(row)
    return joined


def aggregate(rows, key):
    """Group rows by ``key(row)`` → metrics dict."""
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(key(r), []).append(r)
    out = {}
    for g, rs in groups.items():
        contract = [r for r in rs if r.get("contract_return_pct") is not None]
        out[g] = {
            "n": len(rs),
            "hit_rate": _rate([r.get("direction_correct") for r in rs]),
            "avg_move": _mean([r.get("realized_move_pct") for r in rs]),
            "em_hit": _rate([r.get("hit_1em") for r in rs]),
            "avg_mfe": _mean([r.get("mfe_pct") for r in rs]),
            "avg_mae": _mean([r.get("mae_pct") for r in rs]),
            "n_contract": len(contract),
            "avg_contract_ret": _mean([r.get("contract_return_pct") for r in contract]),
            "avg_best_ret": _mean([r.get("contract_best_return_pct") for r in contract]),
        }
    return out


# ─── Render ───────────────────────────────────────────────────────

def _color(x, good=0.55):
    if x is None:
        return "#888"
    return "#00C853" if x >= good else ("#FFD600" if x >= good - 0.15 else "#FF1744")


def _agg_table(title, agg, order=None) -> str:
    keys = order or sorted(agg)
    body = ""
    for k in keys:
        if k not in agg:
            continue
        m = agg[k]
        body += f"""<tr>
          <td><b style="color:#fff">{k}</b></td>
          <td style="text-align:center">{m['n']}</td>
          <td style="text-align:center;color:{_color(m['hit_rate'])}">{'—' if m['hit_rate'] is None else f"{m['hit_rate']*100:.0f}%"}</td>
          <td style="text-align:right">{_pct(m['avg_move'])}</td>
          <td style="text-align:center;color:{_color(m['em_hit'],0.4)}">{'—' if m['em_hit'] is None else f"{m['em_hit']*100:.0f}%"}</td>
          <td style="text-align:right;color:#00C853">{_pct(m['avg_mfe'])}</td>
          <td style="text-align:right;color:#FF1744">{_pct(m['avg_mae'])}</td>
          <td style="text-align:right">{m['n_contract'] or '—'}</td>
          <td style="text-align:right">{_pct(m['avg_contract_ret'],0)}</td>
          <td style="text-align:right;color:#888">{_pct(m['avg_best_ret'],0)}</td>
        </tr>"""
    return f"""<h2 style="color:#fff;font-size:1.1em;margin:24px 0 8px">{title}</h2>
    <table><thead><tr>
      <th>{title.split()[0]}</th><th style="text-align:center">N</th>
      <th style="text-align:center">Dir hit</th><th style="text-align:right">Avg move</th>
      <th style="text-align:center">≥1 EM</th><th style="text-align:right">Avg MFE</th>
      <th style="text-align:right">Avg MAE</th><th style="text-align:right">N opt</th>
      <th style="text-align:right">Avg opt ret</th><th style="text-align:right">Best-exit</th>
    </tr></thead><tbody>{body or '<tr><td colspan=10 style="text-align:center;color:#666;padding:20px">No scored signals in window</td></tr>'}</tbody></table>"""


def render_html(rows, generated_at) -> str:
    by_source = aggregate(rows, lambda r: r.get("source") or "n/a")
    by_bucket = aggregate(rows, lambda r: _bucket(r.get("score")))
    by_decision = aggregate(rows, lambda r: r.get("_decision") or "undecided")
    overall = aggregate(rows, lambda r: "all").get("all", {"n": 0})

    bucket_order = [b[2] for b in SCORE_BUCKETS]
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Weekly Review — {generated_at:%Y-%m-%d}</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#1a1a2e;color:#e0e0e0;margin:0;padding:20px;max-width:1200px;margin:0 auto}}
h1{{text-align:center;color:#fff;margin:0 0 6px}}
table{{width:100%;border-collapse:collapse;background:#0d1117;border-radius:8px;overflow:hidden;margin-bottom:8px}}
th{{background:#16213e;color:#aaa;padding:9px;text-align:left;font-size:0.72em;text-transform:uppercase;letter-spacing:0.4px}}
td{{padding:9px;border-bottom:1px solid #1a1a2e}}
tr:hover td{{background:#16213e}}
.kpi{{background:#0d1117;padding:14px;border-radius:8px;text-align:center;flex:1}}
.kpi .v{{font-size:1.6em;font-weight:700;color:#fff}}.kpi .l{{font-size:0.72em;color:#888;text-transform:uppercase;margin-top:4px}}
</style></head><body>
<h1>📊 Weekly Signal Review</h1>
<p style="text-align:center;color:#888;font-size:0.85em">Generated {generated_at:%Y-%m-%d %H:%M} · last {LOOKBACK_DAYS}d · signals × forward outcomes</p>
<div style="display:flex;gap:10px;margin:18px 0">
  <div class="kpi"><div class="v">{overall.get('n',0)}</div><div class="l">scored signals</div></div>
  <div class="kpi"><div class="v" style="color:{_color(overall.get('hit_rate'))}">{'—' if overall.get('hit_rate') is None else f"{overall['hit_rate']*100:.0f}%"}</div><div class="l">direction hit-rate</div></div>
  <div class="kpi"><div class="v">{_pct(overall.get('avg_move'))}</div><div class="l">avg realized move</div></div>
  <div class="kpi"><div class="v">{_pct(overall.get('avg_contract_ret'),0)}</div><div class="l">avg option return</div></div>
</div>
{_agg_table("Source edge", by_source)}
{_agg_table("Score calibration", by_bucket, order=bucket_order)}
{_agg_table("Decision filter", by_decision, order=DECISION_ORDER)}
<div style="background:#0d1117;border-radius:8px;padding:12px;margin:14px 0;font-size:0.82em;color:#bbb;line-height:1.7">
  <b style="color:#aaa">Reading it</b> — <b>Dir hit</b> = % where price moved the signaled way by the horizon.
  <b>≥1 EM</b> = % that realized at least one expected move (the thesis bar). <b>Avg opt ret</b> reprices the
  graded contract at the realized spot (IV held). <b>Calibration works</b> if hit-rate / returns climb with the
  score bucket — if they don't, the score isn't earning its weight. <b>N is small early on; treat thin buckets as noise.</b>
  <br><b style="color:#aaa">Decision filter</b> — your nightly call (board pass/promote), joined on the card. You add
  edge as a filter only if <b>promote</b> beats <b>pass</b> on hit-rate / returns. If passed signals do as well, your
  selection isn't earning its keep. (Counts outcome rows per card decision; <code>undecided</code> = not yet reviewed.)
  Trade-journal P&amp;L joins here once the journal carries <code>signal_id</code>.
</div>
</body></html>"""


def text_summary(rows) -> str:
    by_source = aggregate(rows, lambda r: r.get("source") or "n/a")
    by_bucket = aggregate(rows, lambda r: _bucket(r.get("score")))
    by_decision = aggregate(rows, lambda r: r.get("_decision") or "undecided")
    lines = [f"Weekly review — {len(rows)} scored signals (last {LOOKBACK_DAYS}d)", ""]
    lines.append("By source:")
    for k, m in sorted(by_source.items()):
        hr = "—" if m["hit_rate"] is None else f"{m['hit_rate']*100:.0f}%"
        lines.append(f"  {k:20s} N={m['n']:3d}  dir={hr:>4}  move={_pct(m['avg_move'])}  opt={_pct(m['avg_contract_ret'],0)}")
    lines.append("By score bucket:")
    for _, _, label in SCORE_BUCKETS:
        m = by_bucket.get(label)
        if not m:
            continue
        hr = "—" if m["hit_rate"] is None else f"{m['hit_rate']*100:.0f}%"
        em = "—" if m["em_hit"] is None else f"{m['em_hit']*100:.0f}%"
        lines.append(f"  {label:6s} N={m['n']:3d}  dir={hr:>4}  "
                     f"move={_pct(m['avg_move'])}  ≥1EM={em}")
    lines.append("By decision (am I a good filter?):")
    for label in DECISION_ORDER:
        m = by_decision.get(label)
        if not m:
            continue
        hr = "—" if m["hit_rate"] is None else f"{m['hit_rate']*100:.0f}%"
        lines.append(f"  {label:9s} N={m['n']:3d}  dir={hr:>4}  "
                     f"move={_pct(m['avg_move'])}  opt={_pct(m['avg_contract_ret'],0)}")
    return "\n".join(lines)


def main() -> None:
    rows = build_rows()
    html = render_html(rows, datetime.now())
    with open(OUT_PATH, "w") as f:
        f.write(html)
    print(text_summary(rows))
    print(f"\n✅ {OUT_PATH}  ({len(rows)} scored signals)")


def _selftest() -> None:
    """Validate the decision join on synthetic data (no mature outcomes yet).

    One promoted card (its contract was right) vs one passed card (it was wrong);
    assert the decision-filter aggregate separates them and the card-grain join
    resolves a contract outcome to its parent thesis decision.
    """
    import json
    import tempfile

    d = tempfile.mkdtemp()
    sp = os.path.join(d, "signals.jsonl")
    op = os.path.join(d, "outcomes.jsonl")
    dp = os.path.join(d, "decisions.jsonl")
    today = date.today().isoformat()

    with open(sp, "w") as f:
        for r in [
            {"signal_id": "X-swing-AAA-bull", "parent_id": None,
             "source": "swing_persistence", "ticker": "AAA", "direction": 1, "score": 80},
            {"signal_id": "X-grade-AAA-C100-260717", "parent_id": "X-swing-AAA-bull",
             "source": "directional_grader", "ticker": "AAA", "direction": 1, "score": 75},
            {"signal_id": "X-swing-BBB-bear", "parent_id": None,
             "source": "swing_persistence", "ticker": "BBB", "direction": -1, "score": 45},
        ]:
            f.write(json.dumps(r) + "\n")
    with open(op, "w") as f:
        for r in [
            {"signal_id": "X-grade-AAA-C100-260717", "signal_date": today,
             "direction_correct": True, "realized_move_pct": 0.05,
             "contract_return_pct": 0.40},
            {"signal_id": "X-swing-BBB-bear", "signal_date": today,
             "direction_correct": False, "realized_move_pct": -0.03},
        ]:
            f.write(json.dumps(r) + "\n")
    with open(dp, "w") as f:
        f.write(json.dumps({"card_id": "X-swing-AAA-bull", "decision": "promote"}) + "\n")
        f.write(json.dumps({"card_id": "X-swing-BBB-bear", "decision": "pass"}) + "\n")

    rows = build_rows(signals_path=sp, outcomes_path=op, decisions_path=dp)
    tag = {r["signal_id"]: r["_decision"] for r in rows}
    # contract outcome resolves to its PARENT thesis's decision
    assert tag["X-grade-AAA-C100-260717"] == "promote", tag
    assert tag["X-swing-BBB-bear"] == "pass", tag

    by_dec = aggregate(rows, lambda r: r["_decision"])
    assert by_dec["promote"]["hit_rate"] == 1.0, by_dec["promote"]
    assert by_dec["pass"]["hit_rate"] == 0.0, by_dec["pass"]
    assert by_dec["promote"]["avg_contract_ret"] == 0.40, by_dec["promote"]
    print("weekly_review decision-join selftest ✅")
    print(text_summary(rows))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        main()
