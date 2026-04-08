from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import psycopg
import psycopg_pool
from psycopg.rows import dict_row

# Load environment variables from .env file
load_dotenv()


def get_connection(**overrides: Any) -> psycopg.Connection:
    params = {
        "host": os.environ.get("ZDT_DB_HOST", "localhost"),
        "port": int(os.environ.get("ZDT_DB_PORT", "5432")),
        "dbname": os.environ.get("ZDT_DB_NAME", "tos_0dte"),
        "user": os.environ.get("ZDT_DB_USER", os.environ.get("USER", "")),
        "password": os.environ.get("ZDT_DB_PASSWORD", ""),
    }
    params.update(overrides)
    return psycopg.connect(**params, row_factory=dict_row)


def get_pool(**overrides: Any) -> psycopg_pool.Pool:
    params = {
        "host": os.environ.get("ZDT_DB_HOST", "localhost"),
        "port": int(os.environ.get("ZDT_DB_PORT", "5432")),
        "dbname": os.environ.get("ZDT_DB_NAME", "tos_0dte"),
        "user": os.environ.get("ZDT_DB_USER", os.environ.get("USER", "")),
        "password": os.environ.get("ZDT_DB_PASSWORD", ""),
    }
    params.update(overrides)
    return psycopg_pool.Pool(**params, min_size=1, max_size=10, open=True)


def init_db(conn: psycopg.Connection) -> None:
    schema_path = Path(__file__).parent / "schema.sql"
    conn.executescript(schema_path.read_text())
    conn.commit()
