from __future__ import annotations

import sqlite3

import pytest

from duka_pos import products as products_module
from duka_pos import sales as sales_module
from duka_pos.errors import InsufficientStock, ProductNotFound


def _create_rice(conn: sqlite3.Connection):
    product = products_module.create_product(
        conn, name="Rice", unit="kg", cost_price_cents=12000, selling_price_cents=16000
    )
    products_module.add_stock(conn, product_id=product.id, quantity_milli=50000)
    return product


def test_insufficient_stock_rolls_back_entire_sale(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)
    sugar = products_module.create_product(
        conn, name="Sugar", unit="kg", cost_price_cents=10000, selling_price_cents=13000
    )
    products_module.add_stock(conn, product_id=sugar.id, quantity_milli=500)  # only 0.5kg

    with pytest.raises(InsufficientStock):
        sales_module.create_sale(
            conn,
            client_reference="rollback-001",
            lines=[
                {"product_id": rice.id, "quantity_milli": 1000},  # this would succeed alone
                {"product_id": sugar.id, "quantity_milli": 2000},  # this fails: only 500 in stock
            ],
        )

    # Rice stock must NOT have been deducted even though its line was valid —
    # the whole sale is one atomic transaction.
    rice_balance = products_module.get_stock_balance_milli(conn, rice.id)
    assert rice_balance == 50000

    sugar_balance = products_module.get_stock_balance_milli(conn, sugar.id)
    assert sugar_balance == 500

    # No sale, no sale lines, no payment, no receipt must exist.
    sale_count = conn.execute(
        "SELECT COUNT(*) AS c FROM sales WHERE client_reference = ?", ("rollback-001",)
    ).fetchone()["c"]
    assert sale_count == 0
    line_count = conn.execute("SELECT COUNT(*) AS c FROM sale_lines").fetchone()["c"]
    assert line_count == 0
    payment_count = conn.execute("SELECT COUNT(*) AS c FROM payments").fetchone()["c"]
    assert payment_count == 0
    receipt_count = conn.execute("SELECT COUNT(*) AS c FROM receipts").fetchone()["c"]
    assert receipt_count == 0


def test_sale_with_missing_product_rolls_back(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)

    with pytest.raises(ProductNotFound):
        sales_module.create_sale(
            conn,
            client_reference="rollback-002",
            lines=[
                {"product_id": rice.id, "quantity_milli": 1000},
                {"product_id": 999999, "quantity_milli": 1000},
            ],
        )

    rice_balance = products_module.get_stock_balance_milli(conn, rice.id)
    assert rice_balance == 50000
    sale_count = conn.execute(
        "SELECT COUNT(*) AS c FROM sales WHERE client_reference = ?", ("rollback-002",)
    ).fetchone()["c"]
    assert sale_count == 0


def test_no_orphan_payment_without_sale(conn: sqlite3.Connection) -> None:
    """If sale creation fails, there must be no payment row at all."""
    rice = _create_rice(conn)
    with pytest.raises(InsufficientStock):
        sales_module.create_sale(
            conn,
            client_reference="rollback-003",
            lines=[{"product_id": rice.id, "quantity_milli": 999999}],
        )
    payment_count = conn.execute("SELECT COUNT(*) AS c FROM payments").fetchone()["c"]
    assert payment_count == 0
