# TOS Options — Project Layout

## Machines

| Machine     | Role            | Path                          | Access                          |
|-------------|-----------------|-------------------------------|----------------------------------|
| Mac         | Dev / Ideas     | /Users/arivera/projects/tos_options | Local                       |
| Desktop     | Production      | D:\trading\tos_options        | SSH via Tailscale (100.82.57.80)|

## Key Point

The Mac is for writing code and testing ideas. The Desktop is where the real
database, scanner, and data pipeline live. Push changes to git and the Desktop
auto-pulls them — no manual deployment needed.

## Desktop Access

```bash
ssh 23and@100.82.57.80
cd D:\trading\tos_options
```

## Database

- PostgreSQL 16 in Docker, port 5433
- User: trader / DB: options / PW: changeme
- Connect from Desktop:
  ```bash
  cd /d D:\trading\tos_options
  docker compose exec -T db psql -U trader -d options
  ```
- Tables: snapshots, option_contracts, aggregates_by_bucket,
  aggregates_by_expiry, aggregates_by_strike
- snapshots.captured_at is the timestamp field (text format)
- IMPORTANT: Mac being down != scraper down. Desktop runs independently.

## Modules

1. **spread_hunter/** — Live scanner, 5 spread types, runs every 15 min in Docker
2. **algo/** — Modular backtest pipeline with 9 toggleable modules:
   generators, trend, iv_rank, earnings, wall_detector, wall_proximity,
   scoring, risk_manager, stop_loss

## Strategy (Current Best)

- SPY bull put credit spreads (also bear call)
- $5 wide, delta 0.10–0.20, DTE 5–9
- IV rank 30–95%, wall proximity 1%
- Winner: BP 1.5% OTM / 7 DTE / 50% stop / 75% target
  - 96% WR, PF 4.31, maxDD $2.93
- Overlap tested and rejected (correlation risk on SPY dumps)

## Config Presets

- `baseline_config()` — minimal
- `trend_only_config()` — trend filter only
- `full_stack_config()` — all 9 modules

## Data Sources

- Polygon flat files: OHLCV only (no greeks/IV/OI)
- Stock flat files 403 on standard plan — estimate SPY close from ATM put strikes
- Schwab tokens expire every 7 days
- GEX data in `aggregates_by_strike` table (fallback to DB when Schwab expired)

## Alerts

- Discord webhook via .env (DISCORD_WEBHOOK_URL)
- discord/webhook.py: send_message(), send_png()

## Bankroll

$50K, non-overlapping (max_positions=1)
