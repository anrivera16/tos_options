# Trade Review Kanban — Build Plan

The nightly review board that turns generated signals into **kept or killed**
decisions, and grows the survivors into living trade documents. This is the
**Decide → Commit** stage that `PIPELINE.md` marks as the unbuilt manual half of
the loop — built as a board instead of left in your head.

**Status:** **all 4 phases built & verified (2026-06-14).** Registry + card model
→ 15 cards; decision log + seeder w/ live GEX chart (no-clobber); Flask board
(promote/pass/move drive the files); weekly review joins `decisions.jsonl` for
passed-vs-promoted edge (join selftested — real numbers fill once outcomes mature
~2026-06-24). This doc is the spec + phased build process; each phase stands alone.

---

## 1. What this is (and what it is not)

A local kanban board where every signal the generators emit shows up as a card.
You review cards nightly, **discard most**, **promote a few**, and the promoted
ones become permanent markdown trade documents you write into for the life of
the trade and mine afterward.

- It is **not** a new signal source. It measures and acts on the ones you have.
- It is **not** Notion or a SaaS board. Everything is local, plain-text,
  git-versioned, AI-readable. (Notion can come later as a *one-way phone mirror*;
  the files stay the source of truth — see §10.)
- It **is** the manual `Decide → Commit` stage, and it back-fills real decision
  data (`decisions.jsonl`) into the edge measurement, keyed on `signal_id`.

It hangs off the existing `signal_id` spine (`PIPELINE.md` §4). Every card is a
`signal_id`; every decision and document joins back on it.

---

## 2. Design decisions (the rationale, so we don't relitigate)

| Decision | Why |
|---|---|
| **Color = source/strategy** | Lets new experiments and old features coexist on one board — a new strategy is just a new color. Conviction/direction ride as secondary badges. |
| **Board is a permanent fixture; features are pluggable** | Adding/retiring a strategy = one line in `sources.yaml`. The board never changes. |
| **Inbox cards are virtual, rendered from `signals.jsonl`** | ~25–30 signals/night → a file-per-signal is thousands/year of throwaway files. Render on demand instead; nothing accumulates. |
| **A file is born on *promote*, not on generate** | The md is a *living document you author*, not a disposable render. Only the handful you act on earn a file → dozens/year, not thousands. |
| **Discards are soft — state, not deletion** | `forward_scorer` grades **every** signal regardless of your decision. Passed signals are the control group that answers "am I a good filter, or do I toss winners?" — the highest-value behavioral question. Never hard-delete them. |
| **Live card's lane lives in its own md frontmatter** | Only a handful are ever in flight; frontmatter `status:` is git-diffable and hand-editable. Kills the need for a separate `board_state.json`. |
| **JSONL only for append-only facts/events; md for living docs** | `signals.jsonl`/`outcomes.jsonl`/`decisions.jsonl` are immutable streams (JSONL is right). A trade document mutates over its life (md is right). Don't make one tool do both jobs. |
| **Custom HTML + Flask, not a kanban library** | Four columns and colored cards don't justify an npm/React build chain. ~150 lines of hand-written HTML + native drag, matching how `weekly_review.py` already emits HTML. |

---

## 3. Storage model

Three honest pieces. Nothing else.

| Store | Path | Shape | Role |
|---|---|---|---|
| **Signal ledger** | `research/signals/signals.jsonl` | append-only JSONL | machine facts (exists today) |
| **Decision log** | `research/signals/decisions.jsonl` | append-only JSONL | every pass/promote event, keyed on `signal_id` (behavioral record) |
| **Trade documents** | `research/journal/<signal_id>.md` | markdown + frontmatter | the living, human-authored docs for promoted cards; lane lives in `status:` |

`decisions.jsonl` row:
```json
{"signal_id":"20260614-grade-AMZN-P245-260717","decision":"pass","reviewed_at":"2026-06-14T22:10:00","note":""}
```
`decision` ∈ `pass` | `promote`. Append-only; readers keep last-per-`signal_id`.

**There is no `board_state.json`.** Inbox is computed; in-flight lane is the md
frontmatter; everything else is history in `decisions.jsonl`.

---

## 4. Source registry

`flow_dashboard/sources.yaml` — the one file you touch to add or retire a feature.

