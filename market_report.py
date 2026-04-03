from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from schwab.api import debug_top_movers_payload, get_quotes, get_top_movers


CENTRAL_TZ = ZoneInfo("America/Chicago")
MARKET_SESSION_TIMES = {
    time(8, 30),
    time(9, 30),
    time(10, 30),
    time(11, 30),
    time(12, 30),
    time(13, 30),
    time(14, 30),
}
QUOTE_BATCH_SIZE = 500
SPX_SYMBOLS = [
    "MMM", "AOS", "ABT", "ABBV", "ACN", "ADBE", "AMD", "AES", "AFL", "A", "APD", "ABNB",
    "AKAM", "ALB", "ARE", "ALGN", "ALLE", "LNT", "ALL", "GOOGL", "GOOG", "MO", "AMZN",
    "AMCR", "AEE", "AEP", "AXP", "AIG", "AMT", "AWK", "AMP", "AME", "AMGN", "APH", "ADI",
    "AON", "APA", "APO", "AAPL", "AMAT", "APP", "APTV", "ACGL", "ADM", "ARES", "ANET",
    "AJG", "AIZ", "T", "ATO", "ADSK", "ADP", "AZO", "AVB", "AVY", "AXON", "BKR", "BALL",
    "BAC", "BAX", "BDX", "BRK.B", "BBY", "TECH", "BIIB", "BLK", "BX", "XYZ", "BK", "BA",
    "BKNG", "BSX", "BMY", "AVGO", "BR", "BRO", "BF.B", "BLDR", "BG", "BXP", "CHRW", "CDNS",
    "CPT", "CPB", "COF", "CAH", "CCL", "CARR", "CVNA", "CAT", "CBOE", "CBRE", "CDW", "COR",
    "CNC", "CNP", "CF", "CRL", "SCHW", "CHTR", "CVX", "CMG", "CB", "CHD", "CIEN", "CI",
    "CINF", "CTAS", "CSCO", "C", "CFG", "CLX", "CME", "CMS", "KO", "CTSH", "CL", "CMCSA",
    "CAG", "COP", "ED", "STZ", "CEG", "COO", "CPRT", "GLW", "CPAY", "CTVA", "CSGP", "COST",
    "CTRA", "CRWD", "CCI", "CSX", "CMI", "CVS", "DHR", "DRI", "DVA", "DAY", "DECK", "DE",
    "DELL", "DAL", "DVN", "DXCM", "FANG", "DLR", "DFS", "DG", "DLTR", "D", "DPZ", "DOV",
    "DOW", "DHI", "DTE", "DUK", "DD", "EMN", "ETN", "EBAY", "ECL", "EIX", "EW", "EA", "ELV",
    "EMR", "ENPH", "ETR", "EOG", "EPAM", "EQT", "EFX", "EQIX", "EQR", "ERIE", "ESS", "EL",
    "EG", "EVRG", "ES", "EXC", "EXPE", "EXPD", "EXR", "XOM", "FFIV", "FDS", "FICO", "FAST",
    "FRT", "FDX", "FIS", "FITB", "FSLR", "FE", "FI", "FMC", "F", "FTNT", "FTV", "FOXA", "FOX",
    "BEN", "FCX", "GRMN", "IT", "GE", "GEHC", "GEV", "GEN", "GNRC", "GD", "GIS", "GM", "GPC",
    "GILD", "GPN", "GL", "GDDY", "GS", "HAL", "HIG", "HAS", "HCA", "DOC", "HSIC", "HSY",
    "HES", "HPE", "HLT", "HOLX", "HD", "HON", "HRL", "HST", "HWM", "HPQ", "HUBB", "HUM",
    "HBAN", "HII", "IBM", "IEX", "IDXX", "ITW", "INCY", "IR", "PODD", "INTC", "ICE", "IFF",
    "IP", "IPG", "INTU", "ISRG", "IVZ", "INVH", "IQV", "IRM", "JBHT", "JBL", "JKHY", "J", "JNJ",
    "JCI", "JPM", "JNPR", "K", "KVUE", "KDP", "KEY", "KEYS", "KMB", "KIM", "KMI", "KKR", "KLAC",
    "KHC", "KR", "LHX", "LH", "LRCX", "LW", "LVS", "LDOS", "LEN", "LLY", "LIN", "LYV", "LKQ",
    "LMT", "L", "LOW", "LULU", "LYB", "MTB", "MPC", "MKTX", "MAR", "MMC", "MLM", "MAS", "MA",
    "MTCH", "MKC", "MCD", "MCK", "MDT", "MRK", "META", "MET", "MTD", "MGM", "MCHP", "MU",
    "MSFT", "MAA", "MRNA", "MHK", "MOH", "TAP", "MDLZ", "MPWR", "MNST", "MCO", "MS", "MOS",
    "MSI", "MSCI", "NDAQ", "NTAP", "NFLX", "NEM", "NWSA", "NWS", "NEE", "NKE", "NI", "NDSN",
    "NSC", "NTRS", "NOC", "NCLH", "NRG", "NUE", "NVDA", "NVR", "NXPI", "ORLY", "OXY", "ODFL",
    "OMC", "ON", "OKE", "ORCL", "OTIS", "PCAR", "PKG", "PLTR", "PANW", "PARA", "PH", "PAYX",
    "PAYC", "PYPL", "PNR", "PEP", "PFE", "PCG", "PM", "PSX", "PNW", "PNC", "POOL", "PPG", "PPL",
    "PFG", "PG", "PGR", "PLD", "PRU", "PEG", "PTC", "PSA", "PHM", "QRVO", "PWR", "QCOM", "DGX",
    "RL", "RJF", "RTX", "O", "REG", "REGN", "RF", "RSG", "RMD", "RVTY", "ROK", "ROL", "ROP",
    "ROST", "RCL", "SPGI", "CRM", "SBAC", "SLB", "STX", "SRE", "NOW", "SHW", "SPG", "SWKS", "SJM",
    "SW", "SNA", "SOLV", "SO", "LUV", "SWK", "SBUX", "STT", "STLD", "STE", "SYK", "SMCI", "SYF",
    "SNPS", "SYY", "TMUS", "TROW", "TTWO", "TPR", "TRGP", "TGT", "TEL", "TDY", "TER", "TSLA", "TXN",
    "TPL", "TXT", "TMO", "TJX", "TSCO", "TT", "TDG", "TRV", "TRMB", "TFC", "TYL", "TSN", "USB",
    "UBER", "UDR", "ULTA", "UNP", "UAL", "UPS", "URI", "UNH", "UHS", "VLO", "VTR", "VLTO", "VRSN",
    "VRSK", "VZ", "VRTX", "VTRS", "VICI", "V", "VST", "VMC", "WRB", "GWW", "WAB", "WBA", "WMT",
    "DIS", "WBD", "WM", "WAT", "WEC", "WFC", "WELL", "WST", "WDC", "WY", "WSM", "WMB", "WTW",
    "WDAY", "WYNN", "XEL", "XYL", "YUM", "ZBRA", "ZBH", "ZTS",
]
NASDAQ_100_SYMBOLS = [
    "ADBE", "AMD", "ABNB", "ALNY", "GOOGL", "GOOG", "AMZN", "AEP", "AMGN", "ADI", "AAPL", "AMAT",
    "APP", "ARM", "ASML", "TEAM", "ADSK", "ADP", "AXON", "BKR", "BKNG", "AVGO", "CDNS", "CHTR",
    "CTAS", "CSCO", "CCEP", "CTSH", "CMCSA", "CEG", "CPRT", "CSGP", "COST", "CRWD", "CSX", "DDOG",
    "DXCM", "FANG", "DASH", "EA", "EXC", "FAST", "FER", "FTNT", "GEHC", "GILD", "HON", "IDXX",
    "INSM", "INTC", "INTU", "ISRG", "KDP", "KLAC", "KHC", "LRCX", "LIN", "MAR", "MRVL", "MELI",
    "META", "MCHP", "MU", "MSFT", "MSTR", "MDLZ", "MPWR", "MNST", "NFLX", "NVDA", "NXPI", "ORLY",
    "ODFL", "PCAR", "PLTR", "PANW", "PAYX", "PYPL", "PDD", "PEP", "QCOM", "REGN", "ROP", "ROST",
    "STX", "SHOP", "SBUX", "SNPS", "TMUS", "TTWO", "TSLA", "TXN", "TRI", "VRSK", "VRTX", "WMT",
    "WBD", "WDC", "WDAY", "XEL", "ZS",
]


