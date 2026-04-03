from __future__ import annotations

from copy import deepcopy

from schwab.models import flatten_option_chain


def test_flatten_option_chain_uses_chain_level_underlying_and_snapshot(option_chain_fixture: dict) -> None:
    chain = deepcopy(option_chain_fixture)
    chain["underlying"] = {"symbol": "SPY", "last": 634.09}

    for strike_map in (chain["callExpDateMap"], chain["putExpDateMap"]):
        for contracts_by_strike in strike_map.values():
            for contracts in contracts_by_strike.values():
                for contract in contracts:
                    contract.pop("underlyingPrice", None)
                    contract["mark"] = 0.05
                    contract["last"] = 0.05

    rows = flatten_option_chain(chain, "SPY")

    assert rows
    captured_at_values = {row.snapshot_captured_at for row in rows}
    assert len(captured_at_values) == 1
    assert next(iter(captured_at_values)) is not None
    assert all(row.underlying_price == 634.09 for row in rows)
    assert all(row.expiration_date for row in rows)
    assert all(row.dte is not None for row in rows)
    assert all(row.strike > 0 for row in rows)


def test_flatten_option_chain_prefers_contract_underlying_over_chain_value(option_chain_fixture: dict) -> None:
    chain = deepcopy(option_chain_fixture)
    chain["underlying"]["last"] = 630.0
    contract = chain["putExpDateMap"]["2026-04-15:16"]["510.0"][0]
    contract["underlyingPrice"] = 631.5
    contract["mark"] = 0.05
    contract["last"] = 0.05

    rows = flatten_option_chain(chain, "SPY")
    matching = next(row for row in rows if row.symbol == "SPY_041526P510")

    assert matching.underlying_price == 631.5
