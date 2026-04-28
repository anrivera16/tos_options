# GEX Project — Things to Fix

Tracking list of issues, corrections, and follow-ups identified during the
audit review and 15-min report design discussion.

Status legend: `[ ]` open · `[x]` done · `[~]` in progress · `[?]` needs decision

---

## Corrections to the audit report itself

- [x] **Audit section 10, "Minor Note #4" is wrong — SPX is $100, not $250.**
  The audit claims standard SPX options have a 250x multiplier and that the
  code's `CONTRACT_MULTIPLIER = 100` underestimates SPX GEX by 2.5x. This is
  incorrect. Per Cboe SPX product specs, standard SPX options use a $100
  per-index-point multiplier — the same as SPY and XSP. The 250x figure is
  /ES futures, not SPX options. **No code change needed**, but the audit doc
  should be updated to remove this note so it doesn't mislead future readers.

---

## Real items from the audit's "Minor Notes"

- [x] **Volume-weighted GEX as an alternative view.**
  Currently OI-only. Add a `weighting` parameter to the aggregation path
  (`oi` | `volume`) so a volume-weighted snapshot can be computed alongside
  the OI-weighted one. Useful as a faster intraday signal — volume reflects
  what's trading *today*, OI reflects yesterday's positioning. Don't replace
  OI; add as a parallel field on the snapshot.

- [x] **Deduplicate `estimate_gamma_flip` between `calculations.py` and
  `chart.py`.** Both modules have independent flip-finding logic with the
  same formula. Move to `calculations.py` as the single source, have
  `chart.py` import it. Low priority but easy win, and prevents the two
  copies from drifting apart.

- [x] **Document the signed-`put_gex` convention.**
  In `aggregates_by_strike`, `put_gex` values are stored as negatives.
  Some downstream consumers (and the skill docs) compensate with `ABS()`,
  others don't. Add a comment block to `storage.py` and a note to the
  skill README making the convention explicit, so future queries don't
  accidentally double-flip the sign.

---

## Schwab data-source caveats (not bugs, but worth surfacing in code)

- [x] **Make OI-staleness explicit in the data model.**
  Schwab's option chain refreshes greeks and underlying intraday, but OI is
  end-of-day. At 15-min cadence this means bar-to-bar Net GEX changes are
  driven by spot/greek movement re-pricing yesterday's OI — not by
  positioning shifts. Add a `oi_as_of` timestamp field on `snapshots` (even
  if it's just "previous close") so reports can label what's actually
  changing. Consider a `is_intraday_oi_estimate` flag for the future when
  volume-derived OI estimates get added.

- [x] **Add an underlying-price source field to snapshots.**
  `flatten_option_chain` resolves underlying price via priority chain
  (contract → quote → chain). Useful for debugging stale data to know which
  source actually populated the spot value on a given snapshot. Cheap to
  add: just store the source string alongside the price.

---

## 15-minute report — implementation TODOs

- [ ] **Add a `bar_alerts` table.**
  Schema: `(snapshot_id FK, ticker, alert_type, payload_json, created_at)`.
  Populated by the report generator on each bar. Becomes the journaling
  artifact and feeds the alert-format output. Don't put alerts in the
  snapshots table — they're a derived view, not raw state.

- [ ] **Define alert-firing rules as configurable thresholds.**
  Per-ticker config (SPX needs tighter thresholds than single names):
  - regime change (after hysteresis) — once per change
  - gamma flip migration > X% of spot
  - spot crossed flip
  - spot broke a top-3 wall (close-confirmed, not intrabar wick)
  - top wall changed strikes
  - 0DTE Net GEX sign change
  - |Δ Net GEX| > 25% bar-over-bar

- [ ] **Build `cli.py report` subcommand.**
  Flags: `--watchlist <name>`, `--format html|alerts|json`, `--ticker <sym>`
  for drill-down view. HTML format produces dashboard grid, alerts format
  produces terse single-bar log, json format for piping.

- [ ] **Snapshot timing offset.**
  Run on `:00, :15, :30, :45` with a 30–60s offset so Schwab data settles.
  Skip the 9:30 bar (open noise) and the 15:45/16:00 bars (close auction).
  Configurable, but those should be the defaults.

- [ ] **Watchlist config file format.**
  Probably YAML or TOML — `watchlists/default.yml` with per-ticker
  thresholds and a `tickers: [...]` list. Avoid hardcoding in `cli.py`.

- [ ] **HTML dashboard layout.**
  Top: market context strip (SPX spot, regime, flip distance, 0DTE GEX, VIX).
  Middle: grid with one row per ticker, columns for spot/regime/Net GEX/
  Δ vs prior/flip/dist-to-flip/walls/alerts. Sorted by alert presence then
  |Δ Net GEX|. Drill-down via row click loads the full single-ticker view.
  Footer: alert log for the current bar.

- [ ] **Auto-refresh meta tag on the HTML output.**
  `<meta http-equiv="refresh" content="900">` so the dashboard reloads every
  15 minutes if left open in a browser. Make it configurable / disableable.

---

## Open questions

- [?] **Watchlist composition.**
  Are the 5–15 names mostly large-cap liquid (AAPL, NVDA, TSLA, MSFT) or
  mixed including thinner names? Affects how aggressive the alert
  thresholds should be — single names with thin chains have noisier wall
  data than SPX/SPY/QQQ.

- [?] **Where does the report runner live?**
  Options: (1) extend `cli.py` and trigger via local cron, (2) standalone
  long-running scheduler that loops every 15 min, (3) manually triggered.
  Affects whether we need a daemon, a systemd service, or just a cron line.

- [?] **Alert delivery channel.**
  In addition to writing to the `bar_alerts` table and printing to stdout,
  do we want desktop notifications, a Slack/Discord webhook, or just the
  log file? Trivial to add later but worth deciding before the alert format
  is locked in.

---

## Nice-to-haves (not blockers)

- [ ] **Backfill script for historical snapshots.**
  If we want to compute Δ-vs-prior-bar trends over a multi-day window for
  pattern recognition, having a one-shot replay against the existing
  `snapshots` table would let us A/B-test alert thresholds without waiting
  for live data.

- [ ] **Per-ticker baseline IV.**
  Useful context column: today's front-month IV vs. its trailing 20-day
  average. Cheap with the existing `iv_term.py` queries and adds a lot of
  context to "is this a high-vol environment for this name."

- [ ] **POP estimate sanity-check the 0.35–0.75 bound.**
  Tests cover that POP stays in this range, but the range itself was
  presumably picked empirically. Worth re-validating against a few months
  of live data once it's running, in case the bounds need to widen for
  certain regime types.
