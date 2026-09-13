from __future__ import annotations

import sqlite3

import pytest

from duka_pos import products as products_module
from duka_pos.errors import InvalidProductData, InvalidQuantity, ProductNotFound
from duka_pos.money import InvalidProductUnit


def test_create_and_retrieve_product(conn: sqlite3.Connection) -> None:
    product = products_module.create_product(
        conn,
        name="Rice",
        unit="kg",
        cost_price_cents=12000,
        selling_price_cents=16000,
        barcode="RICE001",
    )
    assert product.id > 0
    assert product.name == "Rice"
    assert product.unit == "kg"
    assert product.cost_price_cents == 12000
    assert product.selling_price_cents == 16000
    assert product.active is True

    fetched = products_module.get_product(conn, product.id)
    assert fetched == product


def test_get_missing_product_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(ProductNotFound):
        products_module.get_product(conn, 999)


def test_create_product_new_product_has_zero_stock(conn: sqlite3.Connection) -> None:
    product = products_module.create_product(
        conn, name="Sugar", unit="kg", cost_price_cents=10000, selling_price_cents=13000
    )
    assert products_module.get_stock_balance_milli(conn, product.id) == 0


def test_add_stock_increases_balance(conn: sqlite3.Connection) -> None:
    product = products_module.create_product(
        conn, name="Rice", unit="kg", cost_price_cents=12000, selling_price_cents=16000
    )
    new_balance = products_module.add_stock(conn, product_id=product.id, quantity_milli=50000)
    assert new_balance == 50000

    new_balance = products_module.add_stock(conn, product_id=product.id, quantity_milli=1000)
    assert new_balance == 51000


def test_add_stock_records_movement(conn: sqlite3.Connection) -> None:
    product = products_module.create_product(
        conn, name="Rice", unit="kg", cost_price_cents=12000, selling_price_cents=16000
    )
    products_module.add_stock(conn, product_id=product.id, quantity_milli=50000)
    movement = conn.execute(
        "SELECT * FROM stock_movements WHERE product_id = ?", (product.id,)
    ).fetchone()
    assert movement["movement_type"] == "RECEIVE"
    assert movement["quantity_milli"] == 50000


def test_weighted_quantity_supports_fractional_kg(conn: sqlite3.Connection) -> None:
    """1.35 kg must be represented exactly as 1350 milli-kg, no float drift."""
    product = products_module.create_product(
        conn, name="Rice", unit="kg", cost_price_cents=12000, selling_price_cents=16000
    )
    products_module.add_stock(conn, product_id=product.id, quantity_milli=50000)
    balance = products_module.get_stock_balance_milli(conn, product.id)
    assert balance == 50000
    assert isinstance(balance, int)


def test_add_stock_rejects_zero_or_negative_quantity(conn: sqlite3.Connection) -> None:
    product = products_module.create_product(
        conn, name="Rice", unit="kg", cost_price_cents=12000, selling_price_cents=16000
    )
    with pytest.raises(InvalidQuantity):
        products_module.add_stock(conn, product_id=product.id, quantity_milli=0)
    with pytest.raises(InvalidQuantity):
        products_module.add_stock(conn, product_id=product.id, quantity_milli=-1000)


def test_add_stock_rejects_missing_product(conn: sqlite3.Connection) -> None:
    with pytest.raises(ProductNotFound):
        products_module.add_stock(conn, product_id=999, quantity_milli=1000)


def test_create_product_rejects_invalid_unit(conn: sqlite3.Connection) -> None:
    with pytest.raises(InvalidProductUnit):
        products_module.create_product(
            conn, name="Rice", unit="sack", cost_price_cents=12000, selling_price_cents=16000
        )


def test_create_product_rejects_empty_name(conn: sqlite3.Connection) -> None:
    with pytest.raises(InvalidProductData):
        products_module.create_product(
            conn, name="   ", unit="kg", cost_price_cents=12000, selling_price_cents=16000
        )


def test_create_product_rejects_negative_money(conn: sqlite3.Connection) -> None:
    from duka_pos.errors import InvalidMoney

    with pytest.raises(InvalidMoney):
        products_module.create_product(
            conn, name="Rice", unit="kg", cost_price_cents=-1, selling_price_cents=16000
        )
    with pytest.raises(InvalidMoney):
        products_module.create_product(
            conn, name="Rice", unit="kg", cost_price_cents=12000, selling_price_cents=-1
        )


def test_create_product_rejects_float_money(conn: sqlite3.Connection) -> None:
    from duka_pos.errors import InvalidMoney

    with pytest.raises(InvalidMoney):
        products_module.create_product(
            conn, name="Rice", unit="kg", cost_price_cents=120.5, selling_price_cents=16000
        )


def test_create_product_duplicate_barcode_rejected(conn: sqlite3.Connection) -> None:
    products_module.create_product(
        conn,
        name="Rice",
        unit="kg",
        cost_price_cents=12000,
        selling_price_cents=16000,
        barcode="DUP001",
    )
    with pytest.raises(InvalidProductData):
        products_module.create_product(
            conn,
            name="Beans",
            unit="kg",
            cost_price_cents=8000,
            selling_price_cents=11000,
            barcode="DUP001",
        )


@pytest.mark.parametrize(
    "unit", ["kg", "g", "litre", "ml", "piece", "packet", "bottle", "box", "carton"]
)
def test_all_supported_units_accepted(conn: sqlite3.Connection, unit: str) -> None:
    product = products_module.create_product(
        conn, name=f"Item-{unit}", unit=unit, cost_price_cents=100, selling_price_cents=150
    )
    assert product.unit == unit
