"""M3.2 Daraja tests — mocked HTTP only."""
from __future__ import annotations
import json
import pytest
from fastapi.testclient import TestClient
from duka_pos import api as api_module, mpesa_flow as mpesa_flow_module
from duka_pos import payments as payments_module, products as products_module, sales as sales_module
from duka_pos.daraja_config import DarajaConfig
from duka_pos.errors import InvalidSaleData
from duka_pos.phone import normalize_ke_msisdn
from duka_pos.providers.mpesa_daraja import DarajaHttpError, MpesaDarajaProvider, parse_stk_callback

def _cfg():
    return DarajaConfig(consumer_key="k", consumer_secret="s", shortcode="174379", passkey="pk",
                        callback_url="https://example.test/cb", environment="sandbox", timeout_seconds=5.0)

class FakeTransport:
    def __init__(self):
        self.oauth_status, self.oauth_body = 200, {"access_token": "tok_test", "expires_in": "3599"}
        self.stk_status, self.stk_body = 200, {
            "MerchantRequestID": "mr-1", "CheckoutRequestID": "ws_CO_test_1",
            "ResponseCode": "0", "ResponseDescription": "Success", "CustomerMessage": "Success",
        }
    def request(self, method, url, *, headers=None, body=None, timeout=30.0):
        if "oauth" in url:
            return self.oauth_status, json.dumps(self.oauth_body).encode()
        return self.stk_status, json.dumps(self.stk_body).encode()

def _seed(conn):
    p = products_module.create_product(conn, name="Rice", unit="kg", cost_price_cents=12000, selling_price_cents=16000)
    products_module.add_stock(conn, product_id=p.id, quantity_milli=50000)
    return p

def _cb(checkout="ws_CO_test_1", amount=216, receipt="RCPT1", code=0):
    body = {"MerchantRequestID": "mr-1", "CheckoutRequestID": checkout, "ResultCode": code, "ResultDesc": "ok"}
    if code == 0:
        body["CallbackMetadata"] = {"Item": [
            {"Name": "Amount", "Value": amount}, {"Name": "MpesaReceiptNumber", "Value": receipt},
            {"Name": "PhoneNumber", "Value": 254712345678},
        ]}
    return {"Body": {"stkCallback": body}}

def test_phone():
    assert normalize_ke_msisdn("0712345678") == "254712345678"
    with pytest.raises(InvalidSaleData):
        normalize_ke_msisdn("999")

def test_oauth_and_stk(conn):
    p = _seed(conn)
    sale = sales_module.create_sale(conn, client_reference="s1", lines=[{"product_id": p.id, "quantity_milli": 1350}],
                                    payment_method="MPESA", phone_number="0712345678")
    tr = FakeTransport(); prov = MpesaDarajaProvider(config=_cfg(), transport=tr); prov.clear_token_cache()
    upd = mpesa_flow_module.initiate_stk_for_payment(conn, payment_id=sale.payment.id, provider=prov)
    assert upd.provider_checkout_request_id == "ws_CO_test_1"
    assert products_module.get_stock_balance_milli(conn, p.id) == 50000

def test_callback_success_and_duplicate(conn):
    p = _seed(conn)
    sale = sales_module.create_sale(conn, client_reference="s2", lines=[{"product_id": p.id, "quantity_milli": 1350}],
                                    payment_method="MPESA", phone_number="0712345678")
    tr = FakeTransport(); prov = MpesaDarajaProvider(config=_cfg(), transport=tr); prov.clear_token_cache()
    mpesa_flow_module.initiate_stk_for_payment(conn, payment_id=sale.payment.id, provider=prov)
    r1 = mpesa_flow_module.process_stk_callback(conn, _cb())
    r2 = mpesa_flow_module.process_stk_callback(conn, _cb())
    assert r1["reason"] == "confirmed" and r2["reason"] == "already_confirmed"
    assert products_module.get_stock_balance_milli(conn, p.id) == 48650
    assert sales_module.get_sale(conn, sale.id).gross_profit_cents == 5400

def test_amount_mismatch(conn):
    p = _seed(conn)
    sale = sales_module.create_sale(conn, client_reference="s3", lines=[{"product_id": p.id, "quantity_milli": 1350}],
                                    payment_method="MPESA", phone_number="0712345678")
    tr = FakeTransport(); prov = MpesaDarajaProvider(config=_cfg(), transport=tr); prov.clear_token_cache()
    mpesa_flow_module.initiate_stk_for_payment(conn, payment_id=sale.payment.id, provider=prov)
    r = mpesa_flow_module.process_stk_callback(conn, _cb(amount=1))
    assert r["ok"] is False
    assert sales_module.get_sale(conn, sale.id).status == "PENDING_PAYMENT"

def test_cancel_callback(conn):
    p = _seed(conn)
    sale = sales_module.create_sale(conn, client_reference="s4", lines=[{"product_id": p.id, "quantity_milli": 1000}],
                                    payment_method="MPESA", phone_number="0712345678")
    tr = FakeTransport(); prov = MpesaDarajaProvider(config=_cfg(), transport=tr); prov.clear_token_cache()
    mpesa_flow_module.initiate_stk_for_payment(conn, payment_id=sale.payment.id, provider=prov)
    mpesa_flow_module.process_stk_callback(conn, _cb(code=1032))
    assert payments_module.get_payment(conn, sale.payment.id).status == "CANCELLED"

def test_api_callback(conn):
    p = _seed(conn)
    sale = sales_module.create_sale(conn, client_reference="s5", lines=[{"product_id": p.id, "quantity_milli": 1350}],
                                    payment_method="MPESA", phone_number="0712345678")
    tr = FakeTransport(); prov = MpesaDarajaProvider(config=_cfg(), transport=tr); prov.clear_token_cache()
    mpesa_flow_module.initiate_stk_for_payment(conn, payment_id=sale.payment.id, provider=prov)
    api_module.reset_connection_for_testing()
    api_module.app.dependency_overrides[api_module.get_connection] = lambda: conn
    client = TestClient(api_module.app)
    resp = client.post("/callbacks/daraja/stk", json=_cb())
    assert resp.status_code == 200 and resp.json()["ResultCode"] == 0
    assert sales_module.get_sale(conn, sale.id).status == "COMPLETED"
    api_module.app.dependency_overrides.clear(); api_module.reset_connection_for_testing()

def test_parse_and_oauth_fail():
    parse_stk_callback(_cb())
    with pytest.raises(ValueError):
        parse_stk_callback({})
    tr = FakeTransport(); tr.oauth_status = 400
    prov = MpesaDarajaProvider(config=_cfg(), transport=tr); prov.clear_token_cache()
    with pytest.raises(DarajaHttpError):
        prov.get_access_token()
