"""SQLite persistence layer for Duka POS.

Per ADR-001: SQLite is the local source of truth. This module owns:

- the default/configurable database path
- opening connections with the required pragmas (foreign_keys, WAL)
- schema initialization
- a small transaction context manager so sale/stock/payment writes are
  atomic and roll back completely on any failure

No business logic (products, sales, pricing) lives in this module.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

DEFAULT_DB_PATH = "data/duka_pos.sqlite"


def default_db_path() -> str:
    return os.environ.get("DUKA_POS_DATABASE_PATH", DEFAULT_DB_PATH)


def connect(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    path = str(db_path) if db_path is not None else default_db_path()
    if path != ":memory:":
        parent = Path(path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    with conn:
        conn.executescript(schema_sql)
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(sales)").fetchall()}
        if "shift_id" not in cols:
            conn.execute("ALTER TABLE sales ADD COLUMN shift_id INTEGER REFERENCES shifts (id)")
        if "user_id" not in cols:
            conn.execute("ALTER TABLE sales ADD COLUMN user_id INTEGER REFERENCES users (id)")
        pay_cols = {row["name"] for row in conn.execute("PRAGMA table_info(payments)").fetchall()}
        for col, decl in (
            ("provider", "TEXT"),
            ("provider_checkout_request_id", "TEXT"),
            ("provider_merchant_request_id", "TEXT"),
            ("provider_receipt_number", "TEXT"),
            ("phone_number", "TEXT"),
            ("client_payment_reference", "TEXT"),
            ("updated_at", "TEXT"),
            ("last_error", "TEXT"),
        ):
            if col not in pay_cols:
                conn.execute(f"ALTER TABLE payments ADD COLUMN {col} {decl}")
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_provider_checkout
            ON payments (provider_checkout_request_id)
            WHERE provider_checkout_request_id IS NOT NULL"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments (status)")
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_payments_client_payment_ref
            ON payments (client_payment_reference)
            WHERE client_payment_reference IS NOT NULL"""
        )
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_provider_merchant
            ON payments (provider_merchant_request_id)
            WHERE provider_merchant_request_id IS NOT NULL"""
        )
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_provider_receipt
            ON payments (provider_receipt_number)
            WHERE provider_receipt_number IS NOT NULL"""
        )


def connect_and_init(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    conn = connect(db_path)
    init_db(conn)
    return conn


@contextlib.contextmanager
def transaction(conn: sqlite3.Connection):
    """Run a block of writes as a single atomic SQLite transaction.

    No network calls must be made inside this block.
    """
    conn.commit()  # clear any implicit write txn from prior executes
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()
