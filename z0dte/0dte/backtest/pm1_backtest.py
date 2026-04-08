"""
PM1 Format Backtest Parser for Net Premium Flow

Parses thinkorswim PM1 export format:
- Has LAST price column (required for accurate bid/ask trade classification)
- No Greeks columns

Format: Stock quote and option quote for SPY on 12/1/25 10:02:20
Header row: ,,Volume,Open.Int,AS,BS,Last Size,LAST,LX,BID,BX,ASK,AX,Exp,Strike,BID,BX,ASK,AX,Volume,Open.Int,AS,BS,Last Size,LAST,LX,,
"""

from __future__ import annotations

import csv
import re
from datetime import datetime, date
from pathlib import Path


CONTRACT_MULTIPLIER = 100


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


def safe_float(s: str | None) -> float | None:
    if not s or s in ["<empty>", ""]:
        return None
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def safe_int(s: str | None) -> int:
    if not s or s in ["<empty>", ""]:
        return 0
    s = s.replace(",", "").strip()
    try:
        return int(float(s))
    except ValueError:
        return 0


def classify_trade_side(bid: float | None, ask: float | None, last: float | None) -> str:
    if bid is None or ask is None or last is None:
        return "unknown"
    mid = (bid + ask) / 2
    if last >= mid:
        return "at_ask"
    else:
        return "at_bid"


class PM1Contract:
    def __init__(
        self,
        strike: float,
        put_call: str,
        expiration_date: date,
        dte: int,
        bid: float | None,
        ask: float | None,
        last: float | None,
        volume: int,
        open_interest: int,
        underlying_price: float,
    ):
        self.strike = strike
        self.put_call = put_call
        self.expiration_date = expiration_date
        self.dte = dte
        self.bid = bid
        self.ask = ask
        self.last = last
        self.volume = volume
        self.open_interest = open_interest
        self.underlying_price = underlying_price
        self.mark = (bid + ask) / 2 if bid and ask else None

    def to_dict(self) -> dict:
        return {
            "strike": self.strike,
            "put_call": self.put_call,
            "expiration_date": self.expiration_date.isoformat(),
            "dte": self.dte,
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "mark": self.mark,
            "total_volume": self.volume,
            "open_interest": self.open_interest,
            "underlying_price": self.underlying_price,
        }


class PM1Snapshot:
    def __init__(
        self,
        symbol: str,
        captured_at: datetime,
        underlying_price: float,
        contracts: list[PM1Contract],
        source: str = "pm1_backtest",
    ):
        self.symbol = symbol
        self.captured_at = captured_at
        self.underlying_price = underlying_price
        self.contracts = contracts
        self.source = source

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "captured_at": self.captured_at,
            "underlying_price": self.underlying_price,
            "source": self.source,
            "contracts": [c.to_dict() for c in self.contracts],
        }


