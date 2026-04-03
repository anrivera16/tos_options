# Schwab Scripts

This directory contains Python scripts and CLI commands for:

- authenticating with the Schwab API
- fetching quotes and option-chain data
- computing gamma exposure (GEX)
- computing expanded dealer exposure analytics (GEX, DEX, VEX, TEX)
- persisting option snapshots to SQLite for historical analysis
- generating GEX overlay charts
- uploading finished PNG charts to Discord
- posting hourly text market reports to Discord

## What This Folder Does

The main workflow is:

1. read Schwab credentials from `.env`
2. call the Schwab API
3. normalize option data
4. compute exposure reports and GEX levels
5. render a chart to `out/`
6. optionally upload the PNG to Discord

The fastest daily command is `gexd`, which creates the chart and posts it to Discord in one step.

## Files In This Folder

Important files:

- `cli.py` - main command-line entry point
- `schwab_client.py` - Schwab auth and client creation
- `schwab_api.py` - quote and option-chain API helpers
- `gex.py` - GEX, DEX, VEX, TEX, rollups, and dealer regime calculations
- `storage.py` - SQLite snapshot and aggregate persistence
- `gex_price_overlay.py` - chart generation
- `discord_webhook.py` - Discord PNG upload helper
- `auth_demo.py` - standalone auth helper
- `tests/` - pytest coverage for normalization, math, storage, and CLI flows
- `out/` - generated CSV, JSON, and PNG outputs
- `.env` - local credentials and webhook config

## Requirements

- Python 3.10+
- Schwab API credentials
- Discord webhook URL if you want automatic uploads

## Setup

From the repo root:

```bash
cd python_scripts
pip install -e .
```

That installs the package in editable mode and makes the `gexd` command available in your shell environment.

## Environment Variables

Create or update `python_scripts/.env`.

Example:

