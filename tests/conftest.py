from __future__ import annotations

from copy import deepcopy
import sqlite3
from typing import Generator

import pytest


@pytest.fixture
def option_chain_fixture() -> dict:
    return {
        "symbol": "SPY",
        "underlying": {
            "symbol": "SPY",
            "last": 500.0,
        },
        "callExpDateMap": {
            "2026-04-01:2": {
                "495.0": [
                    {
                        "symbol": "SPY_040126C495",
                        "putCall": "CALL",
                        "underlyingPrice": 500.0,
                        "expirationDate": "2026-04-01T00:00:00",
                        "daysToExpiration": 2,
                        "bid": 6.0,
                        "ask": 6.2,
                        "last": 6.1,
                        "mark": 6.1,
                        "delta": 0.6,
                        "gamma": 0.01,
                        "theta": -0.2,
                        "vega": 0.12,
                        "volatility": 0.2,
                        "openInterest": 100,
                        "totalVolume": 10,
                        "inTheMoney": True,
                    }
                ],
                "505.0": [
                    {
                        "symbol": "SPY_040126C505",
                        "putCall": "CALL",
                        "underlyingPrice": 500.0,
                        "expirationDate": "2026-04-01T00:00:00",
                        "daysToExpiration": 2,
                        "bid": 4.0,
                        "ask": 4.2,
                        "last": 4.1,
                        "mark": 4.1,
                        "delta": 0.4,
                        "gamma": 0.008,
                        "theta": -0.15,
                        "vega": 0.1,
                        "volatility": 0.22,
                        "openInterest": 80,
                        "totalVolume": 12,
                        "inTheMoney": False,
                    }
                ],
            },
            "2026-04-15:16": {
                "500.0": [
                    {
                        "symbol": "SPY_041526C500",
                        "putCall": "CALL",
                        "underlyingPrice": 500.0,
                        "expirationDate": "2026-04-15T00:00:00",
                        "daysToExpiration": 16,
                        "bid": 8.0,
                        "ask": 8.4,
                        "last": 8.2,
                        "mark": 8.2,
                        "delta": 0.5,
                        "gamma": 0.006,
                        "theta": -0.1,
                        "vega": 0.11,
                        "volatility": 0.18,
                        "openInterest": 50,
                        "totalVolume": 8,
                        "inTheMoney": False,
                    }
                ]
            },
        },
        "putExpDateMap": {
            "2026-04-01:2": {
                "495.0": [
                    {
                        "symbol": "SPY_040126P495",
                        "putCall": "PUT",
                        "underlyingPrice": 500.0,
                        "expirationDate": "2026-04-01T00:00:00",
                        "daysToExpiration": 2,
                        "bid": 2.0,
                        "ask": 2.2,
                        "last": 2.1,
                        "mark": 2.1,
                        "delta": -0.35,
                        "gamma": 0.009,
                        "theta": -0.18,
                        "vega": 0.09,
                        "volatility": 0.24,
                        "openInterest": 90,
                        "totalVolume": 14,
                        "inTheMoney": False,
                    }
                ]
            },
            "2026-04-15:16": {
                "500.0": [
                    {
                        "symbol": "SPY_041526P500",
                        "putCall": "PUT",
                        "underlyingPrice": 500.0,
                        "expirationDate": "2026-04-15T00:00:00",
                        "daysToExpiration": 16,
                        "bid": 7.0,
                        "ask": 7.3,
                        "last": 7.1,
                        "mark": 7.1,
                        "delta": -0.45,
                        "gamma": 0.007,
                        "theta": -0.11,
                        "vega": 0.1,
                        "volatility": 0.21,
                        "openInterest": 70,
                        "totalVolume": 9,
                        "inTheMoney": True,
                    }
                ],
                "510.0": [
                    {
                        "symbol": "SPY_041526P510",
                        "putCall": "PUT",
                        "underlyingPrice": 500.0,
                        "expirationDate": "2026-04-15T00:00:00",
                        "daysToExpiration": 16,
                        "bid": 11.0,
                        "ask": 11.4,
                        "last": 11.2,
                        "mark": 11.2,
                        "delta": -0.55,
                        "gamma": 0.005,
                        "theta": -0.09,
                        "vega": 0.08,
                        "volatility": 0.19,
                        "openInterest": 60,
                        "totalVolume": 7,
                        "inTheMoney": True,
                    }
                ],
            },
        },
    }


@pytest.fixture
def option_rows_fixture(option_chain_fixture: dict) -> list[dict]:
    from schwab.models import flatten_option_chain

    return [row.to_dict() for row in flatten_option_chain(deepcopy(option_chain_fixture), "SPY")]


@pytest.fixture
def sqlite_connection() -> Generator[sqlite3.Connection, None, None]:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    yield connection
    connection.close()
