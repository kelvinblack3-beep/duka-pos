from __future__ import annotations

import sqlite3

import pytest

from duka_pos import products as products_module
from duka_pos import sales as sales_module
from duka_pos.errors import (
    EmptySale,
    InvalidQuantity,
    InvalidSaleData,
    NonExactLineTotal,
    UnsupportedPaymentMethod,
)
from duka_pos.money import line_total_cents


def _create_rice(conn: sqlite3.Connection):
    product = products_module.create_product(
        conn, name="Rice", unit="kg", cost_price_cents=12000, selling_price_cents=16000
    )
    products_module.add_stock(conn, product_id=product.id, quantity_milli=50000)
    return product


def test_sale_rejects_zero_quantity_line(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)
    with pytest.raises(InvalidQuantity):
        sales_module.create_sale(
            conn,
            client_reference="invalid-qty-001",
            lines=[{"product_id": rice.id, "quantity_milli": 0}],
        )


def test_sale_rejects_negative_quantity_line(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)
    with pytest.raises(InvalidQuantity):
        sales_module.create_sale(
            conn,
            client_reference="invalid-qty-002",
            lines=[{"product_id": rice.id, "quantity_milli": -500}],
        )


def test_sale_rejects_empty_lines(conn: sqlite3.Connection) -> None:
    with pytest.raises(EmptySale):
        sales_module.create_sale(conn, client_reference="empty-001", lines=[])


def test_sale_rejects_blank_client_reference(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)
    with pytest.raises(InvalidSaleData):
        sales_module.create_sale(
            conn,
            client_reference="   ",
            lines=[{"product_id": rice.id, "quantity_milli": 1000}],
        )


def test_sale_rejects_unsupported_payment_method(conn: sqlite3.Connection) -> None:
    rice = _create_rice(conn)
    with pytest.raises(UnsupportedPaymentMethod):
        sales_module.create_sale(
            conn,
            client_reference="mpesa-not-yet-001",
            lines=[{"product_id": rice.id, "quantity_milli": 1000}],
            payment_method="MPESA",
        )


def test_line_total_cents_exact_division() -> None:
    assert line_total_cents(16000, 1350) == 21600


def test_line_total_cents_rejects_non_exact_result() -> None:
    # 333 cents * 1350 milli = 449550, not divisible by 1000.
    with pytest.raises(NonExactLineTotal):
        line_total_cents(333, 1350)


def test_sale_rejects_non_exact_line_total(conn: sqlite3.Connection) -> None:
    product = products_module.create_product(
        conn, name="Odd Priced Item", unit="piece", cost_price_cents=99, selling_price_cents=333
    )
    products_module.add_stock(conn, product_id=product.id, quantity_milli=5000)
    with pytest.raises(NonExactLineTotal):
        sales_module.create_sale(
            conn,
            client_reference="non-exact-001",
            lines=[{"product_id": product.id, "quantity_milli": 1350}],
        )
