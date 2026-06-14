#!/usr/bin/env python3
"""Journal reader — surface the in-flight trade docs for the board's columns.

Phase 2's seeder *writes* `research/journal/<card_id>.md`. The board needs to
*read* them back to fill the Watching / Open / Closed columns, and to move a card
between them. This module is that thin reader:

  • ``load_journal()``  → light records parsed from each doc's frontmatter.
  • ``set_status()``    → rewrite just the ``status:`` line, leaving your authored
                          body (Plan / Journal / Exit) untouched.

The md frontmatter is the source of truth for an in-flight card's lane — there is
no separate board-state store (see docs/KANBAN_BUILD.md §3).
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass

import yaml

from signal_log import PROJECT_ROOT

JOURNAL_DIR = os.path.join(PROJECT_ROOT, "research", "journal")
STATUSES = ("watching", "open", "closed")  # the lane order


@dataclass
class JournalCard:
    card_id: str
    ticker: str
    source: str          # short tag (drives color, same as Inbox)
    status: str          # watching / open / closed
    direction: int
    score: float | None
    opened: str | None
    path: str

    @property
    def side(self) -> str:
        return "bull" if self.direction > 0 else "bear" if self.direction < 0 else "flat"


def _parse_frontmatter(text: str) -> dict:
    """Return the YAML frontmatter dict from a doc, or {} if absent/malformed."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return {}


def load_journal(path: str | None = None) -> list[JournalCard]:
    """Read every journal doc into a light record. Missing dir → []."""
    base = path or JOURNAL_DIR
    out: list[JournalCard] = []
    for p in sorted(glob.glob(os.path.join(base, "*.md"))):
        with open(p) as f:
            fm = _parse_frontmatter(f.read())
        if not fm.get("signal_id"):
            continue
        score = fm.get("score")
        out.append(JournalCard(
            card_id=fm["signal_id"],
            ticker=fm.get("ticker", "?"),
            source=fm.get("source", "?"),
            status=(fm.get("status") or "watching").lower(),
            direction=int(fm.get("direction") or 0),
            score=float(score) if isinstance(score, (int, float)) else None,
            opened=fm.get("opened"),
            path=p,
        ))
    return out


def by_status(path: str | None = None) -> dict[str, list[JournalCard]]:
    """Group in-flight cards into lane → [cards], in STATUSES order."""
    groups: dict[str, list[JournalCard]] = {s: [] for s in STATUSES}
    for c in load_journal(path):
        groups.setdefault(c.status, []).append(c)
    return groups


def set_status(card_id: str, new_status: str, base: str | None = None) -> bool:
    """Rewrite the frontmatter ``status:`` of one doc. Body is left untouched."""
    if new_status not in STATUSES:
        return False
    p = os.path.join(base or JOURNAL_DIR, f"{card_id}.md")
    if not os.path.exists(p):
        return False
    with open(p) as f:
        lines = f.readlines()

    # Only touch the first frontmatter block (between the first two '---' lines).
    in_fm = False
    fences = 0
    for i, line in enumerate(lines):
        if line.strip() == "---":
            fences += 1
            in_fm = fences == 1
            if fences == 2:
                break
            continue
        if in_fm and line.startswith("status:"):
            lines[i] = f"status: {new_status}\n"
            break
    with open(p, "w") as f:
        f.writelines(lines)
    return True


if __name__ == "__main__":
    g = by_status()
    for s in STATUSES:
        print(f"{s:9} {len(g[s])}")
        for c in g[s]:
            print(f"    {c.card_id:32} {c.ticker:6} {c.side}")
