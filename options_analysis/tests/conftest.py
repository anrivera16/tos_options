from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / f"{name}.json") as f:
        return json.load(f)


@pytest.fixture
def pinned_chain():
    return load_fixture("pinned_chain")


@pytest.fixture
def short_gamma_breakout_chain():
    return load_fixture("short_gamma_breakout_chain")


@pytest.fixture
def balanced_chain():
    return load_fixture("balanced_chain")


@pytest.fixture
def high_iv_chain():
    return load_fixture("high_iv_chain")


@pytest.fixture
def partial_data_chain():
    return load_fixture("partial_data_chain")
