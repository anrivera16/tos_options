from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import psycopg

    from z0dte.sources.base import DataSource
    from z0dte.signals.base import Signal

from z0dte.ingestion.normalizer import normalize_contract_for_db, normalize_snapshot_for_db


class IngestionPipeline:
    def __init__(
        self,
        source: DataSource,
        db_conn: psycopg.Connection,
        signals: list[Signal] | None = None,
    ) -> None:
        self.source = source
        self.db = db_conn
        self.signals = signals or []

    def run_one(self, symbol: str) -> int:
        try:
            snapshot = self.source.fetch_snapshot(symbol)
            snapshot_id = self._write_snapshot(snapshot)
            self._write_contracts(snapshot_id, snapshot)

            for signal in self.signals:
                try:
                    signal.compute(snapshot_id, self.db)
                except Exception as e:
                    print(f"  Signal error ({signal.name}): {e}")
                    self.db.rollback()
                    continue

            self.db.commit()
            return snapshot_id
        except Exception as e:
            self.db.rollback()
            raise

    def run_backtest(self, symbol: str) -> None:
        while self.source.has_more():
            self.run_one(symbol)

    def _write_snapshot(self, snapshot: Any) -> int:
        data = normalize_snapshot_for_db(snapshot)
        result = self.db.execute(
            """
            INSERT INTO snapshots_0dte
                (symbol, captured_at, underlying_price, source, is_backtest, chain_json)
            VALUES
                (%(symbol)s, %(captured_at)s, %(underlying_price)s, %(source)s, %(is_backtest)s, %(chain_json)s)
            ON CONFLICT (symbol, captured_at, is_backtest) DO UPDATE
            SET underlying_price = EXCLUDED.underlying_price,
                chain_json = EXCLUDED.chain_json
            RETURNING id
            """,
            data,
        )
        self.db.commit()
        return result.fetchone()["id"]

    def _write_contracts(self, snapshot_id: int, snapshot: Any) -> None:
        for contract in snapshot.contracts:
            data = normalize_contract_for_db(contract, snapshot_id)
            self.db.execute(
                """
                INSERT INTO contracts_0dte
                    (snapshot_id, symbol, underlying_symbol, underlying_price,
                     expiration_date, dte, strike, put_call,
                     bid, ask, last, mark,
                     delta, gamma, theta, vega, volatility,
                     open_interest, total_volume, in_the_money,
                     volume_at_bid, volume_at_ask, raw_json)
                VALUES
                    (%(snapshot_id)s, %(symbol)s, %(underlying_symbol)s, %(underlying_price)s,
                     %(expiration_date)s, %(dte)s, %(strike)s, %(put_call)s,
                     %(bid)s, %(ask)s, %(last)s, %(mark)s,
                     %(delta)s, %(gamma)s, %(theta)s, %(vega)s, %(volatility)s,
                     %(open_interest)s, %(total_volume)s, %(in_the_money)s,
                     %(volume_at_bid)s, %(volume_at_ask)s, %(raw_json)s)
                """,
                data,
            )
        self.db.commit()
