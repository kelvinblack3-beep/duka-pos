"""M-Pesa Daraja provider: identity + OAuth + STK Push HTTP client.

M3.1 defined the DARAJA identity only.
M3.2 adds real HTTP against the current Safaricom Daraja contract:

  Sandbox base:  https://sandbox.safaricom.co.ke
  Production:    https://api.safaricom.co.ke

  OAuth:  GET  /oauth/v1/generate?grant_type=client_credentials
  STK:    POST /mpesa/stkpush/v1/processrequest

No inventory, sale, or stock logic lives here. Never open a SQLite transaction.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from duka_pos.daraja_config import DarajaConfig
from duka_pos.providers.base import ProviderInitiateResult

PROVIDER_NAME = "DARAJA"
_token_cache: dict[str, tuple[str, float]] = {}


class DarajaHttpError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HttpTransport(Protocol):
    def request(
        self, method: str, url: str, *, headers: dict[str, str] | None = None,
        body: bytes | None = None, timeout: float = 30.0,
    ) -> tuple[int, bytes]: ...


class UrlLibTransport:
    def request(
        self, method: str, url: str, *, headers: dict[str, str] | None = None,
        body: bytes | None = None, timeout: float = 30.0,
    ) -> tuple[int, bytes]:
        req = Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urlopen(req, timeout=timeout) as resp:
                return int(resp.status), resp.read()
        except HTTPError as exc:
            return int(exc.code), (exc.read() if hasattr(exc, "read") else b"")
        except URLError as exp:
            raise DarajaHttpError(f"Daraja network error: {exp.reason}") from exp
        except TimeoutError as exp:
            raise DarajaHttpError("Daraja request timed out") from exp


@dataclass(frozen=True)
class StkPushAccepted:
    merchant_request_id: str
    checkout_request_id: str
    response_code: str
    response_description: str
    customer_message: str | None = None


@dataclass(frozen=True)
class StkQueryResult:
    """Parsed STK Push Query response (M3.3 reconciliation).

    ResultCode is the payment outcome of the original STK request.
    Amount/receipt/phone are optional — query often omits CallbackMetadata.
    """
    response_code: str
    response_description: str
    merchant_request_id: str | None
    checkout_request_id: str | None
    result_code: int
    result_desc: str
    amount_kes: int | None = None
    mpesa_receipt_number: str | None = None
    phone_number: str | None = None


class MpesaDarajaProvider:
    method = "MPESA"
    provider_name = PROVIDER_NAME

    def __init__(self, config: DarajaConfig | None = None, transport: HttpTransport | None = None) -> None:
        self._config = config
        self._transport = transport or UrlLibTransport()

    def is_immediate(self) -> bool:
        return False

    def _require_config(self) -> DarajaConfig:
        if self._config is None:
            raise DarajaHttpError("Daraja is not configured")
        return self._config

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        cfg = self._require_config()
        cache_key = f"{cfg.environment}:{cfg.consumer_key}"
        now = time.time()
        if not force_refresh and cache_key in _token_cache:
            token, expires_at = _token_cache[cache_key]
            if now < expires_at - 30:
                return token
        basic = base64.b64encode(f"{cfg.consumer_key}:{cfg.consumer_secret}".encode()).decode("ascii")
        status, body = self._transport.request(
            "GET", cfg.oauth_url, headers={"Authorization": f"Basic {basic}"}, timeout=cfg.timeout_seconds,
        )
        if status != 200:
            raise DarajaHttpError(f"Daraja OAuth failed with HTTP {status}", status_code=status)
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exp:
            raise DarajaHttpError("Daraja OAuth returned malformed JSON") from exp
        token = data.get("access_token")
        if not token or not isinstance(token, str):
            raise DarajaHttpError("Daraja OAuth response missing access_token")
        try:
            expires_in = int(data.get("expires_in", 3599))
        except (TypeError, ValueError):
            expires_in = 3599
        _token_cache[cache_key] = (token, now + max(60, expires_in))
        return token

    def clear_token_cache(self) -> None:
        _token_cache.clear()

    @staticmethod
    def build_password(shortcode: str, passkey: str, timestamp: str) -> str:
        return base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode("ascii")

    @staticmethod
    def timestamp_now() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    def initiate_stk_push(
        self, *, amount_cents: int, phone_254: str, account_reference: str,
        transaction_desc: str = "Duka POS sale",
    ) -> StkPushAccepted:
        cfg = self._require_config()
        if amount_cents <= 0 or amount_cents % 100 != 0:
            raise DarajaHttpError("amount_cents must be positive whole-KES (divisible by 100)")
        amount_kes = amount_cents // 100
        token = self.get_access_token()
        ts = self.timestamp_now()
        password = self.build_password(cfg.shortcode, cfg.passkey, ts)
        payload = {
            "BusinessShortCode": cfg.shortcode,
            "Password": password,
            "Timestamp": ts,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount_kes,
            "PartyA": phone_254,
            "PartyB": cfg.shortcode,
            "PhoneNumber": phone_254,
            "CallBackURL": cfg.callback_url,
            "AccountReference": account_reference[:12],
            "TransactionDesc": transaction_desc[:13],
        }
        status, resp_body = self._transport.request(
            "POST", cfg.stk_push_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            body=json.dumps(payload).encode(), timeout=cfg.timeout_seconds,
        )
        try:
            data = json.loads(resp_body.decode("utf-8")) if resp_body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exp:
            raise DarajaHttpError(f"Daraja STK malformed JSON (HTTP {status})", status_code=status) from exp
        if status != 200:
            desc = data.get("errorMessage") or data.get("ResponseDescription") or "error"
            raise DarajaHttpError(f"Daraja STK rejected: HTTP {status}: {desc}", status_code=status)
        if str(data.get("ResponseCode", "")) != "0":
            raise DarajaHttpError(
                f"Daraja STK not accepted: ResponseCode={data.get('ResponseCode')} {data.get('ResponseDescription', '')}".strip(),
                status_code=status,
            )
        merchant, checkout = data.get("MerchantRequestID"), data.get("CheckoutRequestID")
        if not merchant or not checkout:
            raise DarajaHttpError("Daraja STK response missing MerchantRequestID or CheckoutRequestID")
        return StkPushAccepted(
            merchant_request_id=str(merchant), checkout_request_id=str(checkout),
            response_code=str(data.get("ResponseCode")), response_description=str(data.get("ResponseDescription") or ""),
            customer_message=data.get("CustomerMessage"),
        )

    def query_stk_status(self, checkout_request_id: str) -> StkQueryResult:
        """Query Daraja for the outcome of a prior STK Push (M3.3).

        POST /mpesa/stkpushquery/v1/query using the same OAuth token and
        Lipa password construction as initiate_stk_push. Network only —
        never call from inside a SQLite transaction.
        """
        cfg = self._require_config()
        if not checkout_request_id or not str(checkout_request_id).strip():
            raise DarajaHttpError("CheckoutRequestID is required for STK query")
        token = self.get_access_token()
        ts = self.timestamp_now()
        password = self.build_password(cfg.shortcode, cfg.passkey, ts)
        payload = {
            "BusinessShortCode": cfg.shortcode,
            "Password": password,
            "Timestamp": ts,
            "CheckoutRequestID": str(checkout_request_id).strip(),
        }
        status, resp_body = self._transport.request(
            "POST",
            cfg.stk_query_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            body=json.dumps(payload).encode(),
            timeout=cfg.timeout_seconds,
        )
        try:
            data = json.loads(resp_body.decode("utf-8")) if resp_body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exp:
            raise DarajaHttpError(
                f"Daraja STK query malformed JSON (HTTP {status})",
                status_code=status,
            ) from exp
        if not isinstance(data, dict):
            raise DarajaHttpError(
                f"Daraja STK query returned non-object (HTTP {status})",
                status_code=status,
            )
        if status != 200:
            desc = (
                data.get("errorMessage")
                or data.get("ResponseDescription")
                or data.get("ResultDesc")
                or "error"
            )
            raise DarajaHttpError(
                f"Daraja STK query rejected: HTTP {status}: {desc}",
                status_code=status,
            )
        return parse_stk_query_response(data)

    def to_initiate_result(self, accepted: StkPushAccepted) -> ProviderInitiateResult:
        return ProviderInitiateResult(
            provider=self.provider_name,
            provider_checkout_request_id=accepted.checkout_request_id,
            provider_merchant_request_id=accepted.merchant_request_id,
            raw_status=accepted.response_code, message=accepted.response_description,
        )


mpesa_daraja_provider = MpesaDarajaProvider()


def parse_stk_callback(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("callback payload must be a JSON object")
    body = payload.get("Body")
    if not isinstance(body, dict):
        raise ValueError("callback missing Body")
    stk = body.get("stkCallback")
    if not isinstance(stk, dict):
        raise ValueError("callback missing Body.stkCallback")
    merchant, checkout = stk.get("MerchantRequestID"), stk.get("CheckoutRequestID")
    if not merchant or not checkout:
        raise ValueError("callback missing MerchantRequestID or CheckoutRequestID")
    if stk.get("ResultCode") is None:
        raise ValueError("callback missing ResultCode")
    try:
        result_code_int = int(stk["ResultCode"])
    except (TypeError, ValueError) as err:
        raise ValueError(
            f"callback ResultCode is not numeric: {stk.get('ResultCode')!r}"
        ) from err
    meta: dict[str, Any] = {}
    cb_meta = stk.get("CallbackMetadata")
    if isinstance(cb_meta, dict):
        for item in cb_meta.get("Item") or []:
            if isinstance(item, dict) and "Name" in item:
                meta[str(item["Name"])] = item.get("Value")
    amount_kes = None
    if "Amount" in meta:
        try:
            amount_kes = int(float(meta["Amount"]))
        except (TypeError, ValueError):
            pass
    receipt = meta.get("MpesaReceiptNumber")
    phone = meta.get("PhoneNumber")
    return {
        "merchant_request_id": str(merchant),
        "checkout_request_id": str(checkout),
        "result_code": result_code_int,
        "result_desc": str(stk.get("ResultDesc") or ""),
        "amount_kes": amount_kes,
        "mpesa_receipt_number": str(receipt) if receipt is not None else None,
        "phone_number": str(phone) if phone is not None else None,
        "transaction_date": meta.get("TransactionDate"),
    }


def parse_stk_query_response(data: dict[str, Any]) -> StkQueryResult:
    """Parse a Daraja STK Push Query JSON body into StkQueryResult.

    Raises ValueError for missing/non-numeric ResultCode or invalid shape.
    Does not raise on missing optional metadata (amount, receipt, phone).
    """
    if not isinstance(data, dict):
        raise ValueError("STK query response must be a JSON object")
    if data.get("ResultCode") is None:
        raise ValueError("STK query response missing ResultCode")
    try:
        result_code_int = int(data["ResultCode"])
    except (TypeError, ValueError) as err:
        raise ValueError(
            f"STK query ResultCode is not numeric: {data.get('ResultCode')!r}"
        ) from err
    merchant = data.get("MerchantRequestID")
    checkout = data.get("CheckoutRequestID")
    amount_kes = None
    receipt = None
    phone = None
    if "Amount" in data and data["Amount"] is not None:
        try:
            amount_kes = int(float(data["Amount"]))
        except (TypeError, ValueError):
            pass
    if data.get("MpesaReceiptNumber") is not None:
        receipt = str(data["MpesaReceiptNumber"])
    if data.get("PhoneNumber") is not None:
        phone = str(data["PhoneNumber"])
    return StkQueryResult(
        response_code=str(data.get("ResponseCode") or ""),
        response_description=str(data.get("ResponseDescription") or ""),
        merchant_request_id=str(merchant) if merchant else None,
        checkout_request_id=str(checkout) if checkout else None,
        result_code=result_code_int,
        result_desc=str(data.get("ResultDesc") or ""),
        amount_kes=amount_kes,
        mpesa_receipt_number=receipt,
        phone_number=phone,
    )
