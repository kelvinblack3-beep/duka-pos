"""Product and inventory (stock movement ledger) domain logic.

Cost price is part of the Product record because it is required to compute
gross profit and to stamp sale lines with unit_cost_cents at sale time.
Callers building cashier-facing responses must strip cost/profit fields
before returning them — see api.py's cashier-facing schemas.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from duka_pos import db as db_module
from duka_pos.errors import InvalidProductData, ProductNotFound
from duka_pos.money import (
    validate_money_cents,
    validate_quantity_milli,
    validate_unit,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    barcode: str | None
    unit: str
    cost_price_cents: int
    selling_price_cents: int
    active: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Product":
        return cls(
            id=row["id"],
            name=row["name"],
            barcode=row["barcode"],
            unit=row["unit"],
            cost_price_cents=row["cost_price_cents"],
            selling_price_cents=row["selling_price_cents"],
            active=bool(row["active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def create_product(
    conn: sqlite3.Connection,
    *,
    name: str,
    unit: str,
    cost_price_cents: int,
    selling_price_cents: int,
    barcode: str | None = None,
    active: bool = True,
) -> Product:
    """Create a product. Runs in its own atomic transaction."""
    if not isinstance(name, str) or not name.strip():
        raise InvalidProductData("name must be a non-empty string")
    validate_unit(unit)
    validate_money_cents(cost_price_cents, field="cost_price_cents")
    validate_money_cents(selling_price_cents, field="selling_price_cents")
    if barcode is not None and (not isinstance(barcode, str) or not barcode.strip()):
        raise InvalidProductData("barcode must be a non-empty string or None")

    now = _now_iso()
    with db_module.transaction(conn):
        try:
            cursor = conn.execute(
                """
                INSERT INTO products (
                    name, barcode, unit, cost_price_cents, selling_price_cents,
                    active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name.strip(),
                    barcode,
                    unit,
                    cost_price_cents,
                    selling_price_cents,
                    1 if active else 0,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise InvalidProductData(f"could not create product: {exc}") from exc
        product_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO stock_balances (product_id, quantity_milli) VALUES (?, 0)",
            (product_id,),
        )

    return get_product(conn, product_id)


def get_product(conn: sqlite3.Connection, product_id: int) -> Product:
    row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        raise ProductNotFound(f"product {product_id} not found")
    return Product.from_row(row)


def get_stock_balance_milli(conn: sqlite3.Connection, product_id: int) -> int:
    row = conn.execute(
        "SELECT quantity_milli FROM stock_balances WHERE product_id = ?",
        (product_id,),
    ).fetchone()
    if row is None:
        raise ProductNotFound(f"product {product_id} not found")
    return row["quantity_milli"]


def add_stock(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    quantity_milli: int,
    unit_cost_cents: int | None = None,
    reference_type: str | None = "MANUAL",
    reference_id: int | None = None,
    user_id: int | None = None,
) -> int:
    """Record a RECEIVE stock movement and update the balance projection.

    Returns the new stock balance in thousandths of the product's unit.
    Runs in its own atomic transaction: the movement insert and the
    balance update either both happen or neither does.
    """
    validate_quantity_milli(quantity_milli, field="quantity_milli")
    if unit_cost_cents is not None:
        validate_money_cents(unit_cost_cents, field="unit_cost_cents")

    # Ensure product exists before opening the write transaction.
    get_product(conn, product_id)

    now = _now_iso()
    with db_module.transaction(conn):
        conn.execute(
            """
            INSERT INTO stock_movements (
                product_id, movement_type, quantity_milli, unit_cost_cents,
                reference_type, reference_id, occurred_at, user_id
            ) VALUES (?, 'RECEIVE', ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                quantity_milli,
                unit_cost_cents,
                reference_type,
                reference_id,
                now,
                user_id,
            ),
        )
        conn.execute(
            """
            UPDATE stock_balances
            SET quantity_milli = quantity_milli + ?
            WHERE product_id = ?
            """,
            (quantity_milli, product_id),
        )

    return get_stock_balance_milli(conn, product_id)
