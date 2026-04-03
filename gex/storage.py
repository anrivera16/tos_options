from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = "out/options_history.sqlite3"


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    output_path = Path(db_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(output_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            underlying_price REAL,
            source TEXT NOT NULL,
            chain_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS option_contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            snapshot_captured_at TEXT,
            symbol TEXT NOT NULL,
            underlying_symbol TEXT,
            underlying_price REAL,
            expiration_date TEXT NOT NULL,
            dte INTEGER,
            strike REAL NOT NULL,
            put_call TEXT NOT NULL,
            bid REAL,
            ask REAL,
            last REAL,
            mark REAL,
            delta REAL,
            gamma REAL,
            theta REAL,
            vega REAL,
            volatility REAL,
            open_interest INTEGER,
            total_volume INTEGER,
            in_the_money INTEGER,
            raw_json TEXT,
            FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS aggregates_by_strike (
            snapshot_id INTEGER NOT NULL,
            strike REAL NOT NULL,
            net_gex REAL NOT NULL,
            call_gex REAL NOT NULL,
            put_gex REAL NOT NULL,
            net_dex REAL NOT NULL,
            net_vex REAL NOT NULL,
            net_tex REAL NOT NULL,
            open_interest_total REAL NOT NULL,
            volume_total REAL NOT NULL,
            contracts_count INTEGER NOT NULL,
            expirations_json TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, strike),
            FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS aggregates_by_expiry (
            snapshot_id INTEGER NOT NULL,
            expiration_date TEXT NOT NULL,
            dte INTEGER,
            net_gex REAL NOT NULL,
            call_gex REAL NOT NULL,
            put_gex REAL NOT NULL,
            net_dex REAL NOT NULL,
            net_vex REAL NOT NULL,
            net_tex REAL NOT NULL,
            call_oi REAL NOT NULL,
            put_oi REAL NOT NULL,
            total_oi REAL NOT NULL,
            total_volume REAL NOT NULL,
            pcr_oi REAL,
            pcr_volume REAL,
            atm_iv REAL,
            PRIMARY KEY (snapshot_id, expiration_date),
            FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS aggregates_by_bucket (
            snapshot_id INTEGER NOT NULL,
            bucket_type TEXT NOT NULL,
            bucket_label TEXT NOT NULL,
            net_gex REAL NOT NULL,
            net_dex REAL NOT NULL,
            net_vex REAL NOT NULL,
            net_tex REAL NOT NULL,
            call_oi REAL NOT NULL,
            put_oi REAL NOT NULL,
            total_oi REAL NOT NULL,
            total_volume REAL NOT NULL,
            contracts_count INTEGER NOT NULL,
            PRIMARY KEY (snapshot_id, bucket_type, bucket_label),
            FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
        );
        """
    )
    connection.commit()


def insert_snapshot(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    captured_at: str,
    underlying_price: float | None,
    source: str,
    chain_payload: dict[str, Any] | None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO snapshots (symbol, captured_at, underlying_price, source, chain_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (symbol, captured_at, underlying_price, source, json.dumps(chain_payload) if chain_payload is not None else None),
    )
    connection.commit()
    return int(cursor.lastrowid)


def insert_option_contracts(
    connection: sqlite3.Connection,
    snapshot_id: int,
    rows: list[dict[str, Any]],
) -> None:
    payload = []
    for row in rows:
        payload.append(
            (
                snapshot_id,
                row.get("snapshot_captured_at"),
                row.get("symbol") or "",
                row.get("underlying_symbol"),
                row.get("underlying_price"),
                row.get("expiration_date") or "",
                row.get("dte"),
                row.get("strike") or 0.0,
                row.get("put_call") or "",
                row.get("bid"),
                row.get("ask"),
                row.get("last"),
                row.get("mark"),
                row.get("delta"),
                row.get("gamma"),
                row.get("theta"),
                row.get("vega"),
                row.get("volatility"),
                row.get("open_interest"),
                row.get("total_volume"),
                1 if row.get("in_the_money") else 0 if row.get("in_the_money") is not None else None,
                json.dumps(row.get("raw")) if row.get("raw") is not None else None,
            )
        )

    connection.executemany(
        """
        INSERT INTO option_contracts (
            snapshot_id,
            snapshot_captured_at,
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
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        payload,
    )
    connection.commit()


def insert_aggregate_rows(
    connection: sqlite3.Connection,
    table_name: str,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    columns = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
    payload = []
    for row in rows:
        values = []
        for column in columns:
            value = row.get(column)
            if isinstance(value, (dict, list)):
                values.append(json.dumps(value, sort_keys=True))
            else:
                values.append(value)
        payload.append(tuple(values))
    connection.executemany(sql, payload)
    connection.commit()
