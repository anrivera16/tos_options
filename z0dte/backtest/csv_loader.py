"""
Historical Data Loader for Calendar Spread Backtesting

Loads Schwab-format CSV files and converts them to Snapshots for backtesting.
Supports the format from backtest_files/ directory.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Iterator

from schwab.models import OptionContractRow


class OptionSnapshot:
    """A snapshot of option data at a point in time."""
    
    def __init__(
        self,
        symbol: str,
        timestamp: datetime,
        underlying_price: float,
        contracts: list[OptionContractRow],
    ):
        self.symbol = symbol
        self.timestamp = timestamp
        self.underlying_price = underlying_price
        self.contracts = contracts
    
    def get_expirations(self) -> list[str]:
        """Get sorted list of unique expiration dates."""
        expirations = set()
        for c in self.contracts:
            if c.expiration_date:
                expirations.add(c.expiration_date)
        return sorted(expirations)
    
    def get_strikes(self, expiration: str | None = None) -> list[float]:
        """Get sorted list of unique strikes, optionally filtered by expiration."""
        strikes = set()
        for c in self.contracts:
            if expiration is None or c.expiration_date == expiration:
                if c.strike and c.strike > 0:
                    strikes.add(c.strike)
        return sorted(strikes)
    
    def get_contracts_at_strike(
        self, strike: float, expiration: str | None = None
    ) -> list[OptionContractRow]:
        """Get all contracts at a given strike, optionally filtered by expiration."""
        results = []
        for c in self.contracts:
            if c.strike == strike:
                if expiration is None or c.expiration_date == expiration:
                    results.append(c)
        return results
    
    def get_atm_strike(self, min_strike: float = 100) -> float | None:
        """Get the ATM strike (closest to underlying price, ignoring very low strikes)."""
        if not self.contracts:
            return None
        valid_strikes = [c.strike for c in self.contracts if c.strike and c.strike >= min_strike]
        if not valid_strikes:
            return None
        return min(valid_strikes, key=lambda s: abs(s - self.underlying_price))
    
    def get_iv_at_strike(
        self, strike: float, expiration: str, option_type: str
    ) -> float | None:
        """Get IV for a specific strike/expiration/type."""
        for c in self.contracts:
            if (c.strike == strike and 
                c.expiration_date == expiration and 
                c.put_call.upper() == option_type.upper()):
                return c.volatility
        return None


class SchwabCSVLoader:
    """
    Load historical option data from Schwab CSV exports.
    
    Supports the format with:
    - First row: Timestamp header
    - Row 2: "UNDERLYING"
    - Row 3: Column headers
    - Row 4: Underlying price data
    - Row 10+: Expiration headers followed by option data rows
    
    The CSV format has expiration date headers like "1 DEC 25  (0)  100 (Weeklys)"
    followed by data rows with option information.
    """
    
    def __init__(self, csv_path: str | Path, symbol: str = "SPY"):
        self.csv_path = Path(csv_path)
        self.symbol = symbol
        self.snapshots: list[OptionSnapshot] = []
        self._parse()
    
    def _safe_float(self, value: str | None) -> float | None:
        """Safely parse a float value."""
        if value is None or value == "" or value == "<empty>":
            return None
        try:
            return float(value.replace(",", "").replace("$", ""))
        except ValueError:
            return None
    
    def _safe_int(self, value: str | None) -> int | None:
        """Safely parse an integer value."""
        if value is None or value == "" or value == "<empty>":
            return None
        try:
            return int(float(value.replace(",", "")))
        except ValueError:
            return None
    
    def _parse_timestamp(self, header: str) -> datetime | None:
        """Extract timestamp from CSV header line."""
        match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})\s+(\d{2}:\d{2}:\d{2})", header)
        if match:
            try:
                return datetime.strptime(f"{match.group(1)} {match.group(2)}", "%m/%d/%y %H:%M:%S")
            except ValueError:
                try:
                    return datetime.strptime(f"{match.group(1)} {match.group(2)}", "%m/%d/%Y %H:%M:%S")
                except ValueError:
                    pass
        return None
    
    def _parse_expiration_date(self, date_str: str) -> str | None:
        """Parse expiration date string to YYYY-MM-DD format."""
        date_str = date_str.strip()
        formats = ["%d %b %y", "%d %b %Y", "%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
    
    def _is_expiration_header(self, line: str) -> tuple[str | None, int | None]:
        """Check if line is an expiration header. Returns (date_str, dte) or (None, None)."""
        match = re.match(r"^\s*(\d{1,2}\s+\w+\s+\d{2,4})\s+\((\d+)\)", line.strip())
        if match:
            date_str = match.group(1)
            dte = int(match.group(2))
            exp_date = self._parse_expiration_date(date_str)
            return (exp_date, dte)
        return (None, None)
    
    def _parse(self) -> None:
        """Parse the CSV file and create snapshots."""
        with open(self.csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        timestamp = None
        underlying_price = None
        current_expiration: str | None = None
        current_dte: int | None = None
        contracts: list[OptionContractRow] = []
        snapshots: list[OptionSnapshot] = []
        
        i = 0
        while i < len(rows):
            row = rows[i]
            
            if not row:
                i += 1
                continue
            
            line = ",".join(row)
            line_stripped = line.strip()
            
            if timestamp is None:
                match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})\s+(\d{2}:\d{2}:\d{2})", line_stripped)
                if match:
                    timestamp = self._parse_timestamp(line_stripped)
                    i += 1
                    continue
            
            if underlying_price is None and "UNDERLYING" in line_stripped:
                underlying_row_idx = i + 2
                if underlying_row_idx < len(rows):
                    underlying_row = rows[underlying_row_idx]
                    for cell in underlying_row:
                        val = self._safe_float(cell)
                        if val is not None and val > 100:
                            underlying_price = val
                            break
                i += 1
                continue
            
            exp_date, exp_dte = self._is_expiration_header(line_stripped)
            if exp_date:
                current_expiration = exp_date
                current_dte = exp_dte
                i += 1
                continue
            
            if current_expiration and len(row) >= 15:
                try:
                    strike = self._safe_float(row[14])
                    if strike is None or strike <= 0:
                        i += 1
                        continue
                    
                    bid = self._safe_float(row[9]) if len(row) > 9 else None
                    ask = self._safe_float(row[11]) if len(row) > 11 else None
                    
                    type_indicator = row[18].strip().upper() if len(row) > 18 else ""
                    opt_type = "CALL"
                    if type_indicator == "P" or "PUT" in type_indicator:
                        opt_type = "PUT"
                    
                    oi = self._safe_int(row[3]) if len(row) > 3 else None
                    volume = self._safe_int(row[2]) if len(row) > 2 else None
                    
                    mid_price = None
                    if bid and ask and bid > 0 and ask > 0:
                        mid_price = (bid + ask) / 2
                    elif bid and bid > 0:
                        mid_price = bid
                    elif ask and ask > 0:
                        mid_price = ask
                    
                    contracts.append(
                        OptionContractRow(
                            snapshot_captured_at=timestamp.isoformat() if timestamp else None,
                            symbol=f"{self.symbol}_{current_expiration}_{strike:.2f}_{opt_type}",
                            underlying_symbol=self.symbol,
                            underlying_price=underlying_price,
                            expiration_date=current_expiration,
                            dte=current_dte,
                            strike=strike,
                            put_call=opt_type,
                            bid=bid,
                            ask=ask,
                            last=mid_price,
                            mark=mid_price,
                            delta=None,
                            gamma=None,
                            theta=None,
                            vega=None,
                            volatility=None,
                            open_interest=oi,
                            total_volume=volume,
                            in_the_money=None,
                            raw={"line": line},
                        )
                    )
                except (IndexError, ValueError):
                    pass
            
            i += 1
        
        if timestamp and underlying_price and contracts:
            snapshots.append(
                OptionSnapshot(
                    symbol=self.symbol,
                    timestamp=timestamp,
                    underlying_price=underlying_price,
                    contracts=contracts,
                )
            )
        
        self.snapshots = snapshots
    
    def get_snapshots(self) -> list[OptionSnapshot]:
        """Get all parsed snapshots."""
        return self.snapshots
    
    def __iter__(self) -> Iterator[OptionSnapshot]:
        """Iterate over snapshots."""
        return iter(self.snapshots)


class BacktestDataLoader:
    """
    Load multiple CSV files and combine into chronological snapshots.
    
    Files are sorted by filename (assumes date format in filename).
    """
    
    def __init__(self, data_dir: str | Path, symbol: str = "SPY"):
        self.data_dir = Path(data_dir)
        self.symbol = symbol
        self.snapshots: list[OptionSnapshot] = []
        self._load_all()
    
    def _load_all(self) -> None:
        """Load all CSV files and combine snapshots."""
        csv_files = sorted(self.data_dir.glob("*.csv"))
        
        for csv_file in csv_files:
            loader = SchwabCSVLoader(csv_file, self.symbol)
            self.snapshots.extend(loader.get_snapshots())
        
        self.snapshots.sort(key=lambda s: s.timestamp)
    
    def get_snapshots(self) -> list[OptionSnapshot]:
        """Get all snapshots sorted by timestamp."""
        return self.snapshots
    
    def __iter__(self) -> Iterator[OptionSnapshot]:
        """Iterate over snapshots."""
        return iter(self.snapshots)
    
    def __len__(self) -> int:
        """Number of snapshots."""
        return len(self.snapshots)


if __name__ == "__main__":
    import sys
    
    data_dir = Path(__file__).parent.parent / "backtest_files"
    if data_dir.exists():
        loader = BacktestDataLoader(data_dir, "SPY")
        print(f"Loaded {len(loader)} snapshots from {data_dir}")
        
        for i, snapshot in enumerate(loader.get_snapshots()[:5]):
            print(f"\nSnapshot {i + 1}: {snapshot.timestamp}")
            print(f"  Underlying: ${snapshot.underlying_price:.2f}")
            print(f"  Expirations: {len(snapshot.get_expirations())}")
            print(f"  Total contracts: {len(snapshot.contracts)}")
            if snapshot.contracts:
                atm = snapshot.get_atm_strike()
                print(f"  ATM Strike: {atm}")
                exps = snapshot.get_expirations()[:5]
                print(f"  First 5 expirations: {exps}")
    else:
        print(f"Data directory not found: {data_dir}")
        sys.exit(1)