```yaml
swing:  { label: "Swing Persistence", color: "#3b82f6", enabled: true }
grade:  { label: "Directional Grade", color: "#22c55e", enabled: true }
gex:    { label: "GEX Gameplan",      color: "#a855f7", enabled: true }
flow:   { label: "Nightly Flow",      color: "#f59e0b", enabled: false }   # experiment, parked
```

- Tag matches the `source` tag in the `signal_id` grammar (`PIPELINE.md` §4).
- `color` → card color on the board.
- `enabled: false` → stops surfacing new cards; existing history/docs untouched.

---

## 5. Card lifecycle (state machine)

```
            generate (cron)
                 │
                 ▼
        ┌──────────────────┐   pass    ┌──────────────────────────┐
        │ INBOX (virtual)  │──────────▶│ decisions.jsonl (pass)   │  ← stays scored,
        │ rendered from    │           │ no file, hidden from view│    never deleted
        │ signals.jsonl    │           └──────────────────────────┘
        └──────────────────┘
                 │ promote
                 ▼
        materialize research/journal/<signal_id>.md  (status: watching)
                 │   + append decisions.jsonl (promote)
                 ▼
        watching ──▶ open ──▶ closed        (lane = frontmatter `status:`)
          │           │          │
          you write   you write  you write
          plan        live notes the review
```

- **Inbox** = signals from the last `N` nights with **no** decision yet (computed:
  ledger minus `decisions.jsonl`). Promoting/passing removes it from Inbox
  automatically — the board self-cleans every night.
- **Promote** seeds the md (§6) and logs a `promote` event.
- **watching → open → closed** are edits to the md `status:` (by the board, or by
  hand in your editor). Closed docs live forever in `research/journal/`.

---

## 6. The trade document (seed → grow → close)

Materialized on promote, seeded with auto data, then authored by you.

```markdown
---
signal_id: 20260614-grade-AMZN-P245-260717
source: grade            # → card color
status: watching         # watching → open → closed  (the lane)
opened: 2026-06-14
ticker: AMZN
direction: -1
score: 82
parent_id: 20260614-swing-AMZN-bear
---
## Thesis        ← seeded from the signal
swing-persistence bear · net premium −$4.2M (5d persistent) · reach 0.9 · pop 41%
![gex](charts/20260614-AMZN-gex.png)

## Plan          ← you write
entry / stop / target / size / what invalidates it

## Journal       ← you append as it lives
6/15 trimmed half into the gap down…

## Exit & Review ← you write at close
what happened vs the thesis, what I'd do differently
```

**Combined cards come free:** the `parent_id` chain (thesis → contracts, plus a
`gex` signal for the same ticker/night) collapses into one seeded document.
Don't model three card types — one doc pulls whatever sources fired.

---

## 7. Components to build

| Component | Path (proposed) | Does |
|---|---|---|
| Source registry loader | `flow_dashboard/sources.py` + `sources.yaml` | read registry, map source → label/color/enabled |
| Card builder | `flow_dashboard/cards.py` | read `signals.jsonl` + `decisions.jsonl` → compute Inbox + in-flight card list; collapse `parent_id` chains |
| Artifact seeder | `flow_dashboard/seed_doc.py` | on promote: render the md (§6), call `gex_chart.py` for the PNG, write to `research/journal/` |
| Board app | `flow_dashboard/board.py` (Flask) + `templates/board.html` | serve columns/cards; `POST /decide` (pass) and `POST /promote` |
| Weekly-review join | extend `flow_dashboard/weekly_review.py` | join `decisions.jsonl` on `signal_id`: hit-rate of passed vs promoted ("am I a good filter?") |

---

## 8. Build phases

Ordered. Each is independently useful; stop after any phase and still have value.

### Phase 1 — Registry + card model (no UI) ✅ done
- `sources.yaml` + `sources.py` — registry loader, long/short tag normalization,
  grey fallback for unregistered sources, ANSI swatch for the CLI.
- `decisions.py` — read-only decision-log loader (`load_decisions` / `decided_ids`);
  card-grain keyed. Append helper deferred to Phase 2.
- `cards.py` — collapses the ledger into cards (`parent_id` → one card per
  ticker/direction/night), lead-source color/score, computed Inbox, parked
  sources dropped.
