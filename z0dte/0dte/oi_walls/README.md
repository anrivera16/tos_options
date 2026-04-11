# OI Walls Live Runner

## Purpose
`python -m cli zodte oi-walls` runs a live OI-wall monitor for near-term options, then posts concise text alerts to Discord.

## Architecture
```text
CLI (zodte oi-walls)
  -> OIWallsLiveRunner (loop/interval/retry/dedupe)
    -> Massive MCP (contracts + per-contract snapshots)
      -> OI wall logic (aggregate_oi_by_strike -> classify_walls -> identify_top_walls)
        -> Discord webhook text message
```

## Prerequisites
- `MASSIVE_API_KEY` (required)
- `DISCORD_WEBHOOK_URL` (required when `--discord` and not `--dry-run`)
- Optional DB env: not required for current stateless live alert flow; only needed if you add persistence.

## CLI Usage
```bash
python -m cli zodte oi-walls --symbol SPY --interval 5 --count 3 --dry-run
python -m cli zodte oi-walls --symbol SPY --interval 15 --discord --top-n 3
python -m cli zodte oi-walls --symbol SPY --count 1 --dry-run --debug
```

## Data Mapping (Massive -> OI Wall Inputs)
- `/v3/reference/options/contracts`
  - `ticker` -> option contract identifier for snapshot calls
  - `strike_price` -> `strike`
  - `contract_type` -> `put_call` (`CALL`/`PUT`)
  - `expiration_date` -> `dte`
- `/v3/snapshot/options/{underlying}/{optionContract}`
  - `open_interest` -> `open_interest`
  - `day.volume` -> `total_volume`
  - `last_quote.bid/ask` -> `bid`/`ask`
  - `day.close` -> `last`
  - `greeks.delta/gamma` -> optional enrich fields
- `/v2/aggs/ticker/{symbol}/prev`
  - `results[0].c` -> spot price

## Discord Alert Contract
Sections:
1. Header: symbol + ET timestamp + spot
2. Top call walls
3. Top put walls
4. Pin range
5. Quick bias line

Example:
```text
OI Walls | SPY | 2026-04-10 09:35:00 ET
Spot: $517.22
Top Call Walls
- 520: OI 12,440 (+0.54%)
Top Put Walls
- 515: OI 10,982 (-0.43%)
Pin Range 515 - 520 (width 5, 0.97%)
Bias upside pressure (calls 18,002 vs puts 13,004)
```

## Operational Limits / Rate Control
- Contracts are filtered to near-spot strikes (`±5%`) and capped for runtime control.
- Reference-contract endpoint supports pagination (`next_cursor`).
- Snapshot/reference calls use retry with exponential backoff and pacing delay.
- Duplicate Discord spam is reduced via in-memory previous-message dedupe.

## Failure / Retry Behavior
- API calls retry up to 4 attempts with backoff.
- Empty/malformed payloads are skipped safely.
- Loop continues on iteration-level exceptions and tracks error count.

## Validation
Dry-run (console only):
```bash
python -m cli zodte oi-walls --symbol SPY --interval 5 --count 1 --dry-run
```
Live Discord:
```bash
python -m cli zodte oi-walls --symbol SPY --interval 15 --discord --count 1
```
Expected:
- Console prints formatted OI-wall report each iteration.
- Discord receives same text when enabled and changed from previous message.

## Troubleshooting
- Auth failures: verify `MASSIVE_API_KEY` is set in shell/env.
- Empty contracts: check market hours/symbol validity; widen strike window in code if needed.
- Discord 4xx/5xx: verify `DISCORD_WEBHOOK_URL`, channel permissions, and webhook health.
