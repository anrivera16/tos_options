from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Signal(ABC):
    name: str
    table: str

    @abstractmethod
    def compute(self, snapshot_id: int, db_conn: Any) -> None:
        ...

    def _load_contracts(self, snapshot_id: int, db_conn: Any) -> list[dict]:
        return db_conn.execute(
            "SELECT * FROM contracts_0dte WHERE snapshot_id = %s",
            [snapshot_id],
        ).fetchall()

    def _load_snapshot(self, snapshot_id: int, db_conn: Any) -> dict:
        return db_conn.execute(
            "SELECT * FROM snapshots_0dte WHERE id = %s",
            [snapshot_id],
        ).fetchone()
