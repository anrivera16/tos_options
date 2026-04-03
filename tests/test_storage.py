from __future__ import annotations

import json

from gex import compute_exposure_report
from gex.storage import init_db, insert_aggregate_rows, insert_option_contracts, insert_snapshot


def test_storage_schema_and_inserts(sqlite_connection, option_rows_fixture: list[dict], option_chain_fixture: dict) -> None:
    init_db(sqlite_connection)

    tables = {
        row[0]
        for row in sqlite_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"snapshots", "option_contracts", "aggregates_by_strike", "aggregates_by_expiry", "aggregates_by_bucket"}.issubset(tables)

    snapshot_id = insert_snapshot(
        sqlite_connection,
        symbol="SPY",
        captured_at=option_rows_fixture[0]["snapshot_captured_at"],
        underlying_price=500.0,
        source="pytest",
        chain_payload=option_chain_fixture,
    )
    insert_option_contracts(sqlite_connection, snapshot_id, option_rows_fixture)

    report = compute_exposure_report(option_rows_fixture)
    insert_aggregate_rows(
        sqlite_connection,
        "aggregates_by_strike",
        [
            {
                "snapshot_id": snapshot_id,
                "strike": row["strike"],
                "net_gex": row["net_gex"],
                "call_gex": row["call_gex"],
                "put_gex": row["put_gex"],
                "net_dex": row["net_dex"],
                "net_vex": row["net_vex"],
                "net_tex": row["net_tex"],
                "open_interest_total": row["total_oi"],
                "volume_total": row["total_volume"],
                "contracts_count": row["contracts_count"],
                "expirations_json": row["expirations"],
            }
            for row in report["by_strike"]
        ],
    )
    insert_aggregate_rows(
        sqlite_connection,
        "aggregates_by_expiry",
        [
            {
                "snapshot_id": snapshot_id,
                "expiration_date": row["expiration_date"],
                "dte": row["dte"],
                "net_gex": row["net_gex"],
                "call_gex": row["call_gex"],
                "put_gex": row["put_gex"],
                "net_dex": row["net_dex"],
                "net_vex": row["net_vex"],
                "net_tex": row["net_tex"],
                "call_oi": row["call_oi"],
                "put_oi": row["put_oi"],
                "total_oi": row["total_oi"],
                "total_volume": row["total_volume"],
                "pcr_oi": row["pcr_oi"],
                "pcr_volume": row["pcr_volume"],
                "atm_iv": row["atm_iv"],
            }
            for row in report["by_expiration"]
        ],
    )
    insert_aggregate_rows(
        sqlite_connection,
        "aggregates_by_bucket",
        [
            {
                "snapshot_id": snapshot_id,
                "bucket_type": row["bucket_type"],
                "bucket_label": row["bucket_label"],
                "net_gex": row["net_gex"],
                "net_dex": row["net_dex"],
                "net_vex": row["net_vex"],
                "net_tex": row["net_tex"],
                "call_oi": row["call_oi"],
                "put_oi": row["put_oi"],
                "total_oi": row["total_oi"],
                "total_volume": row["total_volume"],
                "contracts_count": row["contracts_count"],
            }
            for row in report["by_bucket"]
        ],
    )

    snapshot = sqlite_connection.execute(
        "SELECT symbol, underlying_price, source, chain_json FROM snapshots WHERE id = ?",
        (snapshot_id,),
    ).fetchone()
    assert snapshot["symbol"] == "SPY"
    assert snapshot["underlying_price"] == 500.0
    assert snapshot["source"] == "pytest"
    assert json.loads(snapshot["chain_json"])["symbol"] == "SPY"

    assert sqlite_connection.execute("SELECT COUNT(*) FROM option_contracts").fetchone()[0] == len(option_rows_fixture)
    assert sqlite_connection.execute("SELECT COUNT(*) FROM aggregates_by_strike").fetchone()[0] == len(report["by_strike"])
    assert sqlite_connection.execute("SELECT COUNT(*) FROM aggregates_by_expiry").fetchone()[0] == len(report["by_expiration"])
    assert sqlite_connection.execute("SELECT COUNT(*) FROM aggregates_by_bucket").fetchone()[0] == len(report["by_bucket"])

    contract_prices = sqlite_connection.execute(
        "SELECT MIN(underlying_price), MAX(underlying_price) FROM option_contracts"
    ).fetchone()
    assert contract_prices[0] == 500.0
    assert contract_prices[1] == 500.0


def test_insert_aggregate_rows_serializes_lists(sqlite_connection) -> None:
    init_db(sqlite_connection)
    sqlite_connection.execute(
        "INSERT INTO snapshots (id, symbol, captured_at, underlying_price, source) VALUES (1, 'SPY', '2026-03-30T00:00:00', 500.0, 'pytest')"
    )
    insert_aggregate_rows(
        sqlite_connection,
        "aggregates_by_strike",
        [
            {
                "snapshot_id": 1,
                "strike": 500.0,
                "net_gex": 1.0,
                "call_gex": 1.0,
                "put_gex": 0.0,
                "net_dex": 2.0,
                "net_vex": 3.0,
                "net_tex": 4.0,
                "open_interest_total": 5.0,
                "volume_total": 6.0,
                "contracts_count": 1,
                "expirations_json": ["2026-04-01", "2026-04-15"],
            }
        ],
    )

    stored = sqlite_connection.execute(
        "SELECT expirations_json FROM aggregates_by_strike WHERE snapshot_id = 1 AND strike = 500.0"
    ).fetchone()[0]
    assert json.loads(stored) == ["2026-04-01", "2026-04-15"]
