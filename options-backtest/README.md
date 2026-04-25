# Options Backtest Pipeline

Backtest 5-7 DTE bull put credit spreads using Polygon.io historical options data.

Uses Polygon's S3 flatfiles (free tier) for US options (OPRA) daily aggregates. Downloads, filters to target tickers, stores as Parquet, and runs backtests via DuckDB/Pandas.

---

## Prerequisites

```bash
pip install pandas pyarrow
```

AWS CLI configured with Polygon S3 credentials:

```bash
aws configure set aws_access_key_id YOUR_KEY
aws configure set aws_secret_access_key YOUR_SECRET
```

## Project Structure

```
options-backtest/
  raw/                    # Downloaded .csv.gz files (full OPRA feed)
  parquet/                # Filtered Parquet files (SPY only, ~30-50 MB for 6 months)
  strategy.py             # Core logic: P&L calc, spread selection, classification
  test_strategy.py        # Unit tests (32 tests covering all edge cases)
  download.py             # Step 1: Download raw data from S3
  ingest.py               # Step 2: Filter raw CSVs -> Parquet
  backtest.py             # Step 3: Run backtest (uses strategy.py)
  trade_list.py           # Pretty-print trade list by month
  backtest_results.csv    # Output: trade-by-trade log
```

## Usage

### Step 1: Download raw data

```bash
# Last 6 months (default)
python download.py

# Custom date range
python download.py --start 2025-01-01 --end 2025-06-30

# Last 12 months
python download.py --months 12
```

Downloads ~2.7 MB per trading day. Files go to `raw/`. Skips files already downloaded.

### Step 2: Filter to target tickers

```bash
# SPY only (default)
python ingest.py

# Multiple tickers
python ingest.py --tickers SPY QQQ IWM

# Force reprocess
python ingest.py --tickers SPY --force
```

Reads raw CSVs, filters to your tickers, parses option details (strike, expiry, DTE, type), saves as monthly Parquet files in `parquet/`.

### Step 3: Run backtest

```bash
# Default: SPY, $5 wide, ~15 delta, 5-7 DTE
python backtest.py

# Custom parameters
python backtest.py --ticker SPY --width 2 --delta 20 --dte-min 5 --dte-max 7

# Different bankroll
python backtest.py --capital 50000
```

### Step 4: View trade list

```bash
python trade_list.py
```

### Run unit tests

```bash
python -m unittest test_strategy -v
```

Output includes:
- Win rate
- Total and average P&L per contract
- Outcome breakdown (full win, partial win, max loss, partial loss)
- Monthly P&L breakdown
- Expected value per trade and annual projection

Results are saved to `backtest_results.csv` with entry date, strikes, premiums, and P&L for every trade.

## Strategy Logic

**Bull Put Credit Spread:**
1. On each trading day, find puts expiring in 5-7 calendar days
2. Select the short put at approximately the target delta (ranked by strike distance from ATM)
3. Buy a put `width` dollars below the short strike
4. Open at credit = short premium - long premium
5. Hold to expiry
6. If both legs expire OTM: keep full credit (max profit)
7. If short leg is ITM at expiry: P&L depends on how deep

**Key assumptions:**
- Entry at open price on entry day
- No early exit (hold to expiry)
- No commissions or slippage
- Uses daily open/close only (no intraday modeling)

## Data Source

Polygon.io S3 flatfiles via `files.massive.com`.

Available data types (not all used yet):
- `day_aggs_v1/` -- daily OHLCV per contract (what we use)
- `minute_aggs_v1/` -- minute bars (~10x larger)
- `trades_v1/` -- every individual trade (~20x larger)
- `quotes_v1/` -- NBBO quotes (very large)

## Storage

| Data | Size |
|------|------|
| Raw CSVs (6 months, all tickers) | ~340 MB |
| Filtered Parquet (SPY, 6 months) | ~30-50 MB |
| Filtered Parquet (SPY, 1 year) | ~60-100 MB |

Expanding to QQQ adds ~30%. Even with 10 tickers and a full year, you're under 1 GB.

## Extending

**Add more tickers:**
```bash
python ingest.py --tickers SPY QQQ
python backtest.py --ticker QQQ
```

**Minute-level data:** Change `day_aggs_v1` to `minute_aggs_v1` in `download.py`. Update `ingest.py` to handle the `window_start` field as minute timestamps instead of daily. Much more granular for intraday stop-loss modeling.

**Other strategies:** The Parquet data has calls too. Modify `backtest.py` to:
- Bear call spreads (`option_type == "C"`)
- Iron condors (combine bull put + bear call)
- Custom exit rules (e.g., close at 50% profit target)

## Limitations

- Daily data only. Cannot model intraday stop-outs or timed entries.
- Delta is approximated by strike percentile, not actual computed delta (no IV surface available in day aggs).
- No Greeks (delta, gamma, theta, vega) in the data. For precise delta selection, you'd need Polygon's options snapshots API.
- Weekend/holiday handling is basic (filters to weekdays only).
- No assignment/early exercise risk modeling.
