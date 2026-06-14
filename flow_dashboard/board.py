#!/usr/bin/env python3
"""Trade Review Kanban — the board (Phase 3).

A thin Flask layer over the Phase 1–2 modules. It owns NO state: every request
re-derives the columns from the files, and every action calls the same functions
the CLI uses.

  Inbox            ← cards.inbox_cards()          (signals.jsonl − decisions.jsonl)
  Watching/Open/Closed ← journal.by_status()      (journal/*.md frontmatter)
  card color       ← sources.load_registry()      (sources.yaml)

Run:
    python3 flow_dashboard/board.py        # → http://127.0.0.1:5057
"""
from __future__ import annotations

import os

from flask import (Flask, abort, redirect, render_template, request,
                   send_from_directory, url_for)

from cards import inbox_cards
from decisions import PASS, PROMOTE, record_decision
from journal import JOURNAL_DIR, STATUSES, by_status, set_status
from seed_doc import _find_card, seed_card
from sources import load_registry, source_for

app = Flask(__name__)


# --------------------------------------------------------------------------- #
# View models — flatten cards into dumb dicts so the template stays logic-free
# --------------------------------------------------------------------------- #
def _fmt_contract(c: dict) -> str:
    cp = "C" if (c.get("direction") or 0) > 0 else "P"
    exp = (c.get("expiry") or "")[5:].replace("-", "/")
    g = f" g{c['score']:.0f}" if c.get("score") is not None else ""
    return f"{cp}{c.get('strike'):g} {exp}{g}"


def _inbox_vm(card, registry) -> dict:
    return {
        "card_id": card.card_id,
        "ticker": card.ticker,
        "side": card.side,
        "score": card.score,
        "color": card.source.color,
        "label": card.source.label,
        "sources": "+".join(card.sources),
        "sector": card.sector or "",
        "earnings": card.earnings_flag,
        "contracts": [_fmt_contract(c) for c in card.contracts],
    }


def _journal_vm(jc, registry) -> dict:
    src = source_for(jc.source, registry)
    return {
        "card_id": jc.card_id,
        "ticker": jc.ticker,
        "side": jc.side,
        "score": jc.score,
        "color": src.color,
        "label": src.label,
        "status": jc.status,
        "opened": jc.opened or "",
    }


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    registry = load_registry()
    inbox = [_inbox_vm(c, registry) for c in inbox_cards()]
    lanes = by_status()
    flight = {s: [_journal_vm(c, registry) for c in lanes[s]] for s in STATUSES}
    return render_template(
        "board.html",
        inbox=inbox,
        flight=flight,
        statuses=STATUSES,
        counts={"inbox": len(inbox), **{s: len(flight[s]) for s in STATUSES}},
    )


@app.route("/promote", methods=["POST"])
def promote():
    card_id = request.form["card_id"]
    card = _find_card(card_id)
    if card is None:
        abort(404)
    seed_card(card)
    record_decision(card_id, PROMOTE)
    return redirect(url_for("index"), code=303)


@app.route("/decide", methods=["POST"])
def decide():
    record_decision(request.form["card_id"], PASS)
    return redirect(url_for("index"), code=303)


@app.route("/status", methods=["POST"])
def status():
    set_status(request.form["card_id"], request.form["status"])
    return redirect(url_for("index"), code=303)


@app.route("/doc/<path:fname>")
def doc(fname):
    """Serve a journal file (the seeded md or its GEX chart html) for in-browser view."""
    return send_from_directory(JOURNAL_DIR, fname)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5057, debug=False)