class MarketReportError(RuntimeError):
    pass


@dataclass(frozen=True)
class MarketSection:
    title: str
    breadth_symbols: list[str]
    movers_symbols: list[str]


SECTIONS = (
    MarketSection(title="SPX / S&P 500 Breadth", breadth_symbols=SPX_SYMBOLS, movers_symbols=["$SPX", "NYSE", "INDEX_ALL"]),
    MarketSection(title="NASDAQ-100 Breadth", breadth_symbols=NASDAQ_100_SYMBOLS, movers_symbols=["$COMPX", "NASDAQ", "INDEX_ALL"]),
)


def is_market_report_time(now: datetime | None = None) -> bool:
    current = _to_central(now)
    return current.weekday() < 5 and current.time().replace(second=0, microsecond=0) in MARKET_SESSION_TIMES


def validate_market_report_time(force: bool = False, now: datetime | None = None) -> datetime:
    current = _to_central(now)
    if force:
        return current
    if is_market_report_time(current):
        return current
    raise MarketReportError(
        "Market report runs only during the regular session at 8:30 AM CT through 2:30 PM CT, hourly. Use --force to override."
    )


def build_market_report(now: datetime | None = None) -> str:
    current = _to_central(now)
    sections = [build_market_section(section) for section in SECTIONS]
    return "\n\n".join([f"Market Update - {current.strftime('%-I:%M %p CT')}", *sections])


