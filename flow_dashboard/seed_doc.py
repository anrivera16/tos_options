#!/usr/bin/env python3
"""Artifact seeder — materialize a living trade document when a card is promoted.

A card stays virtual (rendered from the ledger) until you *promote* it. Then this
writes ``research/journal/<card_id>.md``, seeded with the auto data — thesis,
flow, contracts, and a link to the GEX chart — leaving the Plan / Journal / Exit
sections for you to author over the life of the trade.

Seeding NEVER overwrites an existing doc: once it's yours, re-promoting is a
no-op on the file (it just re-logs the decision). The GEX chart is best-effort —
if UW/network is unavailable the doc still materializes with a note.

CLI:
    python3 seed_doc.py promote 20260614-swing-AMZN-bear
    python3 seed_doc.py pass    20260614-swing-INTC-bull
    python3 seed_doc.py list                      # show the Inbox
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date

from cards import Card, build_cards, inbox_cards
from decisions import PASS, PROMOTE, record_decision
from signal_log import PROJECT_ROOT, _dir_tag, load_signals

JOURNAL_DIR = os.path.join(PROJECT_ROOT, "research", "journal")
CHARTS_DIR = os.path.join(JOURNAL_DIR, "charts")
GEX_CHART = os.path.join(PROJECT_ROOT, "scripts", "gex_chart", "gex_chart.py")


# --------------------------------------------------------------------------- #
# GEX chart (best-effort, interactive HTML — not a PNG; see module docstring)
# --------------------------------------------------------------------------- #
def render_gex_chart(ticker: str, on: str) -> str | None:
    """Generate an interactive GEX chart HTML into the journal; return rel path.

    Returns None on any failure (no token, network, render error) so a missing
    chart never blocks the trade doc from being written.
    """
    if not os.path.exists(GEX_CHART):
        return None
    os.makedirs(CHARTS_DIR, exist_ok=True)
    fname = f"{ticker}_{on.replace('-', '')}_gex.html"
    out = os.path.join(CHARTS_DIR, fname)
    try:
        subprocess.run(
            [sys.executable, GEX_CHART, "--ticker", ticker, "--range", "5d",
             "--out", out],
            check=True, capture_output=True, text=True, timeout=90,
            cwd=os.path.dirname(GEX_CHART),
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutError, OSError):
        return None
    return os.path.join("charts", fname) if os.path.exists(out) else None


# --------------------------------------------------------------------------- #
# Document composition
# --------------------------------------------------------------------------- #
def _humanize(v: float) -> str:
    """Compact money-ish formatting: -1e8 → -100M."""
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"{v/div:+.1f}{suf}".replace(".0", "")
    return f"{v:+.0f}"


def _fmt_contract(c: dict) -> str:
    cp = "C" if (c.get("direction") or 0) > 0 else "P"
    strike = c.get("strike")
    exp = (c.get("expiry") or "")[5:].replace("-", "/")  # MM/DD
    bits = [f"**{cp}{strike:g} {exp}**"]
    if c.get("score") is not None:
        bits.append(f"grade {c['score']:.0f}")
    if c.get("entry_mid") is not None:
        bits.append(f"mid {c['entry_mid']:.2f}")
    if c.get("reach") is not None:
        bits.append(f"reach {c['reach']:.2f}")
    if c.get("pop") is not None:
        bits.append(f"pop {c['pop']*100:.0f}%")
    if c.get("delta") is not None:
        bits.append(f"Δ{c['delta']:.2f}")
    return " · ".join(bits)


def build_doc(card: Card, rows: list[dict], chart_rel: str | None) -> str:
    """Compose the seeded markdown for a promoted card."""
    thesis = next((r for r in rows if r.get("signal_id") == card.card_id), None)
    tx = (thesis or {}).get("extra") or {}

    # --- frontmatter ---
    fm = [
        "---",
        f"signal_id: {card.card_id}",
        f"source: {card.lead_tag}",
        "status: watching",
        f"opened: {date.today().isoformat()}",
        f"ticker: {card.ticker}",
        f"direction: {card.direction}",
        f"score: {card.score:g}" if card.score is not None else "score:",
        f"sector: {card.sector}" if card.sector else "sector:",
        "---",
    ]

    # --- thesis (seeded) ---
    head = [f"# {card.ticker} {card.side} · {card.source.label}", ""]
    th = ["## Thesis", ""]
    facts = []
    if card.thesis_score is not None:
        facts.append(f"persistence {card.thesis_score:.0f}")
    if card.iv_rank is not None:
        facts.append(f"IV rank {card.iv_rank:.0f}")
    if tx.get("accumulation") is not None:
        facts.append(f"accumulation {_humanize(tx['accumulation'])}")
    if tx.get("consistency") is not None:
        facts.append(f"consistency {tx['consistency']:.2f}")
    if card.earnings_flag:
        facts.append("⚠ earnings in window")
    if facts:
        th += [" · ".join(facts), ""]
    if card.contracts:
        th += ["**Graded contracts:**", ""]
        th += [f"- {_fmt_contract(c)}" for c in card.contracts]
        th += [""]
    # Interactive chart (HTML, not an image) → link, not a broken ![] embed.
    th += [f"📈 [Open {card.ticker} GEX chart →]({chart_rel})" if chart_rel
           else "_GEX chart unavailable at seed time — run gex_chart.py to attach._",
           ""]

    # --- author sections (left blank for you) ---
    rest = [
        "## Plan", "",
        "entry / stop / target / size · what invalidates it", "",
        "## Journal", "",
        "_append as the trade lives…_", "",
        "## Exit & Review", "",
        "_what happened vs the thesis · what I'd do differently_", "",
    ]
    return "\n".join(fm + [""] + head + th + rest)


def doc_path(card_id: str) -> str:
    return os.path.join(JOURNAL_DIR, f"{card_id}.md")


def seed_card(card: Card) -> tuple[str, bool]:
    """Materialize the trade doc for a card. Returns (path, created).

    ``created`` is False if the doc already existed — we never clobber your edits.
    """
    path = doc_path(card.card_id)
    if os.path.exists(path):
        return path, False
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    rows = [r for r in load_signals() if r.get("signal_id") in set(card.member_ids)]
    chart_rel = render_gex_chart(card.ticker, card.date)
    with open(path, "w") as f:
        f.write(build_doc(card, rows, chart_rel))
    return path, True


# --------------------------------------------------------------------------- #
# CLI orchestration
# --------------------------------------------------------------------------- #
def _find_card(card_id: str) -> Card | None:
    # wide window so we can still act on an older card
    for c in build_cards(nights=400, include_disabled=True):
        if c.card_id == card_id:
            return c
    return None


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    action = argv[0]

    if action == "list":
        q = inbox_cards()
        print(f"\nInbox · {len(q)} card(s)\n")
        for c in q:
            print(f"  {c.card_id:32} {c}")
        print()
        return 0

    if action not in ("pass", "promote"):
        print(f"unknown action {action!r} (use: pass | promote | list)")
        return 2
    if len(argv) < 2:
        print(f"usage: seed_doc.py {action} <card_id> [note…]")
        return 2

    card_id = argv[1]
    note = " ".join(argv[2:])
    card = _find_card(card_id)
    if card is None:
        print(f"no card found for {card_id!r} (try: seed_doc.py list)")
        return 1

    if action == "pass":
        record_decision(card_id, PASS, note=note)
        print(f"passed  {card_id}  →  logged to decisions.jsonl (still scored)")
    else:
        path, created = seed_card(card)
        record_decision(card_id, PROMOTE, note=note)
        rel = os.path.relpath(path, PROJECT_ROOT)
        print(f"promoted {card_id}  →  {'seeded' if created else 'exists'} {rel}")

    remaining = len(inbox_cards())
    print(f"Inbox now: {remaining} card(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
