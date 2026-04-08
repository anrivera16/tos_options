from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schwab.models import OptionContractRow


@dataclass
class Snapshot:
    symbol: str
    captured_at: datetime
    underlying_price: float
    contracts: list[OptionContractRow]
    raw_payload: dict | None = None
    source: str = "unknown"


class DataSource(ABC):
    @abstractmethod
    def fetch_snapshot(self, symbol: str) -> Snapshot:
        ...

    @abstractmethod
    def has_more(self) -> bool:
        ...
