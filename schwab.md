# Schwab/TDA API — Available Data Reference

This document covers every Schwab API endpoint we use, the parameters each accepts, and every field we've observed in the responses. Based on the [schwabdev](https://github.com/tyteen4a01/schwabdev) Python client wrapping the Schwab/TDAmeritrade API v1.

---

## Authentication

**OAuth2 flow** — tokens stored at `~/.schwabdev/tokens.db`

| Item | Detail |
|------|--------|
| Auth URL | `https://api.schwabapi.com/v1/oauth/authorize` |
| Token refresh | Every ~7 days, interactive (30-second code window) |
| Rate limit | ~60 market data calls/min, ~120 total calls/min |
| Scope | Read-only (quotes, chains, price history, movers) |

---

## Endpoints

### 1. GET Option Chains

Our primary data source. Scraped every 5 min for each ticker.

```
GET /marketdata/v1/chains
```

**Parameters:**

| Parameter | Values | Default | Notes |
|-----------|--------|---------|-------|
| symbol | any ticker or $SPX, $NDX | required | Index options use $ prefix |
| contractType | CALL, PUT, ALL | ALL | Filter by put/call |
| strategy | SINGLE, ANALYTICAL, etc. | SINGLE | We use SINGLE |
| range | ITM, NTM, OTM, ALL | ALL | Strike moneyness filter |
| strikeCount | integer | all strikes | We use 50 (index), 25 (stocks) |
| fromDate | YYYY-MM-DD | today | Start of expiration window |
| toDate | YYYY-MM-DD | fromDate + days | End of expiration window |
| interval | integer | 1 | Strike interval for spread strategies |
| includeUnderlyingQuote | true/false | true | Includes quote data in response |

**Response Structure:**

```
{
  "symbol": "SPY",
  "status": "SUCCESS",
  "underlying": { ... },           // full quote object (see below)
  "strategy": "SINGLE",
  "interval": 1,
  "isDelayed": true,
  "isIndex": false,
  "interestRate": 5.25,
  "underlyingPrice": 710.54,
  "volatility": 29.0,             // historical vol
  "callExpDateMap": {             // calls grouped by expiration
    "2026-04-25:3": {             // key = "expirationDate:DTE"
      "710.0": [                  // strike -> array of contracts
        {
          // ── IDENTIFICATION ──
          "symbol": "SPY   260425C00710000",    // OCC symbol
          "description": "SPY Apr 25 2026 710 Call",
          "putCall": "CALL",
          "expirationDate": "2026-04-25",
          "daysToExpiration": 3,
          "strikePrice": 710.0,
          "underlyingSymbol": "SPY",

          // ── PRICING ──
          "bid": 3.50,
          "ask": 3.55,
          "last": 3.52,
          "mark": 3.53,
          "bidSize": 10,
          "askSize": 15,
          "lastSize": 1,
          "totalVolume": 12543,
          "openInterest": 8901,
          "open": 3.20,
          "high": 3.80,
          "low": 2.90,
          "close": 3.10,
          "previousClose": 3.05,
          "change": 0.42,
          "percentChange": 13.55,

          // ── IN-THE-MONEY ──
          "inTheMoney": false,
          "nonStandard": false,
          "underlyingPrice": 710.54,

          // ── GREEKS (from Schwab's model) ──
          "delta": 0.52,
          "gamma": 0.008,
          "theta": -0.45,
          "vega": 0.32,
          "rho": 0.08,
          "volatility": 18.5,          // implied volatility
          "theoreticalOptionValue": 3.55,
          "theoreticalVolatility": 18.3,
          "optionDeliverablesList": [],

          // ── SETTLEMENT ──
          "settlementType": " ",
          "settlementDate": "",
          "mini": false,
          "multiplier": 100,
          "exerciseStyle": "A",         // A=American, E=European
          "deliverableNote": "",
          "lastTradingDay": "2026-04-25",

          // ── MISC ──
          "tradeTimeInLong": 1713960000000,
          "quoteTimeInLong": 1713960000000,
          "timeValue": 2.98,
          "intrinsicValue": 0.54,
          "pennyPilot": true,
          "dollarDelta": 0.52,

          // ── RAW GREEKS (if ANALYTICAL strategy) ──
          "deltaCalc": ...,
          "gammaCalc": ...,
          "thetaCalc": ...,
          "vegaCalc": ...,
          "rhoCalc": ...,
          "ivCalc": ...,
        }
      ]
    }
  },
  "putExpDateMap": { ... }        // same structure for puts
}
```

**What we actually store in our DB:**

| DB Column | API Field | Notes |
|-----------|-----------|-------|
| symbol | putCall.symbol | Full OCC symbol |
| underlying_symbol | top-level symbol | Ticker without $ prefix |
| underlying_price | underlyingPrice or underlying.last | |
| expiration_date | expirationDate | |
| dte | daysToExpiration | |
| strike | strikePrice (map key) | |
| put_call | putCall | "PUT" or "CALL" |
| bid / ask / last / mark | same | |
| delta / gamma / theta / vega | same | Schwab-calculated Greeks |
| volatility | volatility | Implied volatility |
| open_interest | openInterest | |
| total_volume | totalVolume | Day's cumulative |
| in_the_money | inTheMoney | Boolean |

