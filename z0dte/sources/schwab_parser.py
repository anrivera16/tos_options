from __future__ import annotations

import re
from datetime import datetime, date
from pathlib import Path


def parse_schwab_date(exp_str: str) -> date:
    match = re.search(r"(\d{1,2})\s+([A-Z]{3})\s+(\d{2,4})", exp_str)
    if not match:
        return date.today()
    day = int(match.group(1))
    month_str, year_str = match.group(2), match.group(3)
    year = int(year_str)
    if year < 100:
        year += 2000
    months = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
              "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
    month = months.get(month_str.upper(), 1)
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, month, 1)


def calc_dte(exp_date: date, ref_date: date) -> int:
    return max(0, (exp_date - ref_date).days)


def parse_iv(iv_str: str) -> float | None:
    if not iv_str or iv_str in ["<empty>", "--", ""]:
        return None
    iv_str = iv_str.replace("%", "").strip()
    try:
        return float(iv_str) / 100.0
    except ValueError:
        return None


def safe_float(s: str) -> float | None:
    if not s or s in ["<empty>", ""]:
        return None
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def safe_int(s: str) -> int:
    if not s or s in ["<empty>", ""]:
        return 0
    s = s.replace(",", "").strip()
    try:
        return int(float(s))
    except ValueError:
        return 0


def parse_schwab_csv(csv_path: str | Path) -> dict:
    with open(csv_path, newline="", encoding="utf-8-sig", errors="replace") as f:
        lines = f.readlines()

    underlying_price = 0.0
    contracts: list[dict] = []
    dt = datetime.now()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("Stock quote and option quote for"):
            parts = line.split("on")
            if len(parts) > 1:
                date_str = parts[1].strip()
                for fmt in ["%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S"]:
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        pass
            continue

        if line.startswith("LAST,LX,Net Chng"):
            continue

        parts = line.split(",")
        if len(parts) >= 11 and parts[0] and parts[0] not in ["<empty>"]:
            try:
                val = parts[0].strip().replace(",", "")
                if "." in val:
                    underlying_price = float(val)
                    continue
            except ValueError:
                pass

        if line.startswith(",,Volume,Open.Int,%Change,Delta,Gamma,Impl Vol"):
            continue

        if not line.startswith(",,") or len(parts) < 38:
            continue

        try:
            strike_str = parts[20].strip().replace(",", "")
            strike = float(strike_str) if strike_str and strike_str not in ["<empty>"] else 0
            if strike == 0:
                continue

            exp_str = parts[19].strip()
            exp_date = parse_schwab_date(exp_str)
            ref_date = date(dt.year, dt.month, dt.day)
            dte = calc_dte(exp_date, ref_date)

            if underlying_price == 0:
                continue

            put_vol = safe_int(parts[2])
            put_oi = safe_int(parts[3])
            put_delta = safe_float(parts[5])
            put_gamma = safe_float(parts[6])
            put_iv = parse_iv(parts[7])
            put_theta = safe_float(parts[13])
            put_vega = safe_float(parts[14])
            put_bid = safe_float(parts[15])
            put_ask = safe_float(parts[17])

            call_bid = safe_float(parts[21])
            call_ask = safe_float(parts[23])
            call_vol = safe_int(parts[25])
            call_oi = safe_int(parts[26])
            call_delta = safe_float(parts[28])
            call_gamma = safe_float(parts[29])
            call_iv = parse_iv(parts[30])
            call_theta = safe_float(parts[36])
            call_vega = safe_float(parts[37])

            contracts.append({
                "underlying_price": underlying_price,
                "expiration_date": exp_date.isoformat(),
                "dte": dte,
                "strike": strike,
                "put_call": "PUT",
                "bid": put_bid,
                "ask": put_ask,
                "mark": (put_bid + put_ask) / 2 if put_bid and put_ask else None,
                "open_interest": put_oi,
                "total_volume": put_vol,
                "delta": put_delta,
                "gamma": put_gamma,
                "theta": put_theta,
                "vega": put_vega,
                "volatility": put_iv,
            })

            contracts.append({
                "underlying_price": underlying_price,
                "expiration_date": exp_date.isoformat(),
                "dte": dte,
                "strike": strike,
                "put_call": "CALL",
                "bid": call_bid,
                "ask": call_ask,
                "mark": (call_bid + call_ask) / 2 if call_bid and call_ask else None,
                "open_interest": call_oi,
                "total_volume": call_vol,
                "delta": call_delta,
                "gamma": call_gamma,
                "theta": call_theta,
                "vega": call_vega,
                "volatility": call_iv,
            })
        except (ValueError, IndexError):
            continue

    return {
        "captured_at": dt,
        "underlying_price": underlying_price,
        "contracts": contracts,
    }


def load_schwab_csv_to_snapshots(csv_path: str | Path, symbol: str) -> list[dict]:
    data = parse_schwab_csv(csv_path)
    return [{
        "symbol": symbol,
        "captured_at": data["captured_at"],
        "underlying_price": data["underlying_price"],
        "contracts": data["contracts"],
        "source": "schwab_csv",
    }]