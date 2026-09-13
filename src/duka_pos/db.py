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

#: Default database path, relative to the current working directory,
#: matching .env.example's DUKA_POS_DATABASE_PATH.
DEFAULT_DB_PATH = "data/duka_pos.sqlite"


def default_db_path() -> str:
    """Return the configured DB path (env override) or the sensible default.

    Reads DUKA_POS_DATABASE_PATH at call time (not import time) so tests
    and callers can change the environment without reloading this module.
    """
    return os.environ.get("DUKA_POS_DATABASE_PATH", DEFAULT_DB_PATH)


def connect(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with the required pragmas set.

    Creates the parent directory of a file-based path if needed (except
    for the special ':memory:' path, which is not used for real data but
    is convenient in some unit tests).
    """
    path = str(db_path) if db_path is not None else default_db_path()
    if path != ":memory:":
        parent = Path(path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)

    # check_same_thread=False: FastAPI/Starlette run sync endpoint functions
    # in a worker thread pool, so the connection may be used from a
    # different thread than the one that created it. Concurrent access is
    # still serialized by the caller (see api.py's connection lock) —
    # this flag only lifts sqlite3's same-thread check, it does not make
    # the connection safe for simultaneous use from multiple threads.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Apply the schema. Safe to call repeatedly (CREATE TABLE IF NOT EXISTS).

    Also applies small deterministic column migrations required by M2
    without a heavyweight migration tool.
    """
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    with conn:
        conn.executescript(schema_sql)
        # M2: optional shift linkage on sales (nullable for pre-M2 rows).
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(sales)").fetchall()
        }
        if "shift_id" not in cols:
            conn.execute(
                "ALTER TABLE sales ADD COLUMN shift_id INTEGER "
                "REFERENCES shifts (id)"
            )
        if "user_id" not in cols:
            conn.execute(
                "ALTER TABLE sales ADD COLUMN user_id INTEGER "
                "REFERENCES users (id)"
            )


def connect_and_init(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    """Convenience: open a connection and ensure the schema exists."""
    conn = connect(db_path)
    init_db(conn)
    return conn


@contextlib.contextmanager
def transaction(conn: sqlite3.Connection):
    """Run a block of writes as a single atomic SQLite transaction.

    Uses BEGIN IMMEDIATE to acquire the write lock up front. On any
    exception inside the block, the transaction is rolled back in full
    (no partial sale, no orphan stock deduction, no orphan payment) and
    the exception propagates to the caller. On success, the transaction
    is committed.

    No network calls must be made inside this block.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()