**Fields available from API but NOT stored:**
rho, bidSize, askSize, lastSize, open, high, low, close, previousClose, change, percentChange, settlementType, exerciseStyle, multiplier, lastTradingDay, tradeTimeInLong, quoteTimeInLong, timeValue, intrinsicValue, theoreticalOptionValue, nonStandard, pennyPilot, dollarDelta, mini, deliverableNote, optionDeliverablesList

---

### 2. GET Quote(s)

Real-time and fundamental quote data for any ticker.

```
GET /marketdata/v1/quotes              # batch (multiple symbols)
GET /marketdata/v1/{symbol}/quotes      # single
```

**Response Structure:**

```
{
  "SPY": {
    "symbol": "SPY",

    "reference": {
      "symbol": "SPY",
      "description": "SPDR S&P 500 ETF Trust",
      "exchange": "NYSE Arca",
      "exchangeName": "NYSE Arca",
      "assetType": "ETF",
      "cusip": "78462F103",
      "optionable": true,              // whether options trade on it
      "marginable": true,
      "shortable": true,
    },

    "quote": {
      // ── REAL-TIME PRICING ──
      "bidPrice": 710.50,
      "askPrice": 710.55,
      "bidSize": 100,
      "askSize": 200,
      "lastPrice": 710.54,
      "mark": 710.54,
      "open": 708.00,
      "high": 712.30,
      "low": 707.10,
      "closePrice": 708.50,            // previous close
      "previousClose": 706.80,
      "change": 1.74,
      "percentChange": 0.25,
      "fiftyTwoWeekHigh": 730.00,
      "fiftyTwoWeekLow": 580.00,
      "totalVolume": 45234567,

      // ── DIVIDENDS ──
      "dividendAmount": 1.68,
      "dividendYield": 1.2,
      "dividendDate": "2026-03-21",
      "annualDividend": 6.72,

      // ── TRADING STATUS ──
      "tradeTimeInLong": 1713960000000,
      "quoteTimeInLong": 1713960000000,
      "regularMarketTradeTimeInLong": 1713960000000,
      "regularMarketLastPrice": 710.54,
      "regularMarketNetChange": 1.74,
      "regularMarketPercentChange": 0.25,
      "regularMarketVolume": 45234567,
      "regularMarketPreviousClose": 706.80,

      // ── MISC ──
      "securityStatus": "Normal",
      "delayed": true,
      "netChange": 1.74,
    },

    "fundamental": {
      "symbol": "SPY",
      "avg10DaysVolume": 52000000,     // 10-day average volume
      "avg1DaysVolume": 45000000,      // 1-day average volume
      "avg3MonthsVolume": 48000000,    // 3-month average volume
      "marketCap": 500000000000,       // market cap
      "peRatio": 22.5,
      "pegRatio": 1.8,
      "pbRatio": 4.2,
      "priceToBook": 4.2,
      "returnOnEquity": 18.5,
      "revenue": 50000000000,
      "revenuePerShare": 120.5,
      "quarterlyRevenueGrowth": 0.05,
      "grossProfit": 30000000000,
      "ebitda": 25000000000,
      "totalCash": 10000000000,
      "totalDebt": 15000000000,
      "debtToEquity": 30.0,
      "operatingCashFlow": 20000000000,
      "beta": 1.0,
      "eps": 15.20,
      "dividendDate": "2026-03-21",
      "dividendPerShare": 6.72,
      "dividendYield": 1.2,
      "high52": 730.00,
      "low52": 580.00,
      "sharesOutstanding": 700000000,
      "shortRatio": 0.5,
      "shortPercentFloat": 0.002,
      "marginPercentage": 25.0,
      "optionable": true,
      "shortable": true,
    }
  }
}
```

**What we use from quotes:**

| Usage | Fields |
|-------|--------|
| Universe scanner scoring | totalVolume, avg10DaysVolume, lastPrice, percentChange, optionable, symbol |
| Scraper (underlying price) | lastPrice, mark, closePrice |
| Spread hunter (price context) | lastPrice via option chain's underlyingPrice |

---

### 3. GET Price History

OHLCV candles for any symbol.

```
GET /marketdata/v1/{symbol}/pricehistory
```

**Parameters:**

| Parameter | Values | Notes |
|-----------|--------|-------|
| periodType | day, month, year, ytd | |
| period | 1, 2, 3, 4, 5, 6, 10, 15, 30 (days) | depends on periodType |
| frequencyType | minute, hourly, daily, weekly, monthly | |
| frequency | 1, 5, 10, 15, 30 (min) / 1 (day, etc.) | |
| startDate | epoch ms | |
| endDate | epoch ms | |
| needExtendedHoursData | true/false | pre/post market candles |
| needPreviousClose | true/false | |

