from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from schwab.client import create_client

from z0dte.sources.base import DataSource, Snapshot


def align_to_15min(dt: datetime) -> datetime:
    return dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)


class LiveDataSource(DataSource):
    def __init__(self) -> None:
        self.client = create_client()
        self.source = "schwab_live"

    def fetch_snapshot(self, symbol: str) -> Snapshot:
        from schwab.api import get_option_chain
        from schwab.models import flatten_option_chain

        chain_data = get_option_chain(
            symbol=symbol,
            days=7,
            contract_type="ALL",
            option_range="ALL",
            include_underlying_quote=True,
        )

        rows = flatten_option_chain(chain_data, symbol)
        underlying_price = rows[0].underlying_price if rows else 0.0
        captured_at = align_to_15min(datetime.now(ZoneInfo("US/Eastern")))

        return Snapshot(
            symbol=symbol,
            captured_at=captured_at,
            underlying_price=underlying_price,
            contracts=rows,
            raw_payload=chain_data,
            source=self.source,
        )

    def has_more(self) -> bool:
        return True