- **Acceptance ✅:** `python3 flow_dashboard/cards.py` → 29 rows collapse to 15
  cards (8 swing-only, 7 graded w/ 2 contracts each), colored by source.

### Phase 2 — Decision log + seeder (no UI) ✅ done
- `decisions.record_decision()` — append pass/promote, last-per-id dedupe.
- `seed_doc.py` — `seed_card()` materializes the §6 doc into `research/journal/`;
  **no-clobber** (never overwrites your edits); CLI `pass` / `promote` / `list`.
- GEX chart: `gex_chart.py` emits **interactive HTML, not PNG** — so the doc
  *links* the chart (best-effort; missing chart never blocks the doc). PNG
  snapshot deferred (needs headless browser — see §10).
- **Acceptance ✅:** `promote` logged the decision, seeded the md with a live
  33KB GEX chart, and dropped the card from Inbox (15→14→13); re-promote said
  "exists" and preserved a hand-added note. Test decisions cleared after.

### Phase 3 — The board UI ✅ done
- `journal.py` — NEW reader: `load_journal()` / `by_status()` parse doc
  frontmatter for the in-flight lanes; `set_status()` rewrites only the `status:`
  line (body untouched).
- `board.py` (Flask, port 5057): `GET /` renders Inbox / Watching / Open / Closed
  from `cards.py` + journal frontmatter, colored from `sources.yaml`; stateless,
  every action 303-redirects to re-read files. `POST /promote` (seed+log),
  `/decide` (pass), `/status` (move lane), `/doc/<f>` (serve md/chart).
- `templates/board.html` + `static/board.css` — dark 4-column board, per-card
  buttons (drag deferred). Run: `python3 flow_dashboard/board.py`.
- **Acceptance ✅:** board renders 15-card Inbox; promote → card to Open + doc
  seeded w/ live chart, pass → logged + dropped, lane move → frontmatter rewritten;
  all verified over HTTP + screenshot, no console errors. Test data cleared after.

### Phase 4 — Close the loop ✅ done
- `weekly_review.py` joins `decisions.jsonl` on the **card grain** (`parent_id or
  signal_id`, so a contract outcome inherits its thesis's decision): new
  **"Decision filter"** table (promote / pass / undecided) in HTML + text — does
  your nightly filter add edge?
- **Acceptance ✅:** `--selftest` on synthetic data — contract outcome resolves to
  parent's `promote`; promote hit 100% / +40% opt vs pass 0%. Real run with no
  outcomes yet renders empty without crashing; fills ~2026-06-24.

---

## 9. File map (proposed)

```
flow_dashboard/
  sources.yaml           registry: source → label / color / enabled
  sources.py             registry loader
  cards.py               compute Inbox + in-flight cards from ledger + decisions
  seed_doc.py            materialize the seeded trade md (+ gex chart png)
  board.py               Flask board app
  templates/board.html   the kanban page (colored cards, columns, drag)
  weekly_review.py       (extended) join decisions for passed-vs-promoted edge
research/
  signals/
    signals.jsonl        (exists) signal ledger
    decisions.jsonl      (new) append-only pass/promote log
  journal/
    <signal_id>.md       (new) living trade documents
    charts/<...>.png      seeded GEX charts for promoted trades
docs/
  KANBAN_BUILD.md        this document
  PIPELINE.md            the upstream signal→outcome pipeline
```

---

## 10. Deferred / future

- **Notion phone mirror.** Push promoted cards up nightly for couch review;
  files stay source of truth, Notion is one-way (plus a narrow lane write-back if
  ever wanted). Add only after Phases 1–4 work.
- **PNG chart snapshot.** `gex_chart.py` emits interactive HTML; the doc links it.
  A static PNG (for a glanceable thumbnail / portable record) needs a headless
  browser (playwright + chromium) to screenshot the HTML — heavy, so deferred.
- **Auto status nudges.** When a promoted trade's `signal_id` matures in
  `outcomes.jsonl`, surface a prompt to close + review it.
- **Journal `signal_id` link** (`PIPELINE.md` Roadmap #1). The promoted md already
  carries `signal_id`; wiring real Schwab fills in closes the behavioral loop with
  P&L.
```
