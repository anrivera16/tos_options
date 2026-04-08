from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from schwab.models import OptionContractRow, _safe_float, _safe_int

from z0dte.sources.base import DataSource, Snapshot


class CSVDataSource(DataSource):
    def __init__(self, csv_path: str | Path, symbol: str) -> None:
        self.frames = self._parse_csv(csv_path, symbol)
        self.index = 0
        self.source = "csv_backtest"

    def fetch_snapshot(self, symbol: str) -> Snapshot:
        snapshot = self.frames[self.index]
        self.index += 1
        return snapshot

    def has_more(self) -> bool:
        return self.index < len(self.frames)

    def _parse_csv(self, path: str | Path, symbol: str) -> list[Snapshot]:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            return []

        timestamp_col = self._find_timestamp_col(rows[0])
        if timestamp_col:
            return self._parse_timestamped_csv(rows, symbol, timestamp_col)
        else:
            return [self._parse_single_snapshot(rows, symbol)]

    def _find_timestamp_col(self, row: dict[str, str]) -> str | None:
        timestamp_candidates = ["timestamp", "captured_at", "datetime", "date_time", "date"]
        for col in timestamp_candidates:
            if col in row:
                return col
        return None

    def _parse_timestamped_csv(
        self, rows: list[dict[str, str]], symbol: str, timestamp_col: str
    ) -> list[Snapshot]:
        snapshots: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            ts = row.get(timestamp_col, "")
            if ts not in snapshots:
                snapshots[ts] = []
            snapshots[ts].append(row)

        results: list[Snapshot] = []
        for ts_str, ts_rows in sorted(snapshots.items()):
            contracts = self._rows_to_contracts(ts_rows, symbol)
            try:
                captured_at = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                captured_at = datetime.now()
            underlying_price = self._get_underlying_price(contracts)
            results.append(
                Snapshot(
                    symbol=symbol,
                    captured_at=captured_at,
                    underlying_price=underlying_price,
                    contracts=contracts,
                    source=self.source,
                )
            )
        return results

    def _parse_single_snapshot(self, rows: list[dict[str, str]], symbol: str) -> Snapshot:
        contracts = self._rows_to_contracts(rows, symbol)
        underlying_price = self._get_underlying_price(contracts)
        return Snapshot(
            symbol=symbol,
            captured_at=datetime.now(),
            underlying_price=underlying_price,
            contracts=contracts,
            source=self.source,
        )

    def _rows_to_contracts(self, rows: list[dict[str, str]], symbol: str) -> list[OptionContractRow]:
        contracts: list[OptionContractRow] = []
        for row in rows:
            underlying_price = _safe_float(row.get("underlying_price"))
            expiration_date = row.get("expiration_date") or row.get("Expiration", "")
            try:
                dte_val = int(float(row.get("dte") or row.get("DTE", "0") or "0"))
            except (ValueError, TypeError):
                dte_val = 0
            contracts.append(
                OptionContractRow(
                    snapshot_captured_at=row.get("captured_at"),
                    symbol=row.get("symbol") or row.get("Symbol", ""),
                    underlying_symbol=symbol,
                    underlying_price=underlying_price,
                    expiration_date=expiration_date,
                    dte=dte_val if dte_val > 0 else None,
                    strike=_safe_float(row.get("strike") or row.get("Strike", "0")) or 0.0,
                    put_call=str(row.get("type") or row.get("put_call") or row.get("Type", "CALL")).upper(),
                    bid=_safe_float(row.get("bid") or row.get("Bid")),
                    ask=_safe_float(row.get("ask") or row.get("Ask")),
                    last=_safe_float(row.get("last") or row.get("Last")),
                    mark=_safe_float(row.get("mark") or row.get("Mark")),
                    delta=_safe_float(row.get("delta") or row.get("Delta")),
                    gamma=_safe_float(row.get("gamma") or row.get("Gamma")),
                    theta=_safe_float(row.get("theta") or row.get("Theta")),
                    vega=_safe_float(row.get("vega") or row.get("Vega")),
                    volatility=_safe_float(row.get("iv") or row.get("IV") or row.get("volatility")),
                    open_interest=_safe_int(row.get("open_interest") or row.get("Open Interest") or row.get("oi")),
                    total_volume=_safe_int(row.get("volume") or row.get("total_volume") or row.get("Volume")),
                    in_the_money=bool(row.get("in_the_money") or row.get("inTheMoney") or "").lower() == "true",
                    raw=row,
                )
            )
        return contracts

    def _get_underlying_price(self, contracts: list[OptionContractRow]) -> float:
        for c in contracts:
            if c.underlying_price and c.underlying_price > 0:
                return c.underlying_price
        return 0.0