**Response Structure:**

```
{
  "symbol": "SPY",
  "empty": false,
  "candles": [
    {
      "open": 708.00,
      "high": 712.30,
      "low": 707.10,
      "close": 710.54,
      "volume": 1234567,
      "datetime": 1713960000000       // epoch ms
    },
    ...
  ]
}
```

**What we use:** Spread hunter fetches daily price history for SMA trend calculations and hourly candles for IV history.

---

### 4. GET Top Movers (Screener)

Market movers by price change or volume.

```
GET /marketdata/v1/{symbol}/movers
```

**Parameters:**

| Parameter | Values | Notes |
|-----------|--------|-------|
| symbol | $SPX, $COMPX, $DJI, etc. | Index to scan |
| sort | VOLUME, PERCENT_CHANGE, PERCENT_CHANGE_DOWN | Sort direction |
| frequency | 0 (default) | Time window |

**Response Structure:**

```
{
  "screeners": [
    {
      "key": "...",
      "description": "...",
      "symbols": [
        {
          "symbol": "NVDA",
          "change": 5.20,
          "description": "NVIDIA Corporation",
          "lastPrice": 950.00,
          "percentChange": 0.55,
          "volume": 45000000,
          "totalVolume": 45000000,
          "regularMarketPercentChange": 0.55,
          "regularMarketChange": 5.20,
          "regularMarketLastPrice": 950.00,
          "regularMarketTradeTimeInLong": 1713960000000,
          "high52": 975.00,
          "low52": 400.00,
          "navPrice": 0,
          "previousClose": 944.80,
          "tradeTime": 1713960000000,
        },
        ...
      ]
    }
  ]
}
```

**What we use:** Universe scanner fetches movers from $SPX, $COMPX (NASDAQ), $DJI sorted by PERCENT_CHANGE and VOLUME to find high-momentum names.

---

### 5. GET Option Expiration Chain

List of available expiration dates for a symbol.

```
GET /marketdata/v1/{symbol}/expirationchain
```

**Response Structure:**

```
{
  "expirationList": [
    {
      "date": "2026-04-25",
      "daysToExpiration": 3,
      "expirationType": "R",           // R=Regular, Q=Quarterly, W=Weekly
      "settlementType": " ",
      "standard": true,
      "nonStandard": false,
    },
    ...
  ]
}
```

**What we use:** Not currently used by any running service, but available for future features (e.g., targeting specific expiration types).

---

## Rate Limits & Constraints

| Limit | Value |
|-------|-------|
| Market data calls | ~60/min |
| Total API calls | ~120/min |
| Symbols per quote batch | ~500 |
| Options chain size | varies by ticker (~200-2000+ contracts) |
| Token lifetime | ~7 days before re-auth |
| Pre/post market data | Available via parameters |
| Index options | Use $ prefix ($SPX, $NDX, $RUT) |

---

## Data We Collect Per Ticker Per Scrape

For a typical SPY scrape (50 strikes, 14-day DTE window):

| Metric | Value |
|--------|-------|
| Contracts per scrape | ~800-1000 |
| Unique strikes | ~50 |
| Unique expirations | ~5-7 |
| DTE range | 1-14 |
| Greeks coverage | ~100% (all contracts) |
| OI coverage | ~95%+ (most contracts have OI) |
| Size per scrape | ~250 KB |
| API calls per scrape | 2 (chain + rows) |

---

## Summary: What's Available vs What We Store

| Data | Available from API | Stored in DB | Used in Analysis |
|------|-------------------|-------------|-----------------|
| Option chain (full) | Yes | No (rows only) | N/A |
| Individual contracts | Yes | Yes | Yes |
| Greeks (delta/gamma/theta/vega) | Yes | Yes | Yes |
| Rho | Yes | No | No |
| Implied volatility | Yes | Yes | Yes |
| Bid/Ask/Last/Mark | Yes | Yes | Yes |
| Bid/Ask size | Yes | No | No |
| OI / Volume | Yes | Yes | Yes |
| ITM flag | Yes | Yes | No |
| Open/High/Low/Close (option) | Yes | No | No |
| Percent change (option) | Yes | No | No |
| Exercise style | Yes | No | No |
| Settlement type | Yes | No | No |
| Multiplier | Yes | No | No |
| Last trading day | Yes | No | No |
| Time/Intrinsic value | Yes | No | No |
| Theoretical value | Yes | No | No |
| Underlying quote | Yes (in chain) | Underlying price only | Price only |
| Full quote (real-time) | Yes | No (fetched on-demand) | Universe scanner |
| Fundamentals | Yes | No | Universe scanner (vol filter) |
| Price history (OHLCV) | Yes | No (fetched on-demand) | Spread hunter (SMA) |
| Movers / Screener | Yes | No (fetched on-demand) | Universe scanner |
| Expiration chain | Yes | No | Not used yet |
