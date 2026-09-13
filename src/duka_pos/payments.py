"""Payment domain: local state machine and atomic confirmation.

M3.1 foundation only. No Daraja HTTP. No network calls inside SQLite
transactions.

Valid payment status transitions (subset enforced here):

    INITIATED → PENDING
    INITIATED → CANCELLED
    INITIATED → FAILED
    PENDING   → CONFIRMED   (via confirm_payment_and_complete_sale)
    PENDING   → FAILED
    PENDING   → CANCELLED
    CONFIRMED → REVERSED    (M2 void path)
    CONFIRMED → REFUNDED    (future)

Rejected examples: CONFIRMED → PENDING, FAILED → CONFIRMED,
CANCELLED → CONFIRMED (except explicit reconciliation in a later milestone).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from duka_pos import audit as audit_module
from duka_pos import db as db_module
from duka_pos import products as products_module
from duka_pos.errors import (
    InsufficientStock,
    InvalidPaymentTransition,
    PaymentConflict,
    PaymentNotFound,
    SaleNotFound,
)

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "INITIATED": frozenset({"PENDING", "CANCELLED", "FAILED"}),
    "PENDING": frozenset({"CONFIRMED", "FAILED", "CANCELLED"}),
    "CONFIRMED": frozenset({"REVERSED", "REFUNDED"}),
    "FAILED": frozenset(),
    "CANCELLED": frozenset(),
    "REVERSED": frozenset(),
    "REFUNDED": frozenset(),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Payment:
    id: int
    sale_id: int
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
    updated_at: str | None = None
    last_error: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Payment":
        keys = row.keys()
        return cls(
            id=row["id"],
            sale_id=row["sale_id"],
            method=row["method"],
            status=row["status"],
            amount_cents=row["amount_cents"],
            created_at=row["created_at"],
            provider=row["provider"] if "provider" in keys else None,
            provider_checkout_request_id=(
                row["provider_checkout_request_id"]
                if "provider_checkout_request_id" in keys
                else None
            ),
            provider_merchant_request_id=(
                row["provider_merchant_request_id"]
                if "provider_merchant_request_id" in keys
                else None
            ),
            provider_receipt_number=(
                row["provider_receipt_number"]
                if "provider_receipt_number" in keys
                else None
            ),
            phone_number=row["phone_number"] if "phone_number" in keys else None,
            client_payment_reference=(
                row["client_payment_reference"]
                if "client_payment_reference" in keys
                else None
            ),
            updated_at=row["updated_at"] if "updated_at" in keys else None,
            last_error=row["last_error"] if "last_error" in keys else None,
        )


def get_payment(conn: sqlite3.Connection, payment_id: int) -> Payment:
    row = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    if row is None:
        raise PaymentNotFound(f"payment {payment_id} not found")
    return Payment.from_row(row)


def get_payment_for_sale(conn: sqlite3.Connection, sale_id: int) -> Payment | None:
    row = conn.execute(
        "SELECT * FROM payments WHERE sale_id = ? ORDER BY id DESC LIMIT 1",
        (sale_id,),
    ).fetchone()
    return Payment.from_row(row) if row is not None else None


def _assert_transition(current: str, target: str) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidPaymentTransition(
            f"cannot transition payment from {current!r} to {target!r}"
        )


def transition_payment(
    conn: sqlite3.Connection,
    *,
    payment_id: int,
    new_status: str,
    last_error: str | None = None,
    user_id: int | None = None,
) -> Payment:
    """Apply a validated non-confirmation status transition in its own transaction.

    Confirmation of PENDING → CONFIRMED must go through
    ``confirm_payment_and_complete_sale`` so stock/receipt/sale stay atomic.
    """
    if new_status == "CONFIRMED":
        raise InvalidPaymentTransition(
            "use confirm_payment_and_complete_sale to confirm a payment"
        )

    payment = get_payment(conn, payment_id)
    _assert_transition(payment.status, new_status)
    now = _now_iso()
    with db_module.transaction(conn):
        conn.execute(
            """
            UPDATE payments
            SET status = ?, updated_at = ?, last_error = ?
            WHERE id = ? AND status = ?
            """,
            (new_status, now, last_error, payment_id, payment.status),
        )
        audit_module.record(
            conn,
            action="payment.transition",
            user_id=user_id,
            entity_type="payment",
            entity_id=payment_id,
            details={
                "from": payment.status,
                "to": new_status,
                "sale_id": payment.sale_id,
                "last_error": last_error,
            },
        )
    return get_payment(conn, payment_id)


def mark_pending(
    conn: sqlite3.Connection,
    *,
    payment_id: int,
    provider: str | None = None,
    provider_checkout_request_id: str | None = None,
    provider_merchant_request_id: str | None = None,
    user_id: int | None = None,
) -> Payment:
    """INITIATED → PENDING, optionally attaching provider request ids (M3.2)."""
    payment = get_payment(conn, payment_id)
    _assert_transition(payment.status, "PENDING")
    now = _now_iso()
    with db_module.transaction(conn):
        conn.execute(
            """
            UPDATE payments
            SET status = 'PENDING',
                updated_at = ?,
                provider = COALESCE(?, provider),
                provider_checkout_request_id = COALESCE(?, provider_checkout_request_id),
                provider_merchant_request_id = COALESCE(?, provider_merchant_request_id)
            WHERE id = ? AND status = ?
            """,
            (
                now,
                provider,
                provider_checkout_request_id,
                provider_merchant_request_id,
                payment_id,
                payment.status,
            ),
        )
        audit_module.record(
            conn,
            action="payment.pending",
            user_id=user_id,
            entity_type="payment",
            entity_id=payment_id,
            details={"sale_id": payment.sale_id, "provider": provider},
        )
    return get_payment(conn, payment_id)


def fail_payment(
    conn: sqlite3.Connection,
    *,
    payment_id: int,
    last_error: str | None = None,
    user_id: int | None = None,
) -> Payment:
    return transition_payment(
        conn, payment_id=payment_id, new_status="FAILED", last_error=last_error, user_id=user_id
    )


def cancel_payment(
    conn: sqlite3.Connection,
    *,
    payment_id: int,
    last_error: str | None = None,
    user_id: int | None = None,
) -> Payment:
    return transition_payment(
        conn,
        payment_id=payment_id,
        new_status="CANCELLED",
        last_error=last_error,
        user_id=user_id,
    )


def confirm_payment_and_complete_sale(
    conn: sqlite3.Connection,
    *,
    payment_id: int,
    expected_amount_cents: int,
    provider_receipt_number: str | None = None,
    provider_checkout_request_id: str | None = None,
    provider_merchant_request_id: str | None = None,
    user_id: int | None = None,
) -> Payment:
    """Atomically confirm a PENDING payment and complete its sale.

    ``expected_amount_cents`` is **mandatory**. It must equal the locally
    recorded ``payment.amount_cents`` (provider-confirmed amount vs local).
    A call with only ``payment_id`` is not valid and will not confirm.

    Inside one SQLite transaction:
      - verify payment is PENDING (or already CONFIRMED with matching refs → idempotent)
      - verify sale is PENDING_PAYMENT
      - verify amount (mandatory equality)
      - payment → CONFIRMED
      - sale → COMPLETED
      - stock SALE movements + balance updates
      - receipt
      - audit

    On amount mismatch or any failure: full rollback — payment stays PENDING,
    sale stays PENDING_PAYMENT, stock unchanged, no receipt.

    No network calls. Not a cashier-facing operation; intended for trusted
    provider/reconciliation handlers only (M3.2+).
    """
    if not isinstance(expected_amount_cents, int) or isinstance(expected_amount_cents, bool):
        raise PaymentConflict(
            "expected_amount_cents is required and must be an integer (provider-confirmed amount)"
        )

    payment = get_payment(conn, payment_id)

    if payment.status == "CONFIRMED":
        if expected_amount_cents != payment.amount_cents:
            audit_module.record(
                conn,
                action="payment.confirm_conflict",
                user_id=user_id,
                entity_type="payment",
                entity_id=payment_id,
                details={
                    "reason": "amount_mismatch_on_already_confirmed",
                    "stored_amount": payment.amount_cents,
                    "provided_amount": expected_amount_cents,
                },
            )
            raise PaymentConflict(
                f"payment {payment_id} already CONFIRMED with amount "
                f"{payment.amount_cents}; cannot accept {expected_amount_cents}"
            )
        if (
            provider_receipt_number is not None
            and payment.provider_receipt_number is not None
            and provider_receipt_number != payment.provider_receipt_number
        ):
            audit_module.record(
                conn,
                action="payment.confirm_conflict",
                user_id=user_id,
                entity_type="payment",
                entity_id=payment_id,
                details={
                    "reason": "receipt_mismatch_on_already_confirmed",
                    "stored": payment.provider_receipt_number,
                    "provided": provider_receipt_number,
                },
            )
            raise PaymentConflict(
                f"payment {payment_id} already CONFIRMED with different provider receipt"
            )
        if (
            provider_checkout_request_id is not None
            and payment.provider_checkout_request_id is not None
            and provider_checkout_request_id != payment.provider_checkout_request_id
        ):
            audit_module.record(
                conn,
                action="payment.confirm_conflict",
                user_id=user_id,
                entity_type="payment",
                entity_id=payment_id,
                details={
                    "reason": "checkout_id_mismatch_on_already_confirmed",
                    "stored": payment.provider_checkout_request_id,
                    "provided": provider_checkout_request_id,
                },
            )
            raise PaymentConflict(
                f"payment {payment_id} already CONFIRMED with different checkout request id"
            )
        if (
            provider_merchant_request_id is not None
            and payment.provider_merchant_request_id is not None
            and provider_merchant_request_id != payment.provider_merchant_request_id
        ):
            audit_module.record(
                conn,
                action="payment.confirm_conflict",
                user_id=user_id,
                entity_type="payment",
                entity_id=payment_id,
                details={
                    "reason": "merchant_id_mismatch_on_already_confirmed",
                    "stored": payment.provider_merchant_request_id,
                    "provided": provider_merchant_request_id,
                },
            )
            raise PaymentConflict(
                f"payment {payment_id} already CONFIRMED with different merchant request id"
            )
        return payment

    if payment.status not in ("PENDING", "INITIATED"):
        raise InvalidPaymentTransition(
            f"cannot confirm payment in status {payment.status!r}"
        )

    if expected_amount_cents != payment.amount_cents:
        # Do not mutate state; leave PENDING / PENDING_PAYMENT.
        audit_module.record(
            conn,
            action="payment.confirm_conflict",
            user_id=user_id,
            entity_type="payment",
            entity_id=payment_id,
            details={
                "reason": "amount_mismatch",
                "stored_amount": payment.amount_cents,
                "provided_amount": expected_amount_cents,
            },
        )
        raise PaymentConflict(
            f"amount mismatch: payment has {payment.amount_cents} cents, "
            f"confirmation has {expected_amount_cents}"
        )

    sale_row = conn.execute(
        "SELECT * FROM sales WHERE id = ?", (payment.sale_id,)
    ).fetchone()
    if sale_row is None:
        raise SaleNotFound(f"sale {payment.sale_id} not found")
    if sale_row["status"] != "PENDING_PAYMENT":
        raise PaymentConflict(
            f"sale {payment.sale_id} status is {sale_row['status']!r}, "
            "expected PENDING_PAYMENT"
        )

    lines = conn.execute(
        "SELECT * FROM sale_lines WHERE sale_id = ? ORDER BY id",
        (payment.sale_id,),
    ).fetchall()
    if not lines:
        raise PaymentConflict(f"sale {payment.sale_id} has no lines")

    now = _now_iso()

    with db_module.transaction(conn):
        row = conn.execute(
            "SELECT * FROM payments WHERE id = ?", (payment_id,)
        ).fetchone()
        if row is None:
            raise PaymentNotFound(f"payment {payment_id} not found")
        if row["status"] == "CONFIRMED":
            return Payment.from_row(row)
        if row["status"] not in ("PENDING", "INITIATED"):
            raise InvalidPaymentTransition(
                f"cannot confirm payment in status {row['status']!r}"
            )

        # Provider-reference uniqueness: same checkout/merchant/receipt must not
        # confirm a different payment (one payment per sale; no double-apply).
        for field, value in (
            ("provider_checkout_request_id", provider_checkout_request_id),
            ("provider_merchant_request_id", provider_merchant_request_id),
            ("provider_receipt_number", provider_receipt_number),
        ):
            if value is None:
                continue
            conflict = conn.execute(
                f"SELECT id, sale_id FROM payments WHERE {field} = ? AND id != ?",
                (value, payment_id),
            ).fetchone()
            if conflict is not None:
                raise PaymentConflict(
                    f"{field} {value!r} already used by payment {conflict['id']}"
                )

        for line in lines:
            product_id = line["product_id"]
            qty = line["quantity_milli"]
            balance = products_module.get_stock_balance_milli(conn, product_id)
            if qty > balance:
                product = products_module.get_product(conn, product_id)
                raise InsufficientStock(
                    f"product {product_id} ({product.name}) has {balance} milli-units "
                    f"in stock; confirmation requires {qty}"
                )
            conn.execute(
                """
                UPDATE stock_balances
                SET quantity_milli = quantity_milli - ?
                WHERE product_id = ?
                """,
                (qty, product_id),
            )
            conn.execute(
                """
                INSERT INTO stock_movements (
                    product_id, movement_type, quantity_milli, unit_cost_cents,
                    reference_type, reference_id, occurred_at, user_id
                ) VALUES (?, 'SALE', ?, ?, 'SALE', ?, ?, ?)
                """,
                (
                    product_id,
                    -qty,
                    line["unit_cost_cents"],
                    payment.sale_id,
                    now,
                    user_id,
                ),
            )

        conn.execute(
            """
            UPDATE payments
            SET status = 'CONFIRMED',
                updated_at = ?,
                provider_receipt_number = COALESCE(?, provider_receipt_number),
                provider_checkout_request_id = COALESCE(?, provider_checkout_request_id),
                provider_merchant_request_id = COALESCE(?, provider_merchant_request_id),
                last_error = NULL
            WHERE id = ?
            """,
            (
                now,
                provider_receipt_number,
                provider_checkout_request_id,
                provider_merchant_request_id,
                payment_id,
            ),
        )

        conn.execute(
            "UPDATE sales SET status = 'COMPLETED' WHERE id = ?",
            (payment.sale_id,),
        )

        receipt_number = f"RCPT-{payment.sale_id:08d}"
        existing_receipt = conn.execute(
            "SELECT id FROM receipts WHERE sale_id = ?", (payment.sale_id,)
        ).fetchone()
        if existing_receipt is None:
            conn.execute(
                """
                INSERT INTO receipts (sale_id, receipt_number, created_at)
                VALUES (?, ?, ?)
                """,
                (payment.sale_id, receipt_number, now),
            )

        audit_module.record(
            conn,
            action="payment.confirmed",
            user_id=user_id,
            entity_type="payment",
            entity_id=payment_id,
            details={
                "sale_id": payment.sale_id,
                "amount_cents": payment.amount_cents,
                "provider_receipt_number": provider_receipt_number,
            },
        )

    return get_payment(conn, payment_id)
