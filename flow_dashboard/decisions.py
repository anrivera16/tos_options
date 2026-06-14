#!/usr/bin/env python3
"""Decision log — append-only record of nightly review calls (pass / promote).

Keyed on the **card grain** (the thesis-level signal_id, e.g.
``20260614-swing-AMZN-bear``): you review a card — a ticker/direction/night idea,
with its contracts collapsed under it — not an individual contract. A decision
removes that card from the Inbox; passed cards stay in ``signals.jsonl`` and are
still forward-scored, so they remain the control group for "am I a good filter?".

Same JSONL discipline as signal_log: pure append, readers keep last-per-id.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from signal_log import SIGNALS_DIR

DECISIONS_PATH = os.path.join(SIGNALS_DIR, "decisions.jsonl")

# decision ∈ {"pass", "promote"}
PASS = "pass"
PROMOTE = "promote"


def record_decision(card_id: str, decision: str, *, note: str = "", **extra) -> dict:
    """Append one decision row for a card; return it. Pure append, idempotent-safe.

    A second decision on the same card just appends another row — readers keep the
    last, so changing your mind (pass → promote) Just Works.
    """
    row = {
        "card_id": card_id,
        "decision": decision,
        "reviewed_at": datetime.now().isoformat(timespec="seconds"),
        "note": note,
        **extra,
    }
    os.makedirs(SIGNALS_DIR, exist_ok=True)
    with open(DECISIONS_PATH, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return row


def load_decisions(path: str | None = None, *, dedupe: bool = True) -> dict[str, dict]:
    """Read the log → {card_id: last_decision_row}. Missing file → {}."""
    path = path or DECISIONS_PATH
    if not os.path.exists(path):
        return {}
    latest: dict[str, dict] = {}
    rows: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not dedupe:
        return {i: r for i, r in enumerate(rows)}  # index-keyed full history
    for r in rows:
        cid = r.get("card_id")
        if cid:
            latest[cid] = r
    return latest


def decided_ids(path: str | None = None) -> set[str]:
    """Card ids that already have a decision (pass or promote)."""
    return set(load_decisions(path).keys())


if __name__ == "__main__":
    d = load_decisions()
    print(f"Decisions: {DECISIONS_PATH}")
    print(f"  {len(d)} decided card(s)")
    for cid, row in list(d.items())[:10]:
        print(f"  {row.get('decision','?'):8} {cid}")