def parse_pm1_file(csv_path: str | Path, symbol: str = "SPY") -> PM1Snapshot:
    with open(csv_path, newline="", encoding="utf-8-sig", errors="replace") as f:
        lines = f.readlines()

    captured_at = datetime.now()
    underlying_price = 0.0
    contracts: list[PM1Contract] = []
    is_pm1_format = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Parse timestamp from first line
        if "Stock quote and option quote for" in line:
            # Use split with maxsplit=1 to split on the LAST " on "
            # Line: "Stock quote and option quote for SPY on 12/1/25 10:02:20"
            parts = line.rsplit(" on ", 1)
            if len(parts) == 2:
                date_str = parts[1].strip()
                for fmt in ["%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S"]:
                    try:
                        captured_at = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        pass
            continue

        # Detect PM1 format (has LAST column between Last Size and BID)
        if "Last Size,LAST,LX,BID" in line:
            is_pm1_format = True
            continue

        # Parse underlying price
        if line.startswith("LAST,LX,Net Chng"):
            continue
        if not is_pm1_format:
            parts = line.split(",")
            if len(parts) >= 5 and parts[0]:
                try:
                    val = parts[0].strip().replace(",", "")
                    if "." in val:
                        underlying_price = float(val)
                        continue
                except ValueError:
                    pass

        # Skip non-contract lines
        if not line.startswith(",,") or "Last Size,LAST,LX,BID" in line:
            continue

        parts = line.split(",")
        if len(parts) < 25:
            continue

        try:
            # PM1 column mapping:
            # Col 13: Exp, Col 14: Strike
            # Put side: Vol=2, OI=3, LAST=7, BID=9, ASK=11
            # Call side: BID=15, ASK=17, Vol=19, OI=20, LAST=24
            
            exp_str = parts[13].strip()
            strike_str = parts[14].strip().replace(",", "")
            
            if not exp_str or not strike_str or strike_str in ["<empty>", ""]:
                continue
                
            exp_date = parse_schwab_date(exp_str)
            strike = float(strike_str)
            
            if strike == 0:
                continue

            ref_date = date(captured_at.year, captured_at.month, captured_at.day)
            dte = max(0, (exp_date - ref_date).days)

            # Skip non-0DTE contracts for backtest
            if dte != 0:
                continue

            # Parse puts (left side)
            put_vol = safe_int(parts[2])
            put_oi = safe_int(parts[3])
            put_last = safe_float(parts[7])
            put_bid = safe_float(parts[9])
            put_ask = safe_float(parts[11])

            # Parse calls (right side)
            call_bid = safe_float(parts[15])
            call_ask = safe_float(parts[17])
            call_vol = safe_int(parts[19])
            call_oi = safe_int(parts[20])
            call_last = safe_float(parts[24])

            if underlying_price == 0:
                # Try to get from call side strike vicinity
                continue

            # Create PUT contract
            if put_bid is not None or put_ask is not None:
                contracts.append(PM1Contract(
                    strike=strike,
                    put_call="PUT",
                    expiration_date=exp_date,
                    dte=dte,
                    bid=put_bid,
                    ask=put_ask,
                    last=put_last,
                    volume=put_vol,
                    open_interest=put_oi,
                    underlying_price=underlying_price,
                ))

            # Create CALL contract
            if call_bid is not None or call_ask is not None:
                contracts.append(PM1Contract(
                    strike=strike,
                    put_call="CALL",
                    expiration_date=exp_date,
                    dte=dte,
                    bid=call_bid,
                    ask=call_ask,
                    last=call_last,
                    volume=call_vol,
                    open_interest=call_oi,
                    underlying_price=underlying_price,
                ))

        except (ValueError, IndexError):
            continue

    return PM1Snapshot(
        symbol=symbol,
        captured_at=captured_at,
        underlying_price=underlying_price,
        contracts=contracts,
    )


def compute_premium_flow(snapshot: PM1Snapshot) -> dict:
    """
    Compute dollar-weighted premium flow from PM1 snapshot.
    
    Returns:
        dict with:
        - call_premium_at_ask: Total $ call volume hitting ask
        - call_premium_at_bid: Total $ call volume hitting bid
        - put_premium_at_ask: Total $ put volume hitting ask
        - put_premium_at_bid: Total $ put volume hitting bid
        - net_premium_flow: (calls_ask - calls_bid) - (puts_ask - puts_bid)
    """
    call_at_ask = 0.0
    call_at_bid = 0.0
    put_at_ask = 0.0
    put_at_bid = 0.0

    for c in snapshot.contracts:
        if c.volume == 0:
            continue
        if c.mark is None or c.mark <= 0:
            continue

        dollar_premium = c.volume * c.mark * CONTRACT_MULTIPLIER
        side = classify_trade_side(c.bid, c.ask, c.last)

        if c.put_call == "CALL":
            if side == "at_ask":
                call_at_ask += dollar_premium
            elif side == "at_bid":
                call_at_bid += dollar_premium
            else:
                call_at_ask += dollar_premium * 0.5
                call_at_bid += dollar_premium * 0.5
        else:
            if side == "at_ask":
                put_at_ask += dollar_premium
            elif side == "at_bid":
                put_at_bid += dollar_premium
            else:
                put_at_ask += dollar_premium * 0.5
                put_at_bid += dollar_premium * 0.5

    net_flow = (call_at_ask - call_at_bid) - (put_at_ask - put_at_bid)

    return {
        "symbol": snapshot.symbol,
        "captured_at": snapshot.captured_at,
        "underlying_price": snapshot.underlying_price,
        "call_premium_at_ask": call_at_ask,
        "call_premium_at_bid": call_at_bid,
        "put_premium_at_ask": put_at_ask,
        "put_premium_at_bid": put_at_bid,
        "net_premium_flow": net_flow,
        "call_volume": sum(c.volume for c in snapshot.contracts if c.put_call == "CALL"),
        "put_volume": sum(c.volume for c in snapshot.contracts if c.put_call == "PUT"),
        "num_contracts": len(snapshot.contracts),
    }


