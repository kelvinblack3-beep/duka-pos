from __future__ import annotations

import sqlite3

from duka_pos import products as products_module
from duka_pos import sales as sales_module


def _create_rice(conn: sqlite3.Connection):
    product = products_module.create_product(
        conn, name="Rice", unit="kg", cost_price_cents=12000, selling_price_cents=16000
    )
    products_module.add_stock(conn, product_id=product.id, quantity_milli=50000)
    return product


def test_duplicate_client_reference_does_not_create_second_sale(
    conn: sqlite3.Connection,
) -> None:
    rice = _create_rice(conn)
    lines = [{"product_id": rice.id, "quantity_milli": 1350}]

    first = sales_module.create_sale(conn, client_reference="dup-001", lines=lines)
    second = sales_module.create_sale(conn, client_reference="dup-001", lines=lines)

    assert first.id == second.id

    count = conn.execute(
        "SELECT COUNT(*) AS c FROM sales WHERE client_reference = ?", ("dup-001",)
    ).fetchone()["c"]
    assert count == 1


def test_duplicate_client_reference_does_not_deduct_stock_twice(
    conn: sqlite3.Connection,
) -> None:
    rice = _create_rice(conn)
    lines = [{"product_id": rice.id, "quantity_milli": 1350}]

    sales_module.create_sale(conn, client_reference="dup-002", lines=lines)
    sales_module.create_sale(conn, client_reference="dup-002", lines=lines)

    remaining = products_module.get_stock_balance_milli(conn, rice.id)
    assert remaining == 50000 - 1350  # only deducted once


def test_duplicate_client_reference_does_not_create_second_payment(
    conn: sqlite3.Connection,
) -> None:
    rice = _create_rice(conn)
    lines = [{"product_id": rice.id, "quantity_milli": 1350}]

    first = sales_module.create_sale(conn, client_reference="dup-003", lines=lines)
    sales_module.create_sale(conn, client_reference="dup-003", lines=lines)

    count = conn.execute(
        "SELECT COUNT(*) AS c FROM payments WHERE sale_id = ?", (first.id,)
    ).fetchone()["c"]
    assert count == 1


def test_duplicate_client_reference_does_not_create_second_receipt(
    conn: sqlite3.Connection,
) -> None:
    rice = _create_rice(conn)
    lines = [{"product_id": rice.id, "quantity_milli": 1350}]

    first = sales_module.create_sale(conn, client_reference="dup-004", lines=lines)
    sales_module.create_sale(conn, client_reference="dup-004", lines=lines)

    count = conn.execute(
        "SELECT COUNT(*) AS c FROM receipts WHERE sale_id = ?", (first.id,)
    ).fetchone()["c"]
    assert count == 1


def test_different_client_reference_creates_distinct_sales(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)
    lines = [{"product_id": rice.id, "quantity_milli": 1000}]

    first = sales_module.create_sale(conn, client_reference="ref-a", lines=lines)
    second = sales_module.create_sale(conn, client_reference="ref-b", lines=lines)

    assert first.id != second.id
    remaining = products_module.get_stock_balance_milli(conn, rice.id)
    assert remaining == 50000 - 1000 - 1000
