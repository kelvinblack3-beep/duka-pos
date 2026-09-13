"""M-Pesa flow orchestration (M3.2). HTTP never inside SQLite transactions."""

from __future__ import annotations

import sqlite3
from typing import Any

from duka_pos import audit as audit_module
from duka_pos import db as db_module
from duka_pos import payments as payments_module
from duka_pos.errors import InvalidSaleData, PaymentConflict, PaymentNotFound
from duka_pos.phone import normalize_ke_msisdn
from duka_pos.providers.mpesa_daraja import DarajaHttpError, MpesaDarajaProvider, parse_stk_callback


def attach_provider_refs(conn, *, payment_id, merchant_request_id, checkout_request_id, user_id=None):
    payment = payments_module.get_payment(conn, payment_id)
    if payment.status not in ("PENDING", "INITIATED"):
        raise PaymentConflict(f"cannot attach provider refs to payment in status {payment.status!r}")
    with db_module.transaction(conn):
        for field, value in (
            ("provider_checkout_request_id", checkout_request_id),
            ("provider_merchant_request_id", merchant_request_id),
        ):
            conflict = conn.execute(
                f"SELECT id FROM payments WHERE {field} = ? AND id != ?", (value, payment_id)
            ).fetchone()
            if conflict is not None:
                raise PaymentConflict(f"{field} {value!r} already used by payment {conflict['id']}")
        conn.execute(
            """UPDATE payments SET provider_checkout_request_id = ?,
                provider_merchant_request_id = ?, provider = COALESCE(provider, 'DARAJA'),
                updated_at = datetime('now') WHERE id = ?""",
            (checkout_request_id, merchant_request_id, payment_id),
        )
        audit_module.record(
            conn, action="payment.stk_initiated", user_id=user_id, entity_type="payment",
            entity_id=payment_id,
            details={"checkout_request_id": checkout_request_id, "merchant_request_id": merchant_request_id, "sale_id": payment.sale_id},
        )
    return payments_module.get_payment(conn, payment_id)


def mark_stk_initiation_failed(conn, *, payment_id, error_message, user_id=None):
    payment = payments_module.get_payment(conn, payment_id)
    safe_msg = (error_message or "stk_initiation_failed")[:500]
    for secret_word in ("passkey", "secret", "token", "Bearer"):
        if secret_word.lower() in safe_msg.lower():
            safe_msg = "stk_initiation_failed"
            break
    with db_module.transaction(conn):
        conn.execute(
            "UPDATE payments SET last_error = ?, updated_at = datetime('now') WHERE id = ?",
            (safe_msg, payment_id),
        )
        audit_module.record(
            conn, action="payment.stk_initiation_failed", user_id=user_id,
            entity_type="payment", entity_id=payment_id,
            details={"sale_id": payment.sale_id, "error": safe_msg},
        )
    return payments_module.get_payment(conn, payment_id)


def initiate_stk_for_payment(conn, *, payment_id, provider: MpesaDarajaProvider, user_id=None):
    payment = payments_module.get_payment(conn, payment_id)
    if payment.method != "MPESA":
        raise PaymentConflict("STK initiation only applies to MPESA payments")
    if payment.status not in ("PENDING", "INITIATED"):
        raise PaymentConflict(f"cannot initiate STK for payment in status {payment.status!r}")
    if not payment.phone_number:
        raise InvalidSaleData("phone_number is required for MPESA STK")
    phone_254 = normalize_ke_msisdn(payment.phone_number)
    try:
        accepted = provider.initiate_stk_push(
            amount_cents=payment.amount_cents, phone_254=phone_254,
            account_reference=f"S{payment.sale_id}", transaction_desc="Duka POS",
        )
    except DarajaHttpError as exc:
        mark_stk_initiation_failed(conn, payment_id=payment_id, error_message=str(exc), user_id=user_id)
        raise
    return attach_provider_refs(
        conn, payment_id=payment_id, merchant_request_id=accepted.merchant_request_id,
        checkout_request_id=accepted.checkout_request_id, user_id=user_id,
    )


def find_payment_by_checkout(conn, checkout_request_id: str):
    row = conn.execute(
        "SELECT * FROM payments WHERE provider_checkout_request_id = ?", (checkout_request_id,)
    ).fetchone()
    return payments_module.Payment.from_row(row) if row else None


def process_stk_callback(conn, payload: dict[str, Any], *, user_id=None) -> dict[str, Any]:
    try:
        parsed = parse_stk_callback(payload)
    except ValueError as exc:
        audit_module.record(conn, action="payment.callback_malformed", user_id=user_id, entity_type="payment", details={"error": str(exc)})
        conn.commit()
        return {"ok": False, "reason": "malformed", "detail": str(exc)}

    checkout = parsed["checkout_request_id"]
    payment = find_payment_by_checkout(conn, checkout)
    if payment is None:
        audit_module.record(conn, action="payment.callback_unknown", user_id=user_id, entity_type="payment", details={"checkout_request_id": checkout})
        conn.commit()
        return {"ok": False, "reason": "unknown_checkout", "checkout_request_id": checkout}

    audit_module.record(
        conn, action="payment.callback_received", user_id=user_id, entity_type="payment",
        entity_id=payment.id,
        details={"checkout_request_id": checkout, "result_code": parsed["result_code"], "sale_id": payment.sale_id},
    )
    conn.commit()

    if payment.status == "CONFIRMED":
        audit_module.record(conn, action="payment.callback_duplicate", user_id=user_id, entity_type="payment", entity_id=payment.id, details={"checkout_request_id": checkout})
        conn.commit()
        return {"ok": True, "reason": "already_confirmed", "payment_id": payment.id, "sale_id": payment.sale_id}

    if payment.status in ("FAILED", "CANCELLED", "REVERSED", "REFUNDED"):
        return {"ok": True, "reason": "already_terminal", "payment_id": payment.id, "status": payment.status}

    if parsed["result_code"] != 0:
        target = "CANCELLED" if parsed["result_code"] == 1032 else "FAILED"
        try:
            payments_module.transition_payment(
                conn, payment_id=payment.id, new_status=target,
                last_error=(parsed["result_desc"][:500] if parsed["result_desc"] else None), user_id=user_id,
            )
        except Exception:
            pass
        return {"ok": True, "reason": "provider_failure", "result_code": parsed["result_code"], "payment_id": payment.id, "status": target}

    amount_kes = parsed.get("amount_kes")
    if amount_kes is None:
        audit_module.record(conn, action="payment.callback_rejected", user_id=user_id, entity_type="payment", entity_id=payment.id, details={"reason": "missing_amount"})
        conn.commit()
        return {"ok": False, "reason": "missing_amount", "payment_id": payment.id}

    expected_cents = int(amount_kes) * 100
    try:
        confirmed = payments_module.confirm_payment_and_complete_sale(
            conn, payment_id=payment.id, expected_amount_cents=expected_cents,
            provider_receipt_number=parsed.get("mpesa_receipt_number"),
            provider_checkout_request_id=checkout,
            provider_merchant_request_id=parsed.get("merchant_request_id"), user_id=user_id,
        )
    except (PaymentConflict, PaymentNotFound) as exc:
        audit_module.record(conn, action="payment.callback_rejected", user_id=user_id, entity_type="payment", entity_id=payment.id, details={"reason": str(exc)})
        conn.commit()
        return {"ok": False, "reason": "confirm_conflict", "detail": str(exc)}

    return {"ok": True, "reason": "confirmed", "payment_id": confirmed.id, "sale_id": confirmed.sale_id, "status": confirmed.status}
