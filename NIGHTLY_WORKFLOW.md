# Nightly Stock Review Workflow

End-of-day process to evaluate setups before the next market open.
Each phase is verified working before being documented here.

Environment:
- Mac (laptop) runs commands locally
- Desktop runs the Docker stack (Postgres on `100.82.57.80:5433` over Tailscale)
- `.env` at repo root holds `DATABASE_URL`, Schwab keys, Discord webhook
- Worktree note: symlink `.env` from main checkout if missing
  (`ln -s /Users/arivera/projects/tos_options/.env .env`)

Run order: 1 → 2 → 3 → 4 → 5. Total ~30–45 min.

---

## Phase 1 — System health check

**Goal:** confirm the desktop scraper has fresh end-of-day data before
trusting any of it. Verifies DB reachability over Tailscale, latest
snapshot age, and per-symbol coverage.

```bash
python3 scripts/status_check.py --remote-db
```

Connects directly to `DATABASE_URL` (desktop Postgres over Tailscale),
no Docker needed. Prints snapshot counts, freshness, per-symbol
breakdown, and auth token status.

**Pass criteria:**
- Latest snapshot age < ~12 hours on a market day
  (or last Friday's close if running on a weekend)
- SPY, QQQ, $SPX present with similar snapshot counts (1000+ over 7d)
- `option_contracts` count > 1M

**Verified 2026-05-04:** DB reachable over Tailscale. Latest snapshot
2026-05-01 23:55 UTC (Friday close), 11,822 snapshots, 4.5M contracts.
SPY / QQQ / $SPX all at 1,201 snaps over the trailing 7d window.

**If it fails:**
- Cannot connect → desktop offline or Tailscale down. Wake desktop,
  run `docker compose up -d db scraper-watch spread-hunter` on it.
- Stale > 24h on a market day → Schwab auth likely expired:
  `docker compose run --rm cli auth` on desktop, paste callback URL fast.
- Missing symbols → check `config/dynamic_tickers.json` and the
  universe-scanner service.

---

## Phase 2 — Universe refresh

**Goal:** know which individual names (beyond SPY/QQQ/$SPX) have
fresh chain data to review tonight. Two paths depending on whether
Schwab auth is alive on the Mac.

### Path A — Live scan (preferred, when Schwab auth is valid)

```bash
python3 scripts/universe_scanner.py --scan --top 8 --save
```

Saves the top picks to `config/dynamic_tickers.json`; the desktop
scraper auto-loads that file on its next cycle and starts pulling
chains for those names. Picks are also posted to Discord.

**Auth requirement:** Schwab OAuth refresh token (under
`~/.schwabdev/` on Mac, `/root/.schwabdev` on desktop) must be valid.
Refresh tokens expire every 7 days; access tokens every 30 minutes.

If the call returns 401 / `unsupported_token_type`, re-auth:

```bash
# from desktop (where the scraper container holds the durable tokens)
docker compose run --rm cli auth          # prints URL — open in browser
docker compose run --rm cli auth --prompt # paste callback URL within 30s
docker compose restart scraper-watch scanner-watch spread-hunter
```

### Path B — DB-derived universe (fallback, no API calls)

When Schwab auth is dead and you just want to know what's reviewable
right now, query the DB for symbols actually scraped in the last 5
trading days:

```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os, psycopg
conn = psycopg.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('''
    SELECT symbol, COUNT(*) AS snaps,
           MIN(captured_at)::date AS first_seen,
           MAX(captured_at)::date AS last_seen,
           AVG(underlying_price)::numeric(10,2) AS avg_px
    FROM snapshots
    WHERE captured_at >= NOW() - INTERVAL '5 days'
      AND symbol NOT IN ('SPY','QQQ','\$SPX')
    GROUP BY symbol ORDER BY last_seen DESC, snaps DESC
''')
print(f'{\"SYM\":<8} {\"SNAPS\":>6} {\"FIRST\":<12} {\"LAST\":<12} {\"PX\":>10}')
for r in cur.fetchall():
    print(f'{r[0]:<8} {r[1]:>6} {str(r[2]):<12} {str(r[3]):<12} {r[4]!s:>10}')
conn.close()
"
```

**Pass criteria:**
- 5–15 individual names returned (not just indexes)
- Top names have 100+ snapshots over the window (= active scraping)
- `last_seen` matches the latest scraper cycle from Phase 1

**Verified 2026-05-04:** Path A failed (refresh token expired
2026-04-30). Path B returned 33 names. Top active: PLUG, GOOG, BYND,
GOOGL, META, QCOM, INTC, NVDA, NVD, RBLX (each with 100+ snaps).
`config/dynamic_tickers.json` last updated 2026-04-24, so the
on-disk file is stale — DB query is the source of truth.

## Phase 3 — Regime read on SPY/QQQ

**Goal:** before looking at any individual ticker, fix the macro frame:
IV term shape, gamma flip level, and the major OI walls. Three numbers
to write down per index.

### 3a. IV term structure

```bash
python3 -m cli iv-term --symbol SPY
python3 -m cli iv-term --symbol QQQ
```

Reads from the latest snapshot. Default puts at the ATM strike.
Output shows IV per DTE, flags inversions, and prints
near-vs-far backwardation. Add `--matrix` for the full strike x DTE
heat-grid, or `--delta 0.20` to anchor on a 20-delta put instead
of strike.

**What to record:**
- Term shape: contango (far > near) = quiet; backwardation
  (near > far) = stress
- Highest-IV DTE → best DTE to *sell* premium
- Any "inversion" tag = front-month risk premium

**Verified 2026-05-04 on SPY (close 2026-05-01):** spot $720.15.
DTE-0 IV 11.1%, DTE-14 IV 12.7%. Mild backwardation in the front
3 days (DTE-3 dipped to 8.3%), then steady contango out to DTE-14.
Read: market expects a quiet open, reverts to normal vol curve
within a week. Best DTE to sell = 14 (12.7% IV).

### 3b. Gamma flip + OI walls (direct SQL)

`cli exposure history` is broken against postgres (uses sqlite-style
`?` placeholders — see Known Issues at bottom). Query the
aggregates table directly:

```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os, psycopg
conn = psycopg.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

cur.execute('''SELECT id, captured_at, underlying_price
               FROM snapshots WHERE symbol=%s
               ORDER BY captured_at DESC LIMIT 1''', ('SPY',))
sid, captured, spot = cur.fetchone()
print(f'SPY  snapshot {sid}  {captured}  spot \${spot:.2f}')

lo, hi = spot * 0.95, spot * 1.05
cur.execute('''SELECT strike, net_gex, open_interest_total, volume_total
               FROM aggregates_by_strike
               WHERE snapshot_id = %s AND strike BETWEEN %s AND %s
               ORDER BY open_interest_total DESC NULLS LAST LIMIT 10''',
            (sid, lo, hi))
print(f'\\nTop 10 OI walls (+/- 5%):')
print(f'  {\"STRIKE\":>8}  {\"NET_GEX\":>14}  {\"OI\":>10}')
for r in cur.fetchall():
    print(f'  {r[0]:>8.2f}  {r[1]:>14,.0f}  {r[2]:>10,.0f}')

cur.execute('''SELECT strike, net_gex FROM aggregates_by_strike
               WHERE snapshot_id = %s AND strike BETWEEN %s AND %s
               ORDER BY strike''', (sid, lo, hi))
rows = cur.fetchall(); prev = None
print('\\nGamma flip levels:')
for strike, gex in rows:
    if prev and ((prev[1] or 0) > 0) != ((gex or 0) > 0):
        print(f'  flip between \${prev[0]:.2f} and \${strike:.2f}')
    prev = (strike, gex)
conn.close()
"
```

**What to record per index:**
- Spot at last close
- Top 3 walls by OI (these are pinning magnets / break levels)
- Gamma flip strike (above = mean-reverting / pinning, below = momentum)

**Verified 2026-05-04 on SPY:** spot $720.15. Walls: $710 (145k OI),
$715 (77k), $720 (73k), $725 (60k). Flip between $720 and $721 —
spot is sitting *right on* the flip. Read: any drift below $720
flips dealers short gamma → momentum regime. The $710 wall is the
next big magnet on a flush.

### 3c. Chart overlay (optional, requires live Schwab auth)

```bash
python3 -m cli chart post --symbol SPY --days 14 --discord
```

Renders the GEX-with-price overlay and posts the PNG to the Discord
webhook. Requires a live Schwab access token — fails with 401 if
auth is expired (re-auth per Phase 2 Path A). Skip on auth failure
and rely on 3a + 3b.

## Phase 4 — Spread candidate hunt

**Goal:** generate ranked spread candidates from the latest snapshot
and pick the one (or two) that match the proven config from
`workflow.md` (1.5% OTM bull put credit, 5–9 DTE, $5 width, 50% SL,
75% PT, no overlap).

Two tools, same DB. Use **spread_hunter** for breadth (all spread
types, ranked) and **run_pipeline** for narrow signal-quality
verdict aligned with backtested rules.

### 4a. Spread Hunter — broad candidate scan

```bash
python3 scripts/spread_hunter.py --once \
    --tickers SPY QQQ \
    --type credit \
    --min-dte 5 --max-dte 14 \
    --min-roi 20 \
    --no-trend-filter \
    --iv-rank-min 0
```

**Notable flags:**
- `--type credit` → bull put + bear call only (skip iron condor / fly / calendar)
- `--no-trend-filter` → bypass SMA(20) when DB has <20 days of history
- `--iv-rank-min 0` → don't filter on IV rank (gate it manually after seeing the list)
- `--verbose` → print the active SignalFilter config
- Add `--discord` to also push to webhook

**What you get:** ranked table with short/long strikes, DTE,
credit, max loss, BE, ROI%, net delta, net theta, OI, bid/ask
spread%, composite score.

**Verified 2026-05-04 on SPY (close 2026-05-01):** 17 bear call
candidates, 0 bull put. Top score: short 727 / long 732, 6 DTE,
$1.00 credit, $4.00 max loss, 25.0% ROI, -0.353 theta, 907 OI on
short. The bear-call lean is consistent with spot ($720) sitting
on the gamma flip — the algo prefers selling resistance at $725-727
in that regime.

### 4b. Algo Pipeline — backtested-config verdict

```bash
python3 scripts/run_pipeline.py --config full_stack
```

Single-name (SPY only by default) pipeline that runs the 9
filter modules: generators → trend → IV rank → earnings →
wall_detector → wall_proximity → scoring → stop_loss → risk_manager.
Output prints the count rejected at each stage and *why*.

This is the gating tool, not the discovery tool. If full_stack
returns "no trade", the proven strategy says skip tomorrow.
If it returns a candidate, that's *the* trade.

**Verified 2026-05-04:** 8 raw signals → trend pass → IV gate
**closed (15% rank, min 30%)** → all 8 rejected. Plus 1 hit on
the $710 wall proximity filter. Verdict: **no trade for tomorrow's
open under the proven config.** IV is too low to justify the
risk; wait for IV rank > 30% before selling.

### 4c. Cross-check candidates against Phase 3 walls

For every Phase 4a candidate that passes Phase 4b (or that you'd
take on a less strict config), validate against the Phase 3 GEX:

- Short strike should NOT sit within ~1% of a major OI wall
  (the algo flags these as `wall_proximity` rejections automatically)
- For bull puts: short strike should be *below* spot AND below the
  gamma flip
- For bear calls: short strike should be *above* spot AND above any
  call wall

The 727/732 bear call from 4a passes: $727 is above the $725 wall
(not stacked on it) and well above the gamma flip ($720-721).

## Phase 5 — Gameplan note

**Goal:** commit a decision on paper before tomorrow's open, so the
morning is execution-only — not re-deciding under gap pressure.

### 5a. (Optional) Format trade log via script

```bash
python3 scripts/tos_trade_log.py
```

Prints the top 3 bull put / bear call / iron condor candidates with
OCC symbols ready to paste into TOS.

**Known issue (2026-05-04):** crashes with `IndexError` when
`bull_put_credit` returns no candidates. It assumes both sides have
≥ 1 candidate. Skip this script when the regime is one-sided
(today's data triggers the bug — 0 bull puts, 17 bear calls).
Construct OCC symbols manually from Phase 4 output until fixed.

### 5b. Manual OCC symbol construction

OCC format: `<UNDERLYING>_<MMDDYY><P|C><strike-in-thousands-8digits>`

Example for the top Phase 4a candidate (SPY 727/732 bear call,
exp 2026-05-07):
```
short call: SPY  _050726C00727000   (sell)
long  call: SPY  _050726C00732000   (buy)
```

In TOS: Trade tab → ticker SPY → option chain → 7 May 26 expiry →
right-click 727 call → SELL → Vertical → 732 long leg auto-added.

### 5c. Gameplan template

Save tonight's plan as `out/gameplan_YYYY-MM-DD.md` (file written
manually — there's no scaffolder yet). Template:

```markdown
# Gameplan — open of <next-trading-day>
generated <ISO-timestamp>, snapshot at <Phase-1 latest>

## Macro frame (Phase 3)
- SPY spot $___  IV-DTE0 ___%  IV-DTE14 ___%  shape: contango / backwardation
- Gamma flip: $___    Walls: $___ / $___ / $___
- Regime: pinning / momentum

## Universe (Phase 2)
Active names: ___, ___, ___ (top 5 by snap count)

## Primary trade
- Strategy: bull-put / bear-call / no-trade
- Underlying: SPY
- Short: <strike> <P|C>  Long: <strike> <P|C>
- Expiration: <date> (DTE <n>)
- Credit target: $___    Max loss: $___
- ROI%: ___    Short delta: ___
- OCC short: SPY_<MMDDYY><P|C><strike8>
- OCC long:  SPY_<MMDDYY><P|C><strike8>

## Exits (pre-baked, no improvising)
- Profit target: 75% of credit  ($___ buyback)
- Stop loss: 50% of max loss   ($___ debit)
- Time stop: close on expiry day, 30 min before close

## Skip-it conditions (don't enter if any are true at 9:30)
- SPY gaps > 1% in either direction
- VIX > 25 or up > 3 points overnight
- FOMC / CPI / jobs print scheduled this week within DTE
- Algo pipeline (Phase 4b) flipped to "no trade"
- An existing position is open (no overlap rule)

## Sizing
- Risk per trade: 2% of bankroll = $___ max loss
- Contract count: floor($___ / max_loss_per_contract) = ___

## Notes
- ___
```

**Verified 2026-05-04:** filling this template against today's
data produces a "no-trade" gameplan: Phase 4b said no (IV rank 15%
too low), and Phase 4a was bear-call only (the proven backtested
config is bull-put). Sit out the open, re-check tomorrow night.

---

## Known Issues (uncovered during walk-through)

✅ **FIXED — `scripts/status_check.py`** — added `--remote-db` / `-r`
flag. Skips Docker, connects to `DATABASE_URL` directly over Tailscale.
Use from Mac: `python3 scripts/status_check.py --remote-db`

✅ **FIXED — `cli exposure history` against postgres** — `cli.py` now
uses the `_ph()` helper for placeholder compatibility and `cursor.description`
for row-to-dict conversion. Works with both sqlite and postgres.

✅ **FIXED — CLI commands not auto-loading `.env`** — `cli.py` now calls
`load_dotenv()` at module load. `gex/iv_term.py` `DEFAULT_DB` and
`gex/storage.py` `DEFAULT_DB_PATH` now both read `DATABASE_URL` from env.
No more `set -a; source .env; set +a` needed.

✅ **FIXED — `scripts/tos_trade_log.py` IndexError** — quick-reference
section now guards with `if scored["bull_put_credit"]:` / `if ics:`
before accessing `[0]`. Prints "no candidates" cleanly.

4. **Worktree missing `.env`** — symlink from main checkout (one-time):
   `ln -s /Users/arivera/projects/tos_options/.env .env`

5. **`scripts/universe_scanner.py`** — needs live Schwab API. When
   the refresh token (7-day expiry) is dead, falls back to no-op.
   Re-auth from the desktop, or use Phase 2 Path B (DB query) for
   tonight's universe.

6. **Algo pipeline trend filter** — needs ≥ 20 days of price history
   in the DB to compute SMA(20). With < 20, it logs a warning and
   becomes a pass-through (neutral). Bypass with `--no-trend-filter`
   in spread_hunter.

---

## One-shot script (TODO)

Once the issues above are fixed, wrap Phases 1–4 into a single
`scripts/nightly.sh` that runs them in order, writes Phase 5
template to `out/gameplan_YYYY-MM-DD.md`, and posts a summary to
Discord. Not built yet — verify each phase independently first.
