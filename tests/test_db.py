from __future__ import annotations

import sqlite3
from pathlib import Path

from duka_pos import db as db_module


def test_connect_and_init_creates_expected_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "sub" / "duka.sqlite"
    conn = db_module.connect_and_init(db_path)
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        expected = {
            "products",
            "stock_balances",
            "stock_movements",
            "sales",
            "sale_lines",
            "payments",
            "receipts",
        }
        assert expected.issubset(tables)
    finally:
        conn.close()


def test_connect_and_init_creates_parent_directory(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "dir" / "duka.sqlite"
    assert not db_path.parent.exists()
    conn = db_module.connect_and_init(db_path)
    conn.close()
    assert db_path.exists()


def test_foreign_keys_enabled(conn: sqlite3.Connection) -> None:
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1


def test_wal_mode_enabled(conn: sqlite3.Connection) -> None:
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0].lower() == "wal"


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "duka.sqlite"
    conn = db_module.connect(db_path)
    db_module.init_db(conn)
    db_module.init_db(conn)  # must not raise
    conn.close()


def test_transaction_commits_on_success(conn: sqlite3.Connection) -> None:
    from duka_pos import products as products_module

    product = products_module.create_product(
        conn, name="Sugar", unit="kg", cost_price_cents=10000, selling_price_cents=13000
    )
    assert product.id is not None
    # Data must be visible outside the transaction (it committed).
    row = conn.execute("SELECT * FROM products WHERE id = ?", (product.id,)).fetchone()
    assert row is not None


def test_transaction_rolls_back_on_exception(conn: sqlite3.Connection) -> None:
    before = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    try:
        with db_module.transaction(conn):
            conn.execute(
                """
                INSERT INTO products (
                    name, barcode, unit, cost_price_cents, selling_price_cents,
                    active, created_at, updated_at
                ) VALUES ('Ghost', NULL, 'kg', 100, 200, 1, 'x', 'x')
                """
            )
            raise RuntimeError("simulated failure mid-transaction")
    except RuntimeError:
        pass
    after = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    assert after == before, "a failed transaction must not leave partial writes"
