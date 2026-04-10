from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    import psycopg

from schwab.models import OptionContractRow

from z0dte.backtest.csv_loader import OptionSnapshot


class DBDataSource:
    def __init__(
        self,
        db_conn: psycopg.Connection,
        symbols: list[str] | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        source: str | None = None,
    ):
        self.db = db_conn
        self.symbols = symbols or ["SPY"]
        self.from_date = from_date
        self.to_date = to_date
        self.source = source
        self._snapshots: list[OptionSnapshot] = []
        self._loaded = False

    def load_snapshots(self) -> list[OptionSnapshot]:
        if self._loaded:
            return self._snapshots

        symbol_placeholders = ", ".join(f"${i+1}" for i in range(len(self.symbols)))
        params: list = list(self.symbols)

        query = f"""
            SELECT 
                s.id AS snapshot_id,
                s.symbol,
                s.captured_at,
                s.underlying_price
            FROM snapshots_0dte s
            WHERE s.symbol IN ({symbol_placeholders})
        """
        param_idx = len(self.symbols) + 1

        if self.source:
            query += f" AND s.source = ${param_idx}"
            params.append(self.source)
            param_idx += 1

        if self.from_date:
            query += f" AND s.captured_at >= ${param_idx}"
            params.append(self.from_date)
            param_idx += 1

        if self.to_date:
            query += f" AND s.captured_at <= ${param_idx}"
            params.append(self.to_date)

        query += " ORDER BY s.captured_at"

        rows = self.db.execute(query, tuple(params)).fetchall()

        for row in rows:
            snapshot_id = row["snapshot_id"]
            contracts = self._load_contracts(snapshot_id)

            timestamp = row["captured_at"]
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)

            self._snapshots.append(
                OptionSnapshot(
                    symbol=row["symbol"],
                    timestamp=timestamp,
                    underlying_price=row["underlying_price"],
                    contracts=contracts,
                )
            )

        self._loaded = True
        return self._snapshots

    def _load_contracts(self, snapshot_id: int) -> list[OptionContractRow]:
        query = """
            SELECT 
                symbol,
                underlying_symbol,
                underlying_price,
                expiration_date,
                dte,
                strike,
                put_call,
                bid,
                ask,
                last,
                mark,
                delta,
                gamma,
                theta,
                vega,
                volatility,
                open_interest,
                total_volume,
                in_the_money,
                raw_json
            FROM contracts_0dte
            WHERE snapshot_id = %s
            ORDER BY expiration_date, strike, put_call
        """
        rows = self.db.execute(query, (snapshot_id,)).fetchall()

        contracts = []
        for row in rows:
            raw_json = row["raw_json"]
            if isinstance(raw_json, str):
                import json as json_mod
                raw_json = json_mod.loads(raw_json)

            contracts.append(
                OptionContractRow(
                    snapshot_captured_at=None,
                    symbol=row["symbol"],
                    underlying_symbol=row["underlying_symbol"],
                    underlying_price=row["underlying_price"],
                    expiration_date=str(row["expiration_date"]),
                    dte=row["dte"],
                    strike=row["strike"],
                    put_call=row["put_call"],
                    bid=row["bid"],
                    ask=row["ask"],
                    last=row["last"],
                    mark=row["mark"],
                    delta=row["delta"],
                    gamma=row["gamma"],
                    theta=row["theta"],
                    vega=row["vega"],
                    volatility=row["volatility"],
                    open_interest=row["open_interest"],
                    total_volume=row["total_volume"],
                    in_the_money=row["in_the_money"],
                    raw=raw_json or {},
                )
            )
        return contracts

    def get_snapshots(
        self,
        symbols: list[str] | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[OptionSnapshot]:
        snapshots = self.load_snapshots()

        if symbols:
            snapshots = [s for s in snapshots if s.symbol in symbols]
        if from_date:
            snapshots = [s for s in snapshots if s.timestamp >= from_date]
        if to_date:
            snapshots = [s for s in snapshots if s.timestamp <= to_date]

        return snapshots

    def __iter__(self) -> Iterator[OptionSnapshot]:
        return iter(self.load_snapshots())

    def __len__(self) -> int:
        return len(self.load_snapshots())


class DBMultiSymbolLoader:
    def __init__(
        self,
        db_conn: psycopg.Connection,
        symbols: list[str],
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        source: str | None = None,
    ):
        self.db = db_conn
        self.symbols = symbols
        self.from_date = from_date
        self.to_date = to_date
        self.source = source
        self._snapshots: list[OptionSnapshot] = []
        self._loaded = False

    def load_all(self) -> list[OptionSnapshot]:
        if self._loaded:
            return self._snapshots

        symbol_placeholders = ", ".join(f"${i+1}" for i in range(len(self.symbols)))
        params: list = list(self.symbols)

        query = f"""
            SELECT 
                s.id AS snapshot_id,
                s.symbol,
                s.captured_at,
                s.underlying_price
            FROM snapshots_0dte s
            WHERE s.symbol IN ({symbol_placeholders})
        """
        param_idx = len(self.symbols) + 1

        if self.source:
            query += f" AND s.source = ${param_idx}"
            params.append(self.source)
            param_idx += 1

        if self.from_date:
            query += f" AND s.captured_at >= ${param_idx}"
            params.append(self.from_date)
            param_idx += 1

        if self.to_date:
            query += f" AND s.captured_at <= ${param_idx}"
            params.append(self.to_date)

        query += " ORDER BY s.captured_at"

        rows = self.db.execute(query, tuple(params)).fetchall()

        for row in rows:
            snapshot_id = row["snapshot_id"]
            contracts = self._load_contracts(snapshot_id)

            timestamp = row["captured_at"]
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)

            self._snapshots.append(
                OptionSnapshot(
                    symbol=row["symbol"],
                    timestamp=timestamp,
                    underlying_price=row["underlying_price"],
                    contracts=contracts,
                )
            )

        self._loaded = True
        return self._snapshots

    def _load_contracts(self, snapshot_id: int) -> list[OptionContractRow]:
        query = """
            SELECT 
                symbol,
                underlying_symbol,
                underlying_price,
                expiration_date,
                dte,
                strike,
                put_call,
                bid,
                ask,
                last,
                mark,
                delta,
                gamma,
                theta,
                vega,
                volatility,
                open_interest,
                total_volume,
                in_the_money,
                raw_json
            FROM contracts_0dte
            WHERE snapshot_id = %s
            ORDER BY expiration_date, strike, put_call
        """
        rows = self.db.execute(query, (snapshot_id,)).fetchall()

        contracts = []
        for row in rows:
            raw_json = row["raw_json"]
            if isinstance(raw_json, str):
                import json as json_mod
                raw_json = json_mod.loads(raw_json)

            contracts.append(
                OptionContractRow(
                    snapshot_captured_at=None,
                    symbol=row["symbol"],
                    underlying_symbol=row["underlying_symbol"],
                    underlying_price=row["underlying_price"],
                    expiration_date=str(row["expiration_date"]),
                    dte=row["dte"],
                    strike=row["strike"],
                    put_call=row["put_call"],
                    bid=row["bid"],
                    ask=row["ask"],
                    last=row["last"],
                    mark=row["mark"],
                    delta=row["delta"],
                    gamma=row["gamma"],
                    theta=row["theta"],
                    vega=row["vega"],
                    volatility=row["volatility"],
                    open_interest=row["open_interest"],
                    total_volume=row["total_volume"],
                    in_the_money=row["in_the_money"],
                    raw=raw_json or {},
                )
            )
        return contracts

    def __iter__(self) -> Iterator[OptionSnapshot]:
        return iter(self.load_all())

    def __len__(self) -> int:
        return len(self.load_all())
