from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "out/options_history.sqlite3"


def _is_postgres(db_path: str) -> bool:
    return db_path.startswith("postgresql://") or db_path.startswith("postgres://")


def get_connection(db_path: str = DEFAULT_DB_PATH):
    """Return a DB connection — sqlite3.Connection or psycopg connection."""
    if _is_postgres(db_path):
        import psycopg
        conn = psycopg.connect(db_path)
        conn.autocommit = True
        return conn
    else:
        output_path = Path(db_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(output_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _ph(conn) -> str:
    """Return placeholder character: %s for postgres, ? for sqlite."""
    import psycopg
    if isinstance(conn, psycopg.Connection):
        return "%s"
    return "?"


def init_db(connection) -> None:
    import psycopg
    if isinstance(connection, psycopg.Connection):
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id BIGSERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                underlying_price DOUBLE PRECISION,
                source TEXT NOT NULL,
                chain_json TEXT,
                created_at TEXT NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS option_contracts (
                id BIGSERIAL PRIMARY KEY,
                snapshot_id BIGINT NOT NULL,
                snapshot_captured_at TEXT,
                symbol TEXT NOT NULL,
                underlying_symbol TEXT,
                underlying_price DOUBLE PRECISION,
                expiration_date TEXT NOT NULL,
                dte INTEGER,
                strike DOUBLE PRECISION NOT NULL,
                put_call TEXT NOT NULL,
                bid DOUBLE PRECISION,
                ask DOUBLE PRECISION,
                last DOUBLE PRECISION,
                mark DOUBLE PRECISION,
                delta DOUBLE PRECISION,
                gamma DOUBLE PRECISION,
                theta DOUBLE PRECISION,
                vega DOUBLE PRECISION,
                volatility DOUBLE PRECISION,
                open_interest INTEGER,
                total_volume INTEGER,
                in_the_money INTEGER,
                -- Tier 1: liquidity flow
                bid_size INTEGER,
                ask_size INTEGER,
                last_size INTEGER,
                -- Tier 1: premium momentum
                open_price DOUBLE PRECISION,
                high_price DOUBLE PRECISION,
                low_price DOUBLE PRECISION,
                close_price DOUBLE PRECISION,
                percent_change DOUBLE PRECISION,
                -- Tier 1: mispricing + decomposition
                theoretical_option_value DOUBLE PRECISION,
                time_value DOUBLE PRECISION,
                intrinsic_value DOUBLE PRECISION,
                raw_json TEXT,
                FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS aggregates_by_strike (
                snapshot_id BIGINT NOT NULL,
                strike DOUBLE PRECISION NOT NULL,
                net_gex DOUBLE PRECISION NOT NULL,
                call_gex DOUBLE PRECISION NOT NULL,
                put_gex DOUBLE PRECISION NOT NULL,
                net_dex DOUBLE PRECISION NOT NULL,
                net_vex DOUBLE PRECISION NOT NULL,
                net_tex DOUBLE PRECISION NOT NULL,
                open_interest_total DOUBLE PRECISION NOT NULL,
                volume_total DOUBLE PRECISION NOT NULL,
                contracts_count INTEGER NOT NULL,
                expirations_json TEXT NOT NULL,
                PRIMARY KEY (snapshot_id, strike),
                FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS aggregates_by_expiry (
                snapshot_id BIGINT NOT NULL,
                expiration_date TEXT NOT NULL,
                dte INTEGER,
                net_gex DOUBLE PRECISION NOT NULL,
                call_gex DOUBLE PRECISION NOT NULL,
                put_gex DOUBLE PRECISION NOT NULL,
                net_dex DOUBLE PRECISION NOT NULL,
                net_vex DOUBLE PRECISION NOT NULL,
                net_tex DOUBLE PRECISION NOT NULL,
                call_oi DOUBLE PRECISION NOT NULL,
                put_oi DOUBLE PRECISION NOT NULL,
                total_oi DOUBLE PRECISION NOT NULL,
                total_volume DOUBLE PRECISION NOT NULL,
                pcr_oi DOUBLE PRECISION,
                pcr_volume DOUBLE PRECISION,
                atm_iv DOUBLE PRECISION,
                PRIMARY KEY (snapshot_id, expiration_date),
                FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS aggregates_by_bucket (
                snapshot_id BIGINT NOT NULL,
                bucket_type TEXT NOT NULL,
                bucket_label TEXT NOT NULL,
                net_gex DOUBLE PRECISION NOT NULL,
                net_dex DOUBLE PRECISION NOT NULL,
                net_vex DOUBLE PRECISION NOT NULL,
                net_tex DOUBLE PRECISION NOT NULL,
                call_oi DOUBLE PRECISION NOT NULL,
                put_oi DOUBLE PRECISION NOT NULL,
                total_oi DOUBLE PRECISION NOT NULL,
                total_volume DOUBLE PRECISION NOT NULL,
                contracts_count INTEGER NOT NULL,
                PRIMARY KEY (snapshot_id, bucket_type, bucket_label),
                FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
            );
            """
        )
    else:
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
                -- Tier 1: liquidity flow
                bid_size INTEGER,
                ask_size INTEGER,
                last_size INTEGER,
                -- Tier 1: premium momentum
                open_price REAL,
                high_price REAL,
                low_price REAL,
                close_price REAL,
                percent_change REAL,
                -- Tier 1: mispricing + decomposition
                theoretical_option_value REAL,
                time_value REAL,
                intrinsic_value REAL,
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
    connection,
    *,
    symbol: str,
    captured_at: str,
    underlying_price: float | None,
    source: str,
    chain_payload: dict[str, Any] | None,
    skip_raw_json: bool = False,
) -> int:
    chain_json = (
        None
        if skip_raw_json
        else (json.dumps(chain_payload) if chain_payload is not None else None)
    )
    ph = _ph(connection)
    import psycopg
    if isinstance(connection, psycopg.Connection):
        cursor = connection.execute(
            f"""
            INSERT INTO snapshots (symbol, captured_at, underlying_price, source, chain_json)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
            RETURNING id
            """,
            (symbol, captured_at, underlying_price, source, chain_json),
        )
        snapshot_id = cursor.fetchone()[0]
    else:
        cursor = connection.execute(
            """
            INSERT INTO snapshots (symbol, captured_at, underlying_price, source, chain_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (symbol, captured_at, underlying_price, source, chain_json),
        )
        connection.commit()
        snapshot_id = int(cursor.lastrowid)

    return snapshot_id


def insert_option_contracts(
    connection,
    snapshot_id: int,
    rows: list[dict[str, Any]],
    skip_raw_json: bool = False,
) -> None:
    payload = []
    for row in rows:
        raw = (
            None
            if skip_raw_json
            else (json.dumps(row.get("raw")) if row.get("raw") is not None else None)
        )
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
                1
                if row.get("in_the_money")
                else 0
                if row.get("in_the_money") is not None
                else None,
                # Tier 1: liquidity flow
                row.get("bid_size"),
                row.get("ask_size"),
                row.get("last_size"),
                # Tier 1: premium momentum
                row.get("open_price"),
                row.get("high_price"),
                row.get("low_price"),
                row.get("close_price"),
                row.get("percent_change"),
                # Tier 1: mispricing + decomposition
                row.get("theoretical_option_value"),
                row.get("time_value"),
                row.get("intrinsic_value"),
                raw,
            )
        )

    ph = _ph(connection)
    columns = [
        "snapshot_id", "snapshot_captured_at", "symbol", "underlying_symbol",
        "underlying_price", "expiration_date", "dte", "strike", "put_call",
        "bid", "ask", "last", "mark", "delta", "gamma", "theta", "vega",
        "volatility", "open_interest", "total_volume", "in_the_money",
        # Tier 1 columns
        "bid_size", "ask_size", "last_size",
        "open_price", "high_price", "low_price", "close_price", "percent_change",
        "theoretical_option_value", "time_value", "intrinsic_value",
        "raw_json",
    ]
    placeholders = ", ".join([ph] * len(columns))
    col_str = ", ".join(columns)
    sql = f"INSERT INTO option_contracts ({col_str}) VALUES ({placeholders})"

    import psycopg
    if isinstance(connection, psycopg.Connection):
        with connection.transaction():
            with connection.cursor() as cur:
                cur.executemany(sql, payload)
    else:
        connection.executemany(sql, payload)
        connection.commit()


def insert_aggregate_rows(
    connection,
    table_name: str,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    # Primary key columns per table for ON CONFLICT
    PK_COLUMNS = {
        "aggregates_by_strike": ("snapshot_id", "strike"),
        "aggregates_by_expiry": ("snapshot_id", "expiration_date"),
        "aggregates_by_bucket": ("snapshot_id", "bucket_type", "bucket_label"),
    }

    columns = list(rows[0].keys())
    ph = _ph(connection)
    placeholders = ", ".join([ph] * len(columns))

    import psycopg
    if isinstance(connection, psycopg.Connection):
        pk = PK_COLUMNS.get(table_name, columns[:1])
        conflict_cols = ", ".join(pk)
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in pk)
        sql = (
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_cols}) DO UPDATE SET {updates}"
        )
    else:
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

    if isinstance(connection, psycopg.Connection):
        with connection.transaction():
            with connection.cursor() as cur:
                cur.executemany(sql, payload)
    else:
        connection.executemany(sql, payload)
        connection.commit()
