"""The locked M1 acceptance test: weighted rice sale.

Rice: cost 12000 cents/kg, selling price 16000 cents/kg, opening stock
50000 milli-kg. Sell 1350 milli-kg (1.35 kg).

Expected:
    sale total      = 21600 cents (KSh 216.00)
    remaining stock = 48650 milli-kg (48.65 kg)
    gross profit    = 5400 cents (KSh 54.00)
"""

from __future__ import annotations

import sqlite3

from duka_pos import products as products_module
from duka_pos import sales as sales_module


def _create_rice(conn: sqlite3.Connection):
    product = products_module.create_product(
        conn,
        name="Rice",
        unit="kg",
        cost_price_cents=12000,
        selling_price_cents=16000,
    )
    products_module.add_stock(conn, product_id=product.id, quantity_milli=50000)
    return product


def test_rice_acceptance_sale_total(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)
    sale = sales_module.create_sale(
        conn,
        client_reference="rice-sale-001",
        lines=[{"product_id": rice.id, "quantity_milli": 1350}],
    )
    assert sale.total_cents == 21600
    assert sale.subtotal_cents == 21600


def test_rice_acceptance_remaining_stock(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)
    sales_module.create_sale(
        conn,
        client_reference="rice-sale-002",
        lines=[{"product_id": rice.id, "quantity_milli": 1350}],
    )
    remaining = products_module.get_stock_balance_milli(conn, rice.id)
    assert remaining == 48650


def test_rice_acceptance_gross_profit(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)
    sale = sales_module.create_sale(
        conn,
        client_reference="rice-sale-003",
        lines=[{"product_id": rice.id, "quantity_milli": 1350}],
    )
    assert sale.gross_profit_cents == 5400


def test_rice_acceptance_cash_confirmed(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)
    sale = sales_module.create_sale(
        conn,
        client_reference="rice-sale-004",
        lines=[{"product_id": rice.id, "quantity_milli": 1350}],
    )
    assert sale.payment is not None
    assert sale.payment.method == "CASH"
    assert sale.payment.status == "CONFIRMED"
    assert sale.payment.amount_cents == 21600


def test_rice_acceptance_sale_retrieval(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)
    created = sales_module.create_sale(
        conn,
        client_reference="rice-sale-005",
        lines=[{"product_id": rice.id, "quantity_milli": 1350}],
    )
    fetched = sales_module.get_sale(conn, created.id)
    assert fetched.total_cents == 21600
    assert fetched.lines[0].product_name == "Rice"
    assert fetched.lines[0].quantity_milli == 1350
    assert fetched.lines[0].unit_price_cents == 16000


def test_rice_acceptance_receipt_retrieval(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)
    created = sales_module.create_sale(
        conn,
        client_reference="rice-sale-006",
        lines=[{"product_id": rice.id, "quantity_milli": 1350}],
    )
    receipt = sales_module.get_receipt(conn, created.id)
    assert receipt.total_cents == 21600
    assert receipt.subtotal_cents == 21600
    assert receipt.payment_method == "CASH"
    assert receipt.payment_status == "CONFIRMED"
    assert len(receipt.lines) == 1
    assert receipt.lines[0].product_name == "Rice"
    assert receipt.lines[0].line_total_cents == 21600
    # Cost/profit must never appear on a receipt.
    assert not hasattr(receipt.lines[0], "unit_cost_cents")
    assert not hasattr(receipt, "gross_profit_cents")


def test_multi_line_sale(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)
    sugar = products_module.create_product(
        conn, name="Sugar", unit="kg", cost_price_cents=10000, selling_price_cents=13000
    )
    products_module.add_stock(conn, product_id=sugar.id, quantity_milli=20000)

    sale = sales_module.create_sale(
        conn,
        client_reference="multi-001",
        lines=[
            {"product_id": rice.id, "quantity_milli": 1000},  # 1kg -> 16000 cents
            {"product_id": sugar.id, "quantity_milli": 2000},  # 2kg -> 26000 cents
        ],
    )
    assert sale.subtotal_cents == 16000 + 26000
    assert sale.total_cents == 42000
    assert len(sale.lines) == 2
