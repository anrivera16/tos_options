from abc import ABC, abstractmethod
from typing import Any


class Strategy(ABC):
    name: str

    @abstractmethod
    def evaluate(self, snapshot_id: int, db_conn: Any) -> dict:
        ...
