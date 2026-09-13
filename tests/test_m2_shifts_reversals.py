"""M2 shifts and sale reversal tests."""

from __future__ import annotations

import sqlite3

import pytest

from duka_pos import products as products_module
from duka_pos import reversals as reversals_module
from duka_pos import sales as sales_module
from duka_pos import shifts as shifts_module
from duka_pos import users as users_module
from duka_pos.errors import (
    SaleAlreadyReversed,
    ShiftAlreadyOpen,
    ShiftAlreadyClosed,
)


def _owner(conn: sqlite3.Connection):
    return users_module.create_user(
        conn, username="shiftowner", password="securepass1", role="OWNER"
    )


def _rice_sale(conn: sqlite3.Connection, *, shift_id=None, user_id=None, ref="rice-m2"):
    product = products_module.create_product(
        conn, name="Rice", unit="kg", cost_price_cents=12000, selling_price_cents=16000
    )
    products_module.add_stock(conn, product_id=product.id, quantity_milli=50000)
    sale = sales_module.create_sale(
        conn,
        client_reference=ref,
        lines=[{"product_id": product.id, "quantity_milli": 1350}],
        user_id=user_id,
        shift_id=shift_id,
    )
    return product, sale


def test_open_and_close_shift(conn: sqlite3.Connection) -> None:
    owner = _owner(conn)
    shift = shifts_module.open_shift(conn, user_id=owner.id, opening_cash_cents=50000)
    assert shift.status == "OPEN"
    assert shift.opening_cash_cents == 50000

    closed = shifts_module.close_shift(
        conn, shift_id=shift.id, closing_cash_cents=70000, acting_user_id=owner.id
    )
    assert closed.status == "CLOSED"
    assert closed.closing_cash_cents == 70000
    assert closed.expected_cash_cents is not None
    assert closed.variance_cents == closed.closing_cash_cents - closed.expected_cash_cents


def test_duplicate_open_shift_rejected(conn: sqlite3.Connection) -> None:
    owner = _owner(conn)
    shifts_module.open_shift(conn, user_id=owner.id, opening_cash_cents=0)
    with pytest.raises(ShiftAlreadyOpen):
        shifts_module.open_shift(conn, user_id=owner.id, opening_cash_cents=0)


def test_close_already_closed_rejected(conn: sqlite3.Connection) -> None:
    owner = _owner(conn)
    shift = shifts_module.open_shift(conn, user_id=owner.id, opening_cash_cents=0)
    shifts_module.close_shift(
        conn, shift_id=shift.id, closing_cash_cents=0, acting_user_id=owner.id
    )
    with pytest.raises(ShiftAlreadyClosed):
        shifts_module.close_shift(
            conn, shift_id=shift.id, closing_cash_cents=0, acting_user_id=owner.id
        )


def test_void_sale_restores_stock_and_preserves_original(
    conn: sqlite3.Connection,
) -> None:
    owner = _owner(conn)
    product, sale = _rice_sale(conn, user_id=owner.id, ref="void-001")
    assert sale.total_cents == 21600
    remaining_before = products_module.get_stock_balance_milli(conn, product.id)
    assert remaining_before == 48650

    rev = reversals_module.void_sale(
        conn, sale_id=sale.id, performed_by=owner.id, reason="customer changed mind"
    )
    assert rev.sale_id == sale.id
    assert rev.reversal_type == "VOID"

    remaining_after = products_module.get_stock_balance_milli(conn, product.id)
    assert remaining_after == 50000  # fully restored

    fetched = sales_module.get_sale(conn, sale.id)
    assert fetched.total_cents == 21600  # historical total preserved
    row = conn.execute("SELECT status FROM sales WHERE id = ?", (sale.id,)).fetchone()
    assert row["status"] == "VOID"

    with pytest.raises(SaleAlreadyReversed):
        reversals_module.void_sale(conn, sale_id=sale.id, performed_by=owner.id)


def test_shift_expected_cash_includes_sale(conn: sqlite3.Connection) -> None:
    owner = _owner(conn)
    shift = shifts_module.open_shift(conn, user_id=owner.id, opening_cash_cents=10000)
    _rice_sale(conn, shift_id=shift.id, user_id=owner.id, ref="shift-cash-001")
    closed = shifts_module.close_shift(
        conn, shift_id=shift.id, closing_cash_cents=31600, acting_user_id=owner.id
    )
    assert closed.expected_cash_cents == 31600
    assert closed.variance_cents == 0
