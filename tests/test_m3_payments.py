"""M3.1 payment foundation tests.

Covers state machine, pending stock protection, atomic confirmation,
amount verification, provider identity, idempotency, rollback, and
public-API force-confirm protection.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from duka_pos import payments as payments_module
from duka_pos import products as products_module
from duka_pos import sales as sales_module
from duka_pos.errors import (
    InsufficientStock,
    InvalidPaymentTransition,
    PaymentConflict,
    ReceiptNotFound,
)


def _seed_rice(conn):
    product = products_module.create_product(
        conn, name="Rice", unit="kg", cost_price_cents=12_000, selling_price_cents=16_000
    )
    products_module.add_stock(conn, product_id=product.id, quantity_milli=50_000)
    return product


def test_pending_mpesa_does_not_deduct_stock_or_create_receipt(conn):
    product = _seed_rice(conn)
    before = products_module.get_stock_balance_milli(conn, product.id)
    sale = sales_module.create_sale(
        conn,
        client_reference="mpesa-pending-1",
        lines=[{"product_id": product.id, "quantity_milli": 1_350}],
        payment_method="MPESA",
        phone_number="254712345678",
    )
    assert sale.status == "PENDING_PAYMENT"
    assert sale.payment is not None
    assert sale.payment.status == "PENDING"
    assert sale.payment.method == "MPESA"
    assert sale.payment.amount_cents == 21_600
    assert sale.payment.phone_number == "254712345678"
    assert sale.payment.provider == "DARAJA"
    assert products_module.get_stock_balance_milli(conn, product.id) == before
    with pytest.raises(ReceiptNotFound):
        sales_module.get_receipt(conn, sale.id)


def test_confirm_pending_with_correct_amount(conn):
    product = _seed_rice(conn)
    sale = sales_module.create_sale(
        conn,
        client_reference="mpesa-confirm-ok",
        lines=[{"product_id": product.id, "quantity_milli": 1_350}],
        payment_method="MPESA",
    )
    payment_id = sale.payment.id
    confirmed = payments_module.confirm_payment_and_complete_sale(
        conn,
        payment_id=payment_id,
        expected_amount_cents=21_600,
        provider_receipt_number="RCPT-MPESA-1",
    )
    assert confirmed.status == "CONFIRMED"
    sale2 = sales_module.get_sale(conn, sale.id)
    assert sale2.status == "COMPLETED"
    assert products_module.get_stock_balance_milli(conn, product.id) == 48_650
    receipt = sales_module.get_receipt(conn, sale.id)
    assert receipt.receipt_number.startswith("RCPT-")
    assert sale2.gross_profit_cents == 5_400


def test_confirm_rejects_wrong_amount_leaves_pending(conn):
    product = _seed_rice(conn)
    sale = sales_module.create_sale(
        conn,
        client_reference="mpesa-wrong-amt",
        lines=[{"product_id": product.id, "quantity_milli": 1_350}],
        payment_method="MPESA",
    )
    with pytest.raises(PaymentConflict):
        payments_module.confirm_payment_and_complete_sale(
            conn, payment_id=sale.payment.id, expected_amount_cents=1
        )
    sale2 = sales_module.get_sale(conn, sale.id)
    assert sale2.status == "PENDING_PAYMENT"
    assert sale2.payment.status == "PENDING"
    assert products_module.get_stock_balance_milli(conn, product.id) == 50_000
    with pytest.raises(ReceiptNotFound):
        sales_module.get_receipt(conn, sale.id)


def test_confirm_rejects_missing_amount(conn):
    product = _seed_rice(conn)
    sale = sales_module.create_sale(
        conn,
        client_reference="mpesa-no-amount",
        lines=[{"product_id": product.id, "quantity_milli": 1_350}],
        payment_method="MPESA",
    )
    with pytest.raises(TypeError):
        payments_module.confirm_payment_and_complete_sale(conn, payment_id=sale.payment.id)  # type: ignore[call-arg]
    sale2 = sales_module.get_sale(conn, sale.id)
    assert sale2.status == "PENDING_PAYMENT"
    assert sale2.payment.status == "PENDING"
    assert products_module.get_stock_balance_milli(conn, product.id) == 50_000


def test_confirm_is_idempotent(conn):
    product = _seed_rice(conn)
    sale = sales_module.create_sale(
        conn,
        client_reference="mpesa-idem",
        lines=[{"product_id": product.id, "quantity_milli": 1_350}],
        payment_method="MPESA",
    )
    payment_id = sale.payment.id
    payments_module.confirm_payment_and_complete_sale(
        conn,
        payment_id=payment_id,
        expected_amount_cents=21_600,
        provider_receipt_number="R1",
    )
    payments_module.confirm_payment_and_complete_sale(
        conn,
        payment_id=payment_id,
        expected_amount_cents=21_600,
        provider_receipt_number="R1",
    )
    assert products_module.get_stock_balance_milli(conn, product.id) == 48_650
    sale2 = sales_module.get_sale(conn, sale.id)
    assert sale2.status == "COMPLETED"


def test_pending_mpesa_provider_is_daraja_identity(conn):
    product = _seed_rice(conn)
    sale = sales_module.create_sale(
        conn,
        client_reference="mpesa-provider-id",
        lines=[{"product_id": product.id, "quantity_milli": 1_000}],
        payment_method="MPESA",
    )
    assert sale.payment.provider == "DARAJA"
    cash = sales_module.create_sale(
        conn,
        client_reference="cash-provider-id",
        lines=[{"product_id": product.id, "quantity_milli": 1_000}],
        payment_method="CASH",
    )
    assert cash.payment.provider == "LOCAL_CASH"


def test_public_api_has_no_force_confirm_endpoint(conn):
    """Ordinary clients must not force PENDING → CONFIRMED via HTTP."""
    from duka_pos import api as api_module

    api_module.reset_connection_for_testing()
    product = _seed_rice(conn)
    sale = sales_module.create_sale(
        conn,
        client_reference="api-no-force",
        lines=[{"product_id": product.id, "quantity_milli": 1_000}],
        payment_method="MPESA",
    )
    payment_id = sale.payment.id

    def _override():
        return conn

    api_module.app.dependency_overrides[api_module.get_connection] = _override
    client = TestClient(api_module.app)

    for method, path in (
        ("post", f"/payments/{payment_id}/confirm"),
        ("post", f"/payments/{payment_id}/force-confirm"),
        ("patch", f"/payments/{payment_id}"),
        ("put", f"/payments/{payment_id}"),
        ("post", "/payments/confirm"),
    ):
        resp = getattr(client, method)(path, json={"expected_amount_cents": 16000})
        assert resp.status_code in (404, 405), (method, path, resp.status_code)

    resp = client.get(f"/payments/{payment_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "PENDING"

    sale2 = sales_module.get_sale(conn, sale.id)
    assert sale2.status == "PENDING_PAYMENT"
    assert sale2.payment.status == "PENDING"

    api_module.app.dependency_overrides.clear()
    api_module.reset_connection_for_testing()


def test_provider_receipt_uniqueness_across_payments(conn):
    product = _seed_rice(conn)
    s1 = sales_module.create_sale(
        conn,
        client_reference="uniq-a",
        lines=[{"product_id": product.id, "quantity_milli": 1_000}],
        payment_method="MPESA",
    )
    s2 = sales_module.create_sale(
        conn,
        client_reference="uniq-b",
        lines=[{"product_id": product.id, "quantity_milli": 1_000}],
        payment_method="MPESA",
    )
    payments_module.confirm_payment_and_complete_sale(
        conn,
        payment_id=s1.payment.id,
        expected_amount_cents=16_000,
        provider_receipt_number="SHARED-RCPT",
    )
    with pytest.raises(PaymentConflict):
        payments_module.confirm_payment_and_complete_sale(
            conn,
            payment_id=s2.payment.id,
            expected_amount_cents=16_000,
            provider_receipt_number="SHARED-RCPT",
        )
    s2b = sales_module.get_sale(conn, s2.id)
    assert s2b.status == "PENDING_PAYMENT"
