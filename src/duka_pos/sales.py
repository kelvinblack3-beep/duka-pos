"""Sale, payment, and receipt domain logic.

Cash path (M1 semantics, preserved):
  create sale → payment CONFIRMED → stock deduction → receipt → COMPLETED
  in one SQLite transaction.

MPESA path (M3.1 local foundation only):
  create sale PENDING_PAYMENT + payment PENDING + lines
  NO stock deduction, NO receipt, provider=DARAJA identity.
  Confirmation is a separate domain operation (confirm_payment_and_complete_sale).

Idempotency: `client_reference` is a UNIQUE column on `sales`. Submitting
the same client_reference twice returns the original sale instead of
creating a second one, deducting stock twice, or recording a second
payment.

No network calls happen anywhere in this module.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from duka_pos import db as db_module
from duka_pos import products as products_module
from duka_pos.errors import (
    EmptySale,
    InsufficientStock,
    InvalidSaleData,
    ReceiptNotFound,
    SaleNotFound,
    UnsupportedPaymentMethod,
)
from duka_pos.money import line_total_cents, validate_quantity_milli
from duka_pos.providers.cash import cash_provider
from duka_pos.providers.mpesa_daraja import mpesa_daraja_provider

#: CASH → immediate confirm. MPESA → pending local record only (no Daraja).
SUPPORTED_PAYMENT_METHODS = frozenset({"CASH", "MPESA"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SaleLineResult:
    product_id: int
    product_name: str
    quantity_milli: int
    unit_price_cents: int
    unit_cost_cents: int
    line_total_cents: int


@dataclass(frozen=True)
class PaymentResult:
    id: int
    method: str
    status: str
    amount_cents: int
    created_at: str
    provider: str | None = None
    provider_checkout_request_id: str | None = None
    provider_merchant_request_id: str | None = None
    provider_receipt_number: str | None = None
    phone_number: str | None = None
    client_payment_reference: str | None = None


@dataclass(frozen=True)
class Sale:
    id: int
    client_reference: str
    status: str
    subtotal_cents: int
    total_cents: int
    created_at: str
    lines: list[SaleLineResult] = field(default_factory=list)
    payment: PaymentResult | None = None

    @property
    def gross_profit_cents(self) -> int:
        """Owner/manager-only figure. Never expose via cashier-facing API."""
        return sum(
            (line.unit_price_cents - line.unit_cost_cents) * line.quantity_milli // 1000
            for line in self.lines
        )


@dataclass(frozen=True)
class ReceiptLine:
    product_name: str
    quantity_milli: int
    unit_price_cents: int
    line_total_cents: int


@dataclass(frozen=True)
class Receipt:
    sale_id: int
    receipt_number: str
    created_at: str
    lines: list[ReceiptLine]
    subtotal_cents: int
    total_cents: int
    payment_method: str
    payment_status: str


def _find_sale_id_by_reference(conn: sqlite3.Connection, client_reference: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM sales WHERE client_reference = ?", (client_reference,)
    ).fetchone()
    return row["id"] if row is not None else None


def create_sale(
    conn: sqlite3.Connection,
    *,
    client_reference: str,
    lines: list[dict],
    payment_method: str = "CASH",
    phone_number: str | None = None,
    client_payment_reference: str | None = None,
    user_id: int | None = None,
    shift_id: int | None = None,
) -> Sale:
    """Create a sale atomically, or return the existing sale if the same
    client_reference was already submitted (idempotency).

    CASH: COMPLETED + CONFIRMED + stock + receipt (M1 behaviour).
    MPESA: PENDING_PAYMENT + PENDING payment, provider=DARAJA identity,
    no stock deduction, no stock reservation, no receipt.

    Pending stock semantics (intentional, ADR-003):
    - Pending M-Pesa does NOT deduct stock and does NOT reserve stock.
    - A pending sale may request more than current stock; confirmation
      may later fail with InsufficientStock. That is preferred to
      false reservations for abandoned STK attempts.
    """
    if not isinstance(client_reference, str) or not client_reference.strip():
        raise InvalidSaleData("client_reference must be a non-empty string")
    if payment_method not in SUPPORTED_PAYMENT_METHODS:
        raise UnsupportedPaymentMethod(
            f"payment method {payment_method!r} is not supported; "
            f"supported methods: {sorted(SUPPORTED_PAYMENT_METHODS)}"
        )
    if not lines:
        raise EmptySale("a sale must contain at least one line")

    existing_id = _find_sale_id_by_reference(conn, client_reference)
    if existing_id is not None:
        return get_sale(conn, existing_id)

    parsed_lines: list[tuple[int, int]] = []
    for i, raw_line in enumerate(lines):
        try:
            product_id = raw_line["product_id"]
            quantity_milli = raw_line["quantity_milli"]
        except (KeyError, TypeError) as exc:
            raise InvalidSaleData(
                f"lines[{i}] must be a mapping with product_id and quantity_milli"
            ) from exc
        validate_quantity_milli(quantity_milli, field=f"lines[{i}].quantity_milli")
        parsed_lines.append((product_id, quantity_milli))

    immediate = payment_method == "CASH"
    sale_status = "COMPLETED" if immediate else "PENDING_PAYMENT"
    payment_status = "CONFIRMED" if immediate else "PENDING"
    if immediate:
        provider = cash_provider.provider_name  # LOCAL_CASH
    else:
        # Explicit future-Daraja path identity; no network in M3.1.
        provider = mpesa_daraja_provider.provider_name  # DARAJA

    now = _now_iso()

    try:
        with db_module.transaction(conn):
            line_results: list[tuple] = []
            subtotal_cents = 0

            for product_id, quantity_milli in parsed_lines:
                product = products_module.get_product(conn, product_id)
                if immediate:
                    balance = products_module.get_stock_balance_milli(conn, product_id)
                    if quantity_milli > balance:
                        raise InsufficientStock(
                            f"product {product_id} ({product.name}) has {balance} milli-units "
                            f"in stock; sale requests {quantity_milli}"
                        )

                total_for_line = line_total_cents(product.selling_price_cents, quantity_milli)
                subtotal_cents += total_for_line
                line_results.append(
                    (product, quantity_milli, product.selling_price_cents, total_for_line)
                )

                if immediate:
                    conn.execute(
                        """
                        UPDATE stock_balances
                        SET quantity_milli = quantity_milli - ?
                        WHERE product_id = ?
                        """,
                        (quantity_milli, product_id),
                    )

            total_cents = subtotal_cents

            try:
                cursor = conn.execute(
                    """
                    INSERT INTO sales (
                        client_reference, status, subtotal_cents, total_cents, created_at,
                        user_id, shift_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        client_reference,
                        sale_status,
                        subtotal_cents,
                        total_cents,
                        now,
                        user_id,
                        shift_id,
                    ),
                )
            except sqlite3.IntegrityError:
                raise _DuplicateSaleReference() from None

            sale_id = cursor.lastrowid

            for product, quantity_milli, unit_price_cents, line_total in line_results:
                conn.execute(
                    """
                    INSERT INTO sale_lines (
                        sale_id, product_id, quantity_milli, unit_price_cents,
                        unit_cost_cents, line_total_cents
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sale_id,
                        product.id,
                        quantity_milli,
                        unit_price_cents,
                        product.cost_price_cents,
                        line_total,
                    ),
                )
                if immediate:
                    conn.execute(
                        """
                        INSERT INTO stock_movements (
                            product_id, movement_type, quantity_milli, unit_cost_cents,
                            reference_type, reference_id, occurred_at, user_id
                        ) VALUES (?, 'SALE', ?, ?, 'SALE', ?, ?, ?)
                        """,
                        (
                            product.id,
                            -quantity_milli,
                            product.cost_price_cents,
                            sale_id,
                            now,
                            user_id,
                        ),
                    )

            conn.execute(
                """
                INSERT INTO payments (
                    sale_id, method, status, amount_cents, created_at,
                    provider, phone_number, client_payment_reference, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sale_id,
                    payment_method,
                    payment_status,
                    total_cents,
                    now,
                    provider,
                    phone_number,
                    client_payment_reference,
                    now,
                ),
            )

            if immediate:
                receipt_number = f"RCPT-{sale_id:08d}"
                conn.execute(
                    """
                    INSERT INTO receipts (sale_id, receipt_number, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (sale_id, receipt_number, now),
                )
    except _DuplicateSaleReference:
        existing_id = _find_sale_id_by_reference(conn, client_reference)
        if existing_id is None:
            raise
        return get_sale(conn, existing_id)

    return get_sale(conn, sale_id)


class _DuplicateSaleReference(Exception):
    """Internal control-flow signal only; never raised to callers."""


def get_sale(conn: sqlite3.Connection, sale_id: int) -> Sale:
    sale_row = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if sale_row is None:
        raise SaleNotFound(f"sale {sale_id} not found")

    line_rows = conn.execute(
        """
        SELECT sl.*, p.name AS product_name
        FROM sale_lines sl
        JOIN products p ON p.id = sl.product_id
        WHERE sl.sale_id = ?
        ORDER BY sl.id
        """,
        (sale_id,),
    ).fetchall()
    lines = [
        SaleLineResult(
            product_id=row["product_id"],
            product_name=row["product_name"],
            quantity_milli=row["quantity_milli"],
            unit_price_cents=row["unit_price_cents"],
            unit_cost_cents=row["unit_cost_cents"],
            line_total_cents=row["line_total_cents"],
        )
        for row in line_rows
    ]

    payment_row = conn.execute(
        "SELECT * FROM payments WHERE sale_id = ? ORDER BY id DESC LIMIT 1",
        (sale_id,),
    ).fetchone()
    payment = None
    if payment_row is not None:
        keys = payment_row.keys()
        payment = PaymentResult(
            id=payment_row["id"],
            method=payment_row["method"],
            status=payment_row["status"],
            amount_cents=payment_row["amount_cents"],
            created_at=payment_row["created_at"],
            provider=payment_row["provider"] if "provider" in keys else None,
            provider_checkout_request_id=(
                payment_row["provider_checkout_request_id"]
                if "provider_checkout_request_id" in keys
                else None
            ),
            provider_merchant_request_id=(
                payment_row["provider_merchant_request_id"]
                if "provider_merchant_request_id" in keys
                else None
            ),
            provider_receipt_number=(
                payment_row["provider_receipt_number"]
                if "provider_receipt_number" in keys
                else None
            ),
            phone_number=payment_row["phone_number"] if "phone_number" in keys else None,
            client_payment_reference=(
                payment_row["client_payment_reference"]
                if "client_payment_reference" in keys
                else None
            ),
        )

    return Sale(
        id=sale_row["id"],
        client_reference=sale_row["client_reference"],
        status=sale_row["status"],
        subtotal_cents=sale_row["subtotal_cents"],
        total_cents=sale_row["total_cents"],
        created_at=sale_row["created_at"],
        lines=lines,
        payment=payment,
    )


def get_receipt(conn: sqlite3.Connection, sale_id: int) -> Receipt:
    """Retrieve the cashier-facing receipt for a sale.

    Deliberately omits unit_cost_cents and gross profit: receipts are
    customer-facing, and cost/profit must not leak through them.
    """
    receipt_row = conn.execute(
        "SELECT * FROM receipts WHERE sale_id = ?", (sale_id,)
    ).fetchone()
    if receipt_row is None:
        raise ReceiptNotFound(f"receipt for sale {sale_id} not found")

    sale = get_sale(conn, sale_id)
    lines = [
        ReceiptLine(
            product_name=line.product_name,
            quantity_milli=line.quantity_milli,
            unit_price_cents=line.unit_price_cents,
            line_total_cents=line.line_total_cents,
        )
        for line in sale.lines
    ]
    payment = sale.payment
    return Receipt(
        sale_id=sale.id,
        receipt_number=receipt_row["receipt_number"],
        created_at=receipt_row["created_at"],
        lines=lines,
        subtotal_cents=sale.subtotal_cents,
        total_cents=sale.total_cents,
        payment_method=payment.method if payment else "UNKNOWN",
        payment_status=payment.status if payment else "UNKNOWN",
    )