def build_market_section(section: MarketSection) -> str:
    breadth = get_breadth(section.breadth_symbols)
    top_volume = _get_first_available_movers(section.movers_symbols, sort="VOLUME", limit=5)
    top_gainers = _get_first_available_movers(section.movers_symbols, sort="PERCENT_CHANGE_UP", limit=5)
    top_losers = _get_first_available_movers(section.movers_symbols, sort="PERCENT_CHANGE_DOWN", limit=5)
    return "\n".join(
        [
            section.title,
            f"Green: {breadth['green']} | Red: {breadth['red']} | Flat: {breadth['flat']}",
            "",
            "Top Volume",
            *_format_movers(top_volume, include_volume=True),
            "",
            "Top Gainers",
            *_format_movers(top_gainers, include_volume=False),
            "",
            "Top Losers",
            *_format_movers(top_losers, include_volume=False),
        ]
    )


def get_breadth(symbols: list[str]) -> dict[str, int]:
    green = 0
    red = 0
    flat = 0

    for batch in _chunked(symbols, QUOTE_BATCH_SIZE):
        quotes = get_quotes(batch)
        for symbol in batch:
            quote = quotes.get(symbol)
            if not quote:
                continue
            change = _extract_net_change(quote)
            if change > 0:
                green += 1
            elif change < 0:
                red += 1
            else:
                flat += 1

    return {"green": green, "red": red, "flat": flat}


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _extract_net_change(quote: dict[str, object]) -> float:
    for key in ("netChange", "markChange", "change"):
        value = quote.get(key)
        if value not in (None, ""):
            return _coerce_float(value)
    quote_data = quote.get("quote")
    if isinstance(quote_data, dict):
        for key in ("netChange", "markChange", "change"):
            value = quote_data.get(key)
            if value not in (None, ""):
                return _coerce_float(value)
    return 0.0


