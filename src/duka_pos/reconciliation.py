"""M3.3 payment reconciliation via Daraja STK Push Query.

Recovers PENDING M-Pesa payments when the STK callback is delayed, lost,
or never delivered. Network calls happen outside SQLite transactions.
Confirmation always goes through payments.confirm_payment_and_complete_sale.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from duka_pos import audit as audit_module
from duka_pos import payments as payments_module
from duka_pos.errors import InvalidSaleData, PaymentConflict, PaymentNotFound
from duka_pos.phone import normalize_ke_msisdn
from duka_pos.providers.mpesa_daraja import (
    DarajaHttpError,
    MpesaDarajaProvider,
    StkQueryResult,
)

# Minimum age before automatic/batch reconciliation (customer still on PIN prompt).
DEFAULT_MIN_AGE_SECONDS = 90

# Terminal STK ResultCodes (aligned with M3.2 callback handling).
# 0 = success; 1032 = user cancelled. Other known failure codes are terminal.
_TERMINAL_CANCEL_CODES = frozenset({1032})
# Common terminal failure codes from Daraja STK (not "still processing").
_TERMINAL_FAIL_CODES = frozenset({
    1,  # insufficient funds / generic failure
    1037,  # timeout / no response from user
    2001,  # wrong PIN
    1019,  # transaction expired
    1001,  # unable to lock subscriber — treated as terminal for *this* checkout
})


def _sanitize_error(msg: str | None) -> str:
    safe = (msg or "reconcile_error")[:500]
    for secret_word in ("passkey", "secret", "token", "Bearer", "Password", "Authorization"):
        if secret_word.lower() in safe.lower():
            return "reconcile_error"
    return safe


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        cleaned = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def is_eligible_for_reconcile(
    payment: payments_module.Payment,
    *,
    min_age_seconds: int = DEFAULT_MIN_AGE_SECONDS,
    now: datetime | None = None,
    require_min_age: bool = False,
) -> tuple[bool, str]:
    """Return (eligible, reason). Manual reconcile may set require_min_age=False."""
    if payment.method != "MPESA":
        return False, "not_mpesa"
    if payment.status not in ("PENDING", "INITIATED"):
        return False, f"status_{payment.status.lower()}"
    if not payment.provider_checkout_request_id:
        return False, "missing_checkout_request_id"
    if require_min_age:
        ref = _parse_iso(payment.updated_at) or _parse_iso(payment.created_at)
        if ref is not None:
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            current = now or datetime.now(timezone.utc)
            age = (current - ref).total_seconds()
            if age < min_age_seconds:
                return False, "too_young"
    return True, "eligible"


def reconcile_payment(
    conn: sqlite3.Connection,
    *,
    payment_id: int,
    provider: MpesaDarajaProvider,
    user_id: int | None = None,
    require_min_age: bool = False,
    min_age_seconds: int = DEFAULT_MIN_AGE_SECONDS,
) -> dict[str, Any]:
    """Reconcile one MPESA payment via STK Push Query.

    HTTP runs outside any SQLite transaction. Confirmation uses the existing
    atomic confirm_payment_and_complete_sale path.
    """
    payment = payments_module.get_payment(conn, payment_id)

    if payment.status == "CONFIRMED":
        audit_module.record(
            conn,
            action="payment.reconcile_already_confirmed",
            user_id=user_id,
            entity_type="payment",
            entity_id=payment.id,
            details={"sale_id": payment.sale_id},
        )
        conn.commit()
        return {
            "ok": True,
            "reason": "already_confirmed",
            "payment_id": payment.id,
            "sale_id": payment.sale_id,
            "status": payment.status,
        }

    if payment.status in ("FAILED", "CANCELLED", "REVERSED", "REFUNDED"):
        return {
            "ok": True,
            "reason": "already_terminal",
            "payment_id": payment.id,
            "status": payment.status,
        }

    eligible, why = is_eligible_for_reconcile(
        payment,
        min_age_seconds=min_age_seconds,
        require_min_age=require_min_age,
    )
    if not eligible:
        audit_module.record(
            conn,
            action="payment.reconcile_skipped",
            user_id=user_id,
            entity_type="payment",
            entity_id=payment.id,
            details={"reason": why, "sale_id": payment.sale_id},
        )
        conn.commit()
        return {"ok": False, "reason": why, "payment_id": payment.id}

    checkout = payment.provider_checkout_request_id
    assert checkout is not None

    audit_module.record(
        conn,
        action="payment.reconcile_attempted",
        user_id=user_id,
        entity_type="payment",
        entity_id=payment.id,
        details={"checkout_request_id": checkout, "sale_id": payment.sale_id},
    )
    conn.commit()

    try:
        query = provider.query_stk_status(checkout)
    except DarajaHttpError as exc:
        safe = _sanitize_error(str(exc))
        audit_module.record(
            conn,
            action="payment.reconcile_provider_error",
            user_id=user_id,
            entity_type="payment",
            entity_id=payment.id,
            details={"error": safe, "sale_id": payment.sale_id},
        )
        conn.execute(
            "UPDATE payments SET last_error = ?, updated_at = datetime('now') WHERE id = ?",
            (safe, payment.id),
        )
        conn.commit()
        return {
            "ok": False,
            "reason": "provider_error",
            "detail": safe,
            "payment_id": payment.id,
        }
    except ValueError as exc:
        safe = _sanitize_error(str(exc))
        audit_module.record(
            conn,
            action="payment.reconcile_malformed",
            user_id=user_id,
            entity_type="payment",
            entity_id=payment.id,
            details={"error": safe, "sale_id": payment.sale_id},
        )
        conn.commit()
        return {
            "ok": False,
            "reason": "malformed",
            "detail": safe,
            "payment_id": payment.id,
        }

    return _apply_query_result(
        conn, payment=payment, query=query, user_id=user_id
    )


def _apply_query_result(
    conn: sqlite3.Connection,
    *,
    payment: payments_module.Payment,
    query: StkQueryResult,
    user_id: int | None,
) -> dict[str, Any]:
    """Validate correlation and apply terminal or success outcome."""
    stored_checkout = payment.provider_checkout_request_id
    if (
        query.checkout_request_id is not None
        and stored_checkout is not None
        and str(query.checkout_request_id) != str(stored_checkout)
    ):
        audit_module.record(
            conn,
            action="payment.reconcile_rejected",
            user_id=user_id,
            entity_type="payment",
            entity_id=payment.id,
            details={
                "reason": "checkout_mismatch",
                "stored": stored_checkout,
                "query": query.checkout_request_id,
            },
        )
        conn.commit()
        return {
            "ok": False,
            "reason": "checkout_mismatch",
            "payment_id": payment.id,
        }

    stored_merchant = payment.provider_merchant_request_id
    if query.merchant_request_id is not None:
        if stored_merchant is None or str(stored_merchant) != str(query.merchant_request_id):
            audit_module.record(
                conn,
                action="payment.reconcile_rejected",
                user_id=user_id,
                entity_type="payment",
                entity_id=payment.id,
                details={
                    "reason": "merchant_mismatch",
                    "stored": stored_merchant,
                    "query": query.merchant_request_id,
                },
            )
            conn.commit()
            return {
                "ok": False,
                "reason": "merchant_mismatch",
                "payment_id": payment.id,
            }

    if query.phone_number is not None and str(query.phone_number).strip() != "":
        try:
            q_norm = normalize_ke_msisdn(str(query.phone_number))
        except InvalidSaleData:
            audit_module.record(
                conn,
                action="payment.reconcile_rejected",
                user_id=user_id,
                entity_type="payment",
                entity_id=payment.id,
                details={"reason": "phone_invalid", "query_phone": str(query.phone_number)},
            )
            conn.commit()
            return {"ok": False, "reason": "phone_invalid", "payment_id": payment.id}
        if payment.phone_number:
            try:
                stored_norm = normalize_ke_msisdn(payment.phone_number)
            except InvalidSaleData:
                stored_norm = None
            if stored_norm is not None and stored_norm != q_norm:
                audit_module.record(
                    conn,
                    action="payment.reconcile_rejected",
                    user_id=user_id,
                    entity_type="payment",
                    entity_id=payment.id,
                    details={
                        "reason": "phone_mismatch",
                        "stored": stored_norm,
                        "query": q_norm,
                    },
                )
                conn.commit()
                return {
                    "ok": False,
                    "reason": "phone_mismatch",
                    "payment_id": payment.id,
                }

    result_code = query.result_code

    if result_code == 0:
        if query.amount_kes is not None:
            expected_cents = int(query.amount_kes) * 100
        else:
            expected_cents = payment.amount_cents
        try:
            confirmed = payments_module.confirm_payment_and_complete_sale(
                conn,
                payment_id=payment.id,
                expected_amount_cents=expected_cents,
                provider_receipt_number=query.mpesa_receipt_number,
                provider_checkout_request_id=payment.provider_checkout_request_id,
                provider_merchant_request_id=payment.provider_merchant_request_id,
                user_id=user_id,
            )
        except (PaymentConflict, PaymentNotFound) as exc:
            audit_module.record(
                conn,
                action="payment.reconcile_rejected",
                user_id=user_id,
                entity_type="payment",
                entity_id=payment.id,
                details={"reason": str(exc)},
            )
            conn.commit()
            return {
                "ok": False,
                "reason": "confirm_conflict",
                "detail": str(exc),
                "payment_id": payment.id,
            }
        audit_module.record(
            conn,
            action="payment.reconcile_confirmed",
            user_id=user_id,
            entity_type="payment",
            entity_id=confirmed.id,
            details={
                "sale_id": confirmed.sale_id,
                "result_code": 0,
                "source": "stk_query",
            },
        )
        conn.commit()
        return {
            "ok": True,
            "reason": "confirmed",
            "payment_id": confirmed.id,
            "sale_id": confirmed.sale_id,
            "status": confirmed.status,
        }

    if result_code in _TERMINAL_CANCEL_CODES:
        try:
            payments_module.transition_payment(
                conn,
                payment_id=payment.id,
                new_status="CANCELLED",
                last_error=_sanitize_error(query.result_desc) or None,
                user_id=user_id,
            )
        except Exception:
            pass
        audit_module.record(
            conn,
            action="payment.reconcile_cancelled",
            user_id=user_id,
            entity_type="payment",
            entity_id=payment.id,
            details={"result_code": result_code, "result_desc": _sanitize_error(query.result_desc)},
        )
        conn.commit()
        return {
            "ok": True,
            "reason": "cancelled",
            "result_code": result_code,
            "payment_id": payment.id,
            "status": "CANCELLED",
        }

    if result_code in _TERMINAL_FAIL_CODES:
        try:
            payments_module.transition_payment(
                conn,
                payment_id=payment.id,
                new_status="FAILED",
                last_error=_sanitize_error(query.result_desc) or None,
                user_id=user_id,
            )
        except Exception:
            pass
        audit_module.record(
            conn,
            action="payment.reconcile_failed",
            user_id=user_id,
            entity_type="payment",
            entity_id=payment.id,
            details={"result_code": result_code, "result_desc": _sanitize_error(query.result_desc)},
        )
        conn.commit()
        return {
            "ok": True,
            "reason": "failed",
            "result_code": result_code,
            "payment_id": payment.id,
            "status": "FAILED",
        }

    audit_module.record(
        conn,
        action="payment.reconcile_ambiguous",
        user_id=user_id,
        entity_type="payment",
        entity_id=payment.id,
        details={
            "result_code": result_code,
            "result_desc": _sanitize_error(query.result_desc),
            "sale_id": payment.sale_id,
        },
    )
    conn.execute(
        "UPDATE payments SET last_error = ?, updated_at = datetime('now') WHERE id = ?",
        (
            _sanitize_error(f"reconcile_ambiguous:{result_code}:{query.result_desc}"),
            payment.id,
        ),
    )
    conn.commit()
    return {
        "ok": False,
        "reason": "ambiguous",
        "result_code": result_code,
        "payment_id": payment.id,
        "status": payment.status,
    }
