"""M3.3 reconciliation tests — mocked STK Push Query only."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from duka_pos import api as api_module
from duka_pos import audit as audit_module
from duka_pos import auth as auth_module
from duka_pos import mpesa_flow as mpesa_flow_module
from duka_pos import payments as payments_module
from duka_pos import products as products_module
from duka_pos import reconciliation as reconciliation_module
from duka_pos import sales as sales_module
from duka_pos import users as users_module
from duka_pos.daraja_config import DarajaConfig
from duka_pos.providers.mpesa_daraja import (
    DarajaHttpError,
    MpesaDarajaProvider,
    parse_stk_query_response,
)


def _cfg():
    return DarajaConfig(
        consumer_key="k",
        consumer_secret="s",
        shortcode="174379",
        passkey="pk",
        callback_url="https://example.test/cb",
        environment="sandbox",
        timeout_seconds=5.0,
    )


class FakeTransport:
    """Supports OAuth, STK push, and STK query URLs."""

    def __init__(self):
        self.oauth_status, self.oauth_body = 200, {
            "access_token": "tok_test",
            "expires_in": "3599",
        }
        self.stk_status, self.stk_body = 200, {
            "MerchantRequestID": "mr-1",
            "CheckoutRequestID": "ws_CO_test_1",
            "ResponseCode": "0",
            "ResponseDescription": "Success",
            "CustomerMessage": "Success",
        }
        self.query_status = 200
        self.query_body = {
            "ResponseCode": "0",
            "ResponseDescription": "The service request has been accepted successfully",
            "MerchantRequestID": "mr-1",
            "CheckoutRequestID": "ws_CO_test_1",
            "ResultCode": "0",
            "ResultDesc": "The service request is processed successfully.",
        }
        self.calls = []

    def request(self, method, url, *, headers=None, body=None, timeout=30.0):
        self.calls.append((method, url, body))
        if "oauth" in url:
            return self.oauth_status, json.dumps(self.oauth_body).encode()
        if "stkpushquery" in url or "query" in url.lower():
            return self.query_status, json.dumps(self.query_body).encode()
        if "stkpush" in url:
            return self.stk_status, json.dumps(self.stk_body).encode()
        return 404, b"{}"


@pytest.fixture
def conn(tmp_path):
    from duka_pos import db as db_module

    path = str(tmp_path / "t.db")
    c = db_module.connect_and_init(path)
    yield c
    c.close()


def _seed_pending_mpesa(conn, *, amount_cents=10000, phone="254712345678"):
    p = products_module.create_product(
        conn, name="Milk", unit="litre", cost_price_cents=50, selling_price_cents=100
    )
    products_module.add_stock(conn, product_id=p.id, quantity_milli=10000)
    sale = sales_module.create_sale(
        conn,
        client_reference="ref-m33",
        lines=[{"product_id": p.id, "quantity_milli": 1000}],
        payment_method="MPESA",
        phone_number=phone,
    )
    tr = FakeTransport()
    provider = MpesaDarajaProvider(config=_cfg(), transport=tr)
    mpesa_flow_module.initiate_stk_for_payment(
        conn, payment_id=sale.payment.id, provider=provider
    )
    sale = sales_module.get_sale(conn, sale.id)
    return sale, tr, provider


def test_parse_stk_query_success():
    data = {
        "ResponseCode": "0",
        "ResponseDescription": "ok",
        "MerchantRequestID": "mr",
        "CheckoutRequestID": "co",
        "ResultCode": "0",
        "ResultDesc": "Success",
        "Amount": "100",
        "MpesaReceiptNumber": "ABC123",
        "PhoneNumber": "254712345678",
    }
    r = parse_stk_query_response(data)
    assert r.result_code == 0
    assert r.amount_kes == 100
    assert r.mpesa_receipt_number == "ABC123"


def test_parse_stk_query_missing_result_code():
    with pytest.raises(ValueError, match="missing ResultCode"):
        parse_stk_query_response({"ResponseCode": "0"})


def test_parse_stk_query_malformed_result_code_no_nameerror():
    """Regression: malformed ResultCode must raise ValueError, never NameError."""
    with pytest.raises(ValueError) as ei:
        parse_stk_query_response(
            {
                "ResponseCode": "0",
                "MerchantRequestID": "mr",
                "CheckoutRequestID": "co",
                "ResultCode": "xyz",
                "ResultDesc": "bad",
            }
        )
    assert not isinstance(ei.value, NameError)
    assert "not numeric" in str(ei.value)


def test_reconcile_success_confirms(conn):
    sale, tr, provider = _seed_pending_mpesa(conn)
    tr.query_body["ResultCode"] = "0"
    tr.query_body["Amount"] = "100"
    tr.query_body["MpesaReceiptNumber"] = "RCPT1"
    r = reconciliation_module.reconcile_payment(
        conn, payment_id=sale.payment.id, provider=provider, user_id=None
    )
    assert r["ok"] is True
    assert r["reason"] == "confirmed"
    assert sales_module.get_sale(conn, sale.id).status == "COMPLETED"


def test_reconcile_terminal_fail(conn):
    sale, tr, provider = _seed_pending_mpesa(conn)
    tr.query_body["ResultCode"] = "1037"
    r = reconciliation_module.reconcile_payment(
        conn, payment_id=sale.payment.id, provider=provider
    )
    assert r["ok"] is True
    assert r["reason"] == "failed"
    pay = payments_module.get_payment(conn, sale.payment.id)
    assert pay.status == "FAILED"


def test_reconcile_terminal_cancel(conn):
    sale, tr, provider = _seed_pending_mpesa(conn)
    tr.query_body["ResultCode"] = "1032"
    r = reconciliation_module.reconcile_payment(
        conn, payment_id=sale.payment.id, provider=provider
    )
    assert r["ok"] is True
    assert r["reason"] == "cancelled"
    pay = payments_module.get_payment(conn, sale.payment.id)
    assert pay.status == "CANCELLED"


def test_reconcile_malformed_result_code(conn):
    sale, tr, provider = _seed_pending_mpesa(conn)
    tr.query_body["ResultCode"] = "not-a-number"
    r = reconciliation_module.reconcile_payment(
        conn, payment_id=sale.payment.id, provider=provider
    )
    assert r["ok"] is False
    assert r["reason"] == "malformed"


def test_reconcile_ambiguous_stays_pending(conn):
    sale, tr, provider = _seed_pending_mpesa(conn)
    tr.query_body["ResultCode"] = "499"
    r = reconciliation_module.reconcile_payment(
        conn, payment_id=sale.payment.id, provider=provider
    )
    assert r["ok"] is False
    assert r["reason"] == "ambiguous"
    pay = payments_module.get_payment(conn, sale.payment.id)
    assert pay.status in ("PENDING", "INITIATED")


def test_reconcile_checkout_mismatch(conn):
    sale, tr, provider = _seed_pending_mpesa(conn)
    tr.query_body["CheckoutRequestID"] = "ws_CO_OTHER"
    r = reconciliation_module.reconcile_payment(
        conn, payment_id=sale.payment.id, provider=provider
    )
    assert r["ok"] is False
    assert r["reason"] == "checkout_mismatch"


def test_api_reconcile_authenticated(conn, monkeypatch):
    sale, tr, provider = _seed_pending_mpesa(conn)
    tr.query_body["ResultCode"] = "0"
    tr.query_body["Amount"] = "100"

    users_module.create_user(conn, username="owner1", password="pass", role="OWNER")
    user, token = auth_module.authenticate(conn, username="owner1", password="pass")

    real_init = MpesaDarajaProvider.__init__

    def _init(self, config=None, transport=None):
        real_init(self, config=config or _cfg(), transport=tr)

    monkeypatch.setattr(MpesaDarajaProvider, "__init__", _init)

    api_module.reset_connection_for_testing()
    api_module.app.dependency_overrides[api_module.get_connection] = lambda: conn
    client = TestClient(api_module.app)
    resp = client.post(
        f"/payments/{sale.payment.id}/reconcile",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reason"] == "confirmed"
    assert sales_module.get_sale(conn, sale.id).status == "COMPLETED"
    api_module.app.dependency_overrides.clear()
    api_module.reset_connection_for_testing()


def test_api_reconcile_requires_auth(conn):
    sale, tr, provider = _seed_pending_mpesa(conn)
    api_module.reset_connection_for_testing()
    api_module.app.dependency_overrides[api_module.get_connection] = lambda: conn
    client = TestClient(api_module.app)
    resp = client.post(f"/payments/{sale.payment.id}/reconcile")
    assert resp.status_code == 401
    api_module.app.dependency_overrides.clear()
    api_module.reset_connection_for_testing()
