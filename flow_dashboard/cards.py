#!/usr/bin/env python3
"""Card model — collapse the raw signal ledger into review cards.

A *card* is one ticker/direction/night idea: the thesis (swing) with its graded
contracts (and, later, a gex gameplan) collapsed underneath it via ``parent_id``.
You review cards, not rows. Each card is identified by its **card_id** — the
thesis-grain signal_id (``20260614-swing-AMZN-bear``), which is also the key the
decision log writes against.

The Inbox is computed, never stored: signals from the last ``INBOX_NIGHTS`` that
have no decision yet. Pass/promote a card and it drops out automatically. This is
what keeps the board self-cleaning and the disk empty of throwaway files.

This module is pure read: ledger + registry + decisions → cards. No network.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, timedelta

from decisions import load_decisions
from signal_log import _dir_tag, load_signals
from sources import Source, ansi_swatch, load_registry, source_for

INBOX_NIGHTS = 5  # how many trailing calendar days of signals to surface

# Which source "leads" a multi-source card — i.e. whose color/score represents it.
# Most tradeable first: a graded contract beats a bare thesis.
LEAD_PRIORITY = ("grade", "gex", "swing", "flow")


@dataclass
class Card:
    card_id: str                       # thesis-grain signal_id; decision key
    date: str                          # YYYY-MM-DD
    ticker: str
    direction: int                     # +1 bull / -1 bear
    lead_tag: str                      # short source tag that colors the card
    source: Source                     # resolved registry entry for lead_tag
    sources: list[str]                 # all short tags present on the card
    score: float | None                # representative score (best contract, else thesis)
    thesis_score: float | None
    sector: str | None
    iv_rank: float | None
    earnings_flag: bool
    contracts: list[dict] = field(default_factory=list)  # grade rows under the thesis
    member_ids: list[str] = field(default_factory=list)  # every signal_id in the card

    @property
    def side(self) -> str:
        return _dir_tag(self.direction)

    def __str__(self) -> str:
        sw = ansi_swatch(self.source.color)
        score = f"{self.score:4.0f}" if self.score is not None else "  · "
        srcs = "+".join(self.sources)
        earn = " ⚠earn" if self.earnings_flag else ""
        ncon = f" · {len(self.contracts)} contract(s)" if self.contracts else ""
        return (f"{sw} {score}  {self.ticker:6} {self.side:4} "
                f"[{srcs:11}] {self.source.label}{ncon}{earn}")


def _thesis_id(row: dict) -> str:
    """The card a row belongs to: its parent thesis if any, else itself."""
    return row.get("parent_id") or row.get("signal_id") or ""


def _lead(tags: set[str]) -> str:
    for t in LEAD_PRIORITY:
        if t in tags:
            return t
    return next(iter(tags)) if tags else "?"


def build_cards(
    *,
    nights: int = INBOX_NIGHTS,
    today: date | None = None,
    registry: dict[str, Source] | None = None,
    include_disabled: bool = False,
) -> list[Card]:
    """Collapse the ledger into cards within the trailing ``nights`` window.

    Returns ALL cards in window (decided or not); callers filter to Inbox via
    ``inbox_cards``. Cards whose lead source is parked (``enabled: false``) are
    dropped unless ``include_disabled``.
    """
    registry = registry if registry is not None else load_registry()
    today = today or date.today()
    cutoff = today - timedelta(days=nights)

    rows = load_signals()
    groups: dict[str, list[dict]] = {}
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        try:
            if date.fromisoformat(d) < cutoff:
                continue
        except ValueError:
            continue
        groups.setdefault(_thesis_id(r), []).append(r)

    cards: list[Card] = []
    for card_id, members in groups.items():
        thesis = next((m for m in members if m.get("signal_id") == card_id), None)
        contracts = [m for m in members
                     if m.get("source") == "directional_grader"]
        tags = {source_for(m["source"], registry).tag for m in members}
        lead_tag = _lead(tags)
        src = source_for(lead_tag, registry)
        if not src.enabled and not include_disabled:
            continue

        rep = thesis or members[0]
        contract_scores = [c["score"] for c in contracts if c.get("score") is not None]
        score = max(contract_scores) if contract_scores else rep.get("score")

        cards.append(Card(
            card_id=card_id,
            date=rep.get("date", ""),
            ticker=rep.get("ticker", "?"),
            direction=int(rep.get("direction") or 0),
            lead_tag=lead_tag,
            source=src,
            sources=sorted(tags),
            score=score,
            thesis_score=(thesis or {}).get("score"),
            sector=rep.get("sector"),
            iv_rank=rep.get("iv_rank"),
            earnings_flag=bool(rep.get("earnings_flag")),
            contracts=sorted(contracts, key=lambda c: -(c.get("score") or 0)),
            member_ids=[m.get("signal_id") for m in members if m.get("signal_id")],
        ))

    # Newest first, then strongest score.
    cards.sort(key=lambda c: (c.date, c.score or 0), reverse=True)
    return cards


def inbox_cards(**kwargs) -> list[Card]:
    """Cards with no decision yet — the nightly review queue."""
    decided = set(load_decisions().keys())
    return [c for c in build_cards(**kwargs) if c.card_id not in decided]


if __name__ == "__main__":
    cards = build_cards()
    queue = inbox_cards()
    decided = len(cards) - len(queue)
    print(f"\n{len(cards)} card(s) in last {INBOX_NIGHTS} nights "
          f"· {len(queue)} in Inbox · {decided} already decided\n")
    for c in queue:
        print(c)
    if not queue:
        print("  (Inbox empty)")
    print()