```env
SCHWAB_API_KEY=...
SCHWAB_API_SECRET=...
SCHWAB_REDIRECT_URI=...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Notes:

- `.env` is a hidden file, so use `ls -a` if you do not see it
- `DISCORD_WEBHOOK_URL` is required for `discord-send`, `gex-chart-discord`, `market-report-discord`, and `gexd`

## First-Time Authentication

Run:

```bash
python auth_demo.py
```

Or use the CLI:

```bash
python -m cli auth
```

If needed, you can paste the callback URL directly:

```bash
python -m cli auth --prompt
```

## Main Commands

### 1. Fastest Daily Command

Use `gexd` for the normal workflow:

```bash
gexd
gexd SPY
gexd QQQ 15
```

Behavior:

- first argument = symbol, default `SPY`
- second argument = max GEX levels, default `10`
- default option-chain window = `30` days
- default output path = `out/<symbol>_gex_price_overlay.png`
- uploads the finished PNG to Discord

Examples:

```bash
gexd
gexd SPY 10
gexd QQQ 15
gexd IWM 12 --days 45
```

Help:

```bash
gexd --help
```

### 2. Full Python CLI Commands

Preferred grouped commands:

```bash
python -m cli auth login
python -m cli auth login --prompt
python -m cli market quote --symbol SPY
python -m cli options expirations --symbol SPY
python -m cli options fetch --symbol SPY --days 30 --output out/options.csv --json-output out/options.json
python -m cli options fetch --symbol SPY --days 30 --output out/options.csv --persist-db
python -m cli exposure gex --symbol SPY --days 30 --output out/gex.json
python -m cli exposure gex --symbol SPY --days 30 --output out/gex.json --persist-db
python -m cli analysis options --symbol SPY --days 30 --output out/options_analysis.json
python -m cli analysis options --symbol SPY --days 30 --prior-regime balanced
python -m cli analysis options --symbol SPY --days 30 --discord
python -m cli exposure history --symbol SPY --limit 5
python -m cli chart render --symbol SPY --days 30 --output out/gex_price_overlay.png
python -m cli chart render --symbol SPY --days 30 --output out/gex_price_overlay.png --discord
python -m cli chart send --file out/gex_price_overlay.png
python -m cli chart post --symbol SPY --days 30 --output out/gex_price_overlay.png
python -m cli report market
python -m cli report market --force --discord
pytest -q
```

Legacy flat commands still work for backward compatibility:

```bash
python -m cli auth
python -m cli auth --prompt
python -m cli quote --symbol SPY
python -m cli expirations --symbol SPY
python -m cli fetch-options --symbol SPY --days 30 --output out/options.csv --json-output out/options.json
python -m cli fetch-options --symbol SPY --days 30 --output out/options.csv --persist-db
python -m cli gex --symbol SPY --days 30 --output out/gex.json
python -m cli gex --symbol SPY --days 30 --output out/gex.json --persist-db
python -m cli options-analysis --symbol SPY --days 30 --output out/options_analysis.json
python -m cli options-analysis --symbol SPY --days 30 --prior-regime balanced
python -m cli options-analysis --symbol SPY --days 30 --no-discord
python -m cli gex-history --symbol SPY --limit 5
python -m cli gex-chart --symbol SPY --days 30 --output out/gex_price_overlay.png
python -m cli discord-send --file out/gex_price_overlay.png
python -m cli gex-chart-discord --symbol SPY --days 30 --output out/gex_price_overlay.png
python -m cli market-report-discord
python -m cli market-report-discord --force
pytest -q
```

### 3. Hourly Market Report To Discord

Use this command to post a text-only market update during the regular session:

```bash
python -m cli report market --discord
```

Behavior:

- posts only on weekdays at `8:30 AM CT`, `9:30 AM CT`, `10:30 AM CT`, `11:30 AM CT`, `12:30 PM CT`, `1:30 PM CT`, and `2:30 PM CT`
- add `--force` to test outside the allowed session window
- report sections are `SPX / S&P 500 Breadth` and `NASDAQ-100 Breadth`
- each section includes breadth plus top 5 volume, top 5 gainers, and top 5 losers

Example cron-style execution:

```bash
python -m cli report market --force --discord
```

## Common Workflows

### Generate a chart and upload it to Discord

Shortest version:

```bash
gexd SPY
```

Equivalent full command:

```bash
python -m cli chart post --symbol SPY --days 30 --max-levels 10 --output out/spy_gex_price_overlay.png
```

### Generate a chart locally only

```bash
python -m cli chart render --symbol SPY --days 30 --output out/gex_price_overlay.png
```

This creates a PNG in `out/` but does not upload it.

### Upload an existing PNG only

```bash
python -m cli chart send --file out/gex_price_overlay.png
```

### Export options data

```bash
python -m cli options fetch --symbol SPY --days 30 --output out/options.csv --json-output out/options.json
```

### Export GEX report JSON

```bash
python -m cli exposure gex --symbol SPY --days 30 --output out/gex.json
```

The JSON report now includes:

- `snapshot`
- `by_strike`
- `by_expiration`
- `by_dte_bucket`
- `by_bucket`
- `dealer_regime`
- `headline_gex`

`headline_gex` keeps the lightweight backward-compatible totals, while `snapshot` and `dealer_regime` provide the richer report used for persistence and validation.

`options_analysis` is a separate options-statistics layer with its own CLI command. It is no longer embedded into the default `gex` payload.

`options_analysis` adds:

- a regime classification with confidence and human-readable reasons
- explicit regime scorecards plus optional hysteresis against a prior regime
- active-strike distance gating so far OTM strikes do not dominate the output
- gamma-flip sanity filtering so implausible levels are excluded from active analysis
- data completeness scoring so missing inputs are explicit
- ranked strike and expiration focus lists with opportunity tags
- strategy fit scoring tied to the current dealer regime
- a short narrative block for downstream CLI, API, or Discord formatting

### Run standalone options analysis

```bash
python -m cli analysis options --symbol SPY --days 30
python -m cli analysis options --symbol SPY --days 30 --output out/options_analysis.json
python -m cli analysis options --symbol SPY --days 30 --prior-regime transition
python -m cli analysis options --symbol SPY --days 30 --discord
python -m cli options-analysis --symbol SPY --days 30 --no-discord
```

The grouped command is local-only by default and uses `--discord` to send the text summary to the configured Discord webhook. The legacy flat command still posts by default, and `--no-discord` keeps that legacy path local-only.

This command emits analysis-only output built from the normalized options chain and upstream exposure report, without exposing the full GEX payload as the primary interface.

The Discord summary includes:

- regime, confidence, and key levels
- top strategies with fit scores
- top strikes with opportunity tags
- top expirations with DTE context
- regime drivers and quality notes

When `--persist-db` is enabled, the same fetch writes a snapshot into `out/options_history.sqlite3` with:

- one row in `snapshots`
- normalized raw contracts in `option_contracts`
- strike aggregates in `aggregates_by_strike`
- expiry aggregates in `aggregates_by_expiry`
- DTE, moneyness, and distance-from-spot aggregates in `aggregates_by_bucket`

Snapshot history is keyed by the normalized chain symbol, so `gex-history --symbol SPY` returns persisted SPY runs consistently.

### Inspect recent persisted snapshots

```bash
python -m cli gex-history --symbol SPY --limit 10
```

## Output Files

Generated files are usually written to `python_scripts/out/`.

Typical outputs:

- `out/options.csv`
- `out/options.json`
- `out/gex.json`
- `out/options_history.sqlite3`
- `out/spy_gex_price_overlay.png`
- `out/qqq_gex_price_overlay.png`

## SQLite Schema Notes

The SQLite database created at `out/options_history.sqlite3` contains four main analytical tables:

- `snapshots` - one row per persisted CLI run, including symbol, captured time, spot price, source, and raw chain JSON
- `option_contracts` - normalized option rows with stable `underlying_price`, `snapshot_captured_at`, `expiration_date`, `dte`, and `strike`
- `aggregates_by_strike` - strike-level exposure rollups used by reports and wall analysis
- `aggregates_by_expiry` - expiry-level exposure rollups including `net_gex`, `net_dex`, `net_vex`, and `net_tex`
- `aggregates_by_bucket` - grouped rollups for DTE buckets, moneyness buckets, and distance-from-spot buckets

Typical verification commands:

```bash
sqlite3 out/options_history.sqlite3 ".tables"
sqlite3 out/options_history.sqlite3 "select id, symbol, captured_at, underlying_price, source from snapshots order by id desc limit 5;"
sqlite3 out/options_history.sqlite3 "select count(*) from option_contracts;"
sqlite3 out/options_history.sqlite3 "select count(*) from aggregates_by_strike;"
sqlite3 out/options_history.sqlite3 "select count(*) from aggregates_by_expiry;"
sqlite3 out/options_history.sqlite3 "select count(*) from aggregates_by_bucket;"
```

## Test Coverage

The local pytest suite now covers the main regression paths:

- `models.flatten_option_chain()` normalization, including chain-level spot usage and `snapshot_captured_at`
- `gex.compute_gex()` exact fixture totals
- `gex.compute_exposure_report()` reconciliation across strike, expiry, and DTE bucket rollups
- `gex.compute_gex_levels()` output shape compatibility for chart generation
- `storage.init_db()` and insert helpers for snapshots, contracts, and aggregates
- CLI smoke tests for `gex --persist-db` and `gex-history`

Run the suite from `python_scripts/`:

```bash
pytest -q
```

For a fast syntax pass:

```bash
python -m compileall .
```

## Optional Shell Function

If you want a shell wrapper instead of the installed script, add this to `~/.zshrc`:

```bash
gexd() {
  local symbol="${1:-SPY}"
  local max_levels="${2:-10}"
  cd /Users/arivera/projects/project_go/python_scripts || return 1
  python -m cli gex-chart-discord --symbol "$symbol" --days 30 --max-levels "$max_levels" --output "out/${symbol,,}_gex_price_overlay.png"
}
```

Then reload your shell:

```bash
source ~/.zshrc
```

## Troubleshooting

### `.env` is missing

- make sure you are inside `python_scripts`
- run `ls -a` because `.env` is hidden

### Discord upload fails

- confirm `DISCORD_WEBHOOK_URL` exists in `.env`
- confirm the PNG file was created in `out/`
- `discord-send` only uploads PNG files

### `gexd` command not found

Run:

```bash
cd /Users/arivera/projects/project_go/python_scripts
pip install -e .
```

Then open a new shell or refresh your environment.

### Authentication issues

- verify `SCHWAB_API_KEY`, `SCHWAB_API_SECRET`, and `SCHWAB_REDIRECT_URI`
- rerun `python auth_demo.py` or `python -m cli auth --prompt`

## Quick Reference

```bash
cd /Users/arivera/projects/project_go/python_scripts
pip install -e .

gexd
gexd SPY
gexd QQQ 15

python -m cli --help
gexd --help
```