def run_backtest(csv_files: list[str | Path], symbol: str = "SPY") -> list[dict]:
    """
    Run backtest on multiple PM1 CSV files.
    
    Args:
        csv_files: List of paths to PM1 CSV files (will be sorted by name)
        symbol: Underlying symbol (default: SPY)
        
    Returns:
        List of premium flow results, one per file
    """
    results = []
    
    # Sort files to process in order
    sorted_files = sorted(csv_files, key=lambda p: str(p))
    
    for csv_path in sorted_files:
        print(f"Processing: {csv_path}")
        snapshot = parse_pm1_file(csv_path, symbol)
        flow = compute_premium_flow(snapshot)
        results.append(flow)
        
        print(f"  Time: {flow['captured_at']}")
        print(f"  SPY: ${flow['underlying_price']:.2f}")
        print(f"  Call Vol: {flow['call_volume']:,} | Put Vol: {flow['put_volume']:,}")
        print(f"  Net Premium Flow: ${flow['net_premium_flow']:+,.0f}")
        print()
    
    return results


def print_summary(results: list[dict]) -> None:
    """Print backtest summary."""
    if not results:
        print("No results to summarize")
        return
    
    print("\n" + "=" * 60)
    print("PREMIUM FLOW BACKTEST SUMMARY")
    print("=" * 60)
    
    for i, r in enumerate(results):
        direction = "BULLISH" if r["net_premium_flow"] > 0 else "BEARISH"
        print(f"\n[{i+1}] {r['captured_at']}")
        print(f"    Underlying: ${r['underlying_price']:.2f}")
        print(f"    Direction:  {direction}")
        print(f"    Net Flow:   ${r['net_premium_flow']:+,.0f}")
        print(f"    Call Flow:  ${r['call_premium_at_ask'] - r['call_premium_at_bid']:+,.0f} "
              f"(ask: ${r['call_premium_at_ask']:+,.0f}, bid: ${r['call_premium_at_bid']:+,.0f})")
        print(f"    Put Flow:   ${r['put_premium_at_ask'] - r['put_premium_at_bid']:+,.0f} "
              f"(ask: ${r['put_premium_at_ask']:+,.0f}, bid: ${r['put_premium_at_bid']:+,.0f})")
    
    # Calculate cumulative
    cumulative = sum(r["net_premium_flow"] for r in results)
    print("\n" + "-" * 60)
    print(f"Total (cumulative): ${cumulative:+,.0f}")


if __name__ == "__main__":
    import glob
    from pathlib import Path
    
    # Example: run on all PM1 files in backtest_files
    pattern = Path(__file__).parent / "backtest_files" / "*PM1*.csv"
    files = sorted(glob.glob(str(pattern)))
    
    if files:
        print(f"Found {len(files)} PM1 files\n")
        results = run_backtest(files, symbol="SPY")
        print_summary(results)
    else:
        print("No PM1 files found")