def _format_movers(rows: list[dict[str, object]], include_volume: bool) -> list[str]:
    if not rows:
        return ["1. No data available"]
    formatted = []
    for index, row in enumerate(rows, start=1):
        symbol = str(row.get("symbol") or row.get("ticker") or "?")
        percent = _extract_percent_change(row)
        line = f"{index}. {symbol} {_format_percent(percent)}"
        if include_volume:
            line = f"{line} | {_format_volume(_coerce_float(row.get('volume'), default=0.0))}"
        formatted.append(line)
    return formatted


def _get_first_available_movers(symbols: list[str], sort: str, limit: int = 5) -> list[dict[str, object]]:
    for symbol in symbols:
        rows = get_top_movers(symbol, sort=sort, limit=limit)
        if rows:
            return rows
    return []


def _extract_percent_change(row: dict[str, object]) -> float:
    percent = row.get("percentChange")
    if percent not in (None, ""):
        return _coerce_float(percent, default=0.0)

    net_percent = row.get("netPercentChange")
    value = _coerce_float(net_percent, default=0.0)
    if -1.0 <= value <= 1.0:
        return value * 100.0
    return value


def debug_market_movers() -> str:
    lines: list[str] = []
    for section in SECTIONS:
        lines.append(f"[{section.title}] movers_symbols={section.movers_symbols}")
        for symbol in section.movers_symbols:
            lines.append(f"  symbol={symbol}")
            for sort in ("VOLUME", "PERCENT_CHANGE_UP", "PERCENT_CHANGE_DOWN"):
                try:
                    rows = get_top_movers(symbol, sort=sort, limit=5)
                    lines.append(f"    {sort}: count={len(rows)}")
                    if rows:
                        sample = rows[0]
                        lines.append(
                            "      sample keys="
                            + ", ".join(sorted(str(key) for key in sample.keys())[:12])
                        )
                        lines.append(f"      sample row={sample}")
                except Exception as exc:
                    lines.append(f"    {sort}: ERROR {type(exc).__name__}: {exc}")
    return "\n".join(lines)


def debug_market_movers_payloads() -> str:
    lines: list[str] = []
    for section in SECTIONS:
        lines.append(f"[{section.title}] movers_symbols={section.movers_symbols}")
        for symbol in section.movers_symbols:
            for sort in ("VOLUME", "PERCENT_CHANGE_UP", "PERCENT_CHANGE_DOWN"):
                try:
                    payload = debug_top_movers_payload(symbol, sort=sort)
                    keys = sorted(payload.keys()) if isinstance(payload, dict) else []
                    lines.append(f"  symbol={symbol} sort={sort} payload_keys={keys}")
                    if isinstance(payload, dict):
                        screeners = payload.get("screeners")
                        lines.append(f"    screeners_type={type(screeners).__name__}")
                        if isinstance(screeners, list):
                            lines.append(f"    screeners_count={len(screeners)}")
                            if screeners:
                                first = screeners[0]
                                lines.append(f"    first_screener={first}")
                        else:
                            lines.append(f"    payload={payload}")
                except Exception as exc:
                    lines.append(f"  symbol={symbol} sort={sort} ERROR {type(exc).__name__}: {exc}")
    return "\n".join(lines)


def _format_percent(value: float) -> str:
    return f"{value:+.1f}%"


def _format_volume(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(int(round(value)))


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        if isinstance(value, (int, float)):
            return value * 1.0
        if isinstance(value, str):
            return float(value)
        return default
    except (TypeError, ValueError):
        return default


def _to_central(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(tz=CENTRAL_TZ)
    if value.tzinfo is None:
        return value.replace(tzinfo=CENTRAL_TZ)
    return value.astimezone(CENTRAL_TZ)


def get_market_report_date(now: datetime | None = None) -> date:
    return _to_central(now).date()
