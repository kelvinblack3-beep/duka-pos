"""FastAPI HTTP boundary for Duka POS M1/M2/M3.1/M3.2/M3.3.

This layer only validates input shape, maps to domain calls, and maps
domain errors to HTTP status codes. No business rules live here.

Cashier-facing responses never include cost_price_cents or gross profit.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from duka_pos import audit as audit_module
from duka_pos import auth as auth_module
from duka_pos import db as db_module
from duka_pos import payments as payments_module
from duka_pos import mpesa_flow as mpesa_flow_module
from duka_pos import reconciliation as reconciliation_module
from duka_pos.daraja_config import DarajaConfigError, load_daraja_config_from_env
from duka_pos.providers.mpesa_daraja import DarajaHttpError, MpesaDarajaProvider
from duka_pos import products as products_module
from duka_pos import reversals as reversals_module
from duka_pos import sales as sales_module
from duka_pos import shifts as shifts_module
from duka_pos import users as users_module
from duka_pos.errors import (
    AuthenticationError,
    DisabledUser,
    DukaPosError,
    InsufficientStock,
    InvalidCredentials,
    InvalidPaymentTransition,
    PaymentConflict,
    PaymentNotFound,
    PermissionDenied,
    ProductNotFound,
    ReceiptNotFound,
    SaleNotFound,
    UnsupportedPaymentMethod,
)

app = FastAPI(title="Duka POS", version="0.1.0")

_connection: sqlite3.Connection | None = None
_connection_lock = threading.Lock()


def get_connection() -> sqlite3.Connection:
    global _connection
    with _connection_lock:
        if _connection is None:
            _connection = db_module.connect_and_init()
        return _connection


def reset_connection_for_testing() -> None:
    global _connection
    if _connection is not None:
        _connection.close()
    _connection = None


class ProductCreateRequest(BaseModel):
    name: str
    unit: Literal["kg", "g", "litre", "ml", "piece", "packet", "bottle", "box", "carton"]
    cost_price_cents: int = Field(ge=0)
    selling_price_cents: int = Field(ge=0)
    barcode: str | None = None


class ProductResponse(BaseModel):
    id: int
    name: str
    barcode: str | None
    unit: str
    cost_price_cents: int
    selling_price_cents: int
    active: bool
    created_at: str
    updated_at: str
    stock_quantity_milli: int


class StockAddRequest(BaseModel):
    quantity_milli: int = Field(gt=0)
    unit_cost_cents: int | None = Field(default=None, ge=0)
    reference_type: str | None = "MANUAL"
    reference_id: int | None = None


class StockAddResponse(BaseModel):
    product_id: int
    stock_quantity_milli: int


class SaleLineRequest(BaseModel):
    product_id: int
    quantity_milli: int = Field(gt=0)


class SaleCreateRequest(BaseModel):
    client_reference: str
    payment_method: Literal["CASH", "MPESA"] = "CASH"
    phone_number: str | None = None
    client_payment_reference: str | None = None
    lines: list[SaleLineRequest]


class SaleLineResponse(BaseModel):
    product_id: int
    product_name: str
    quantity_milli: int
    unit_price_cents: int
    line_total_cents: int


class PaymentResponse(BaseModel):
    id: int | None = None
    method: str
    status: str
    amount_cents: int
    provider: str | None = None
    provider_checkout_request_id: str | None = None
    provider_receipt_number: str | None = None
    phone_number: str | None = None


class SaleResponse(BaseModel):
    id: int
    client_reference: str
    status: str
    subtotal_cents: int
    total_cents: int
    created_at: str
    lines: list[SaleLineResponse]
    payment: PaymentResponse | None


class ReceiptLineResponse(BaseModel):
    product_name: str
    quantity_milli: int
    unit_price_cents: int
    line_total_cents: int


class ReceiptResponse(BaseModel):
    sale_id: int
    receipt_number: str
    created_at: str
    lines: list[ReceiptLineResponse]
    subtotal_cents: int
    total_cents: int
    payment_method: str
    payment_status: str


_NOT_FOUND_ERRORS = (ProductNotFound, SaleNotFound, ReceiptNotFound, PaymentNotFound)
_CONFLICT_ERRORS = (InsufficientStock, PaymentConflict, InvalidPaymentTransition)
_NOT_IMPLEMENTED_ERRORS = (UnsupportedPaymentMethod,)


def _handle_domain_error(exc: DukaPosError) -> HTTPException:
    if isinstance(exc, _NOT_FOUND_ERRORS):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, _CONFLICT_ERRORS):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, _NOT_IMPLEMENTED_ERRORS):
        return HTTPException(status_code=501, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/products", response_model=ProductResponse, status_code=201)
def create_product(
    body: ProductCreateRequest, conn: sqlite3.Connection = Depends(get_connection)
) -> ProductResponse:
    try:
        product = products_module.create_product(
            conn, name=body.name, unit=body.unit,
            cost_price_cents=body.cost_price_cents, selling_price_cents=body.selling_price_cents,
            barcode=body.barcode,
        )
        balance = products_module.get_stock_balance_milli(conn, product.id)
    except DukaPosError as exc:
        raise _handle_domain_error(exc) from exc
    return ProductResponse(**product.__dict__, stock_quantity_milli=balance)


@app.get("/products/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int, conn: sqlite3.Connection = Depends(get_connection)
) -> ProductResponse:
    try:
        product = products_module.get_product(conn, product_id)
        balance = products_module.get_stock_balance_milli(conn, product_id)
    except DukaPosError as exc:
        raise _handle_domain_error(exc) from exc
    return ProductResponse(**product.__dict__, stock_quantity_milli=balance)


@app.post("/products/{product_id}/stock", response_model=StockAddResponse)
def add_stock(
    product_id: int, body: StockAddRequest, conn: sqlite3.Connection = Depends(get_connection),
) -> StockAddResponse:
    try:
        new_balance = products_module.add_stock(
            conn, product_id=product_id, quantity_milli=body.quantity_milli,
            unit_cost_cents=body.unit_cost_cents, reference_type=body.reference_type,
            reference_id=body.reference_id,
        )
    except DukaPosError as exc:
        raise _handle_domain_error(exc) from exc
    return StockAddResponse(product_id=product_id, stock_quantity_milli=new_balance)


@app.post("/sales", response_model=SaleResponse, status_code=201)
def create_sale(
    body: SaleCreateRequest, conn: sqlite3.Connection = Depends(get_connection)
) -> SaleResponse:
    try:
        sale = sales_module.create_sale(
            conn, client_reference=body.client_reference,
            lines=[line.model_dump() for line in body.lines],
            payment_method=body.payment_method, phone_number=body.phone_number,
            client_payment_reference=body.client_payment_reference,
        )
        if body.payment_method == "MPESA" and sale.payment is not None:
            try:
                cfg = load_daraja_config_from_env()
                provider = MpesaDarajaProvider(config=cfg)
                mpesa_flow_module.initiate_stk_for_payment(
                    conn, payment_id=sale.payment.id, provider=provider
                )
                sale = sales_module.get_sale(conn, sale.id)
            except (DarajaConfigError, DarajaHttpError):
                try:
                    mpesa_flow_module.mark_stk_initiation_failed(
                        conn, payment_id=sale.payment.id, error_message="stk_unavailable"
                    )
                except Exception:
                    pass
                sale = sales_module.get_sale(conn, sale.id)
    except DukaPosError as exc:
        raise _handle_domain_error(exc) from exc
    return _sale_to_response(sale)


@app.get("/sales/{sale_id}", response_model=SaleResponse)
def get_sale(sale_id: int, conn: sqlite3.Connection = Depends(get_connection)) -> SaleResponse:
    try:
        sale = sales_module.get_sale(conn, sale_id)
    except DukaPosError as exc:
        raise _handle_domain_error(exc) from exc
    return _sale_to_response(sale)


@app.get("/sales/{sale_id}/receipt", response_model=ReceiptResponse)
def get_receipt(
    sale_id: int, conn: sqlite3.Connection = Depends(get_connection)
) -> ReceiptResponse:
    try:
        receipt = sales_module.get_receipt(conn, sale_id)
    except DukaPosError as exp:
        raise _handle_domain_error(exp) from exp
    return ReceiptResponse(
        sale_id=receipt.sale_id, receipt_number=receipt.receipt_number, created_at=receipt.created_at,
        lines=[ReceiptLineResponse(product_name=line.product_name, quantity_milli=line.quantity_milli,
                                   unit_price_cents=line.unit_price_cents, line_total_cents=line.line_total_cents)
               for line in receipt.lines],
        subtotal_cents=receipt.subtotal_cents, total_cents=receipt.total_cents,
        payment_method=receipt.payment_method, payment_status=receipt.payment_status,
    )


def _sale_to_response(sale: sales_module.Sale) -> SaleResponse:
    return SaleResponse(
        id=sale.id, client_reference=sale.client_reference, status=sale.status,
        subtotal_cents=sale.subtotal_cents, total_cents=sale.total_cents, created_at=sale.created_at,
        lines=[SaleLineResponse(product_id=line.product_id, product_name=line.product_name,
                                quantity_milli=line.quantity_milli, unit_price_cents=line.unit_price_cents,
                                line_total_cents=line.line_total_cents) for line in sale.lines],
        payment=(
            PaymentResponse(
                id=sale.payment.id, method=sale.payment.method, status=sale.payment.status,
                amount_cents=sale.payment.amount_cents, provider=sale.payment.provider,
                provider_checkout_request_id=sale.payment.provider_checkout_request_id,
                provider_receipt_number=sale.payment.provider_receipt_number,
                phone_number=sale.payment.phone_number,
            ) if sale.payment else None
        ),
    )


@app.get("/payments/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: int, conn: sqlite3.Connection = Depends(get_connection)
) -> PaymentResponse:
    try:
        payment = payments_module.get_payment(conn, payment_id)
    except DukaPosError as exc:
        raise _handle_domain_error(exc) from exc
    return PaymentResponse(
        id=payment.id, method=payment.method, status=payment.status, amount_cents=payment.amount_cents,
        provider=payment.provider, provider_checkout_request_id=payment.provider_checkout_request_id,
        provider_receipt_number=payment.provider_receipt_number, phone_number=payment.phone_number,
    )


@app.post("/callbacks/daraja/stk")
def daraja_stk_callback(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_connection),
) -> dict:
    """Safaricom Daraja STK Push result callback."""
    result = mpesa_flow_module.process_stk_callback(conn, payload)
    return {"ResultCode": 0, "ResultDesc": "Accepted", "detail": result}


# ---------------------------------------------------------------------------
# M2: Authentication, users, shifts, reversals, audit
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user_id: int
    username: str
    role: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: Literal["OWNER", "MANAGER", "CASHIER"]


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    active: bool
    created_at: str
    updated_at: str


class ShiftOpenRequest(BaseModel):
    opening_cash_cents: int = Field(ge=0)


class ShiftCloseRequest(BaseModel):
    closing_cash_cents: int = Field(ge=0)


class ShiftResponse(BaseModel):
    id: int
    user_id: int
    opened_at: str
    closed_at: str | None
    opening_cash_cents: int
    closing_cash_cents: int | None
    expected_cash_cents: int | None
    variance_cents: int | None
    status: str


class VoidRequest(BaseModel):
    reason: str | None = None


def _token_from_header(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("authentication required")
    return authorization[len("Bearer ") :].strip()


def get_current_user(
    conn: sqlite3.Connection = Depends(get_connection),
    authorization: str | None = Header(default=None),
) -> auth_module.AuthUser:
    token = _token_from_header(authorization)
    try:
        return auth_module.get_user_for_token(conn, token)
    except (AuthenticationError, DisabledUser) as exp:
        raise HTTPException(status_code=401, detail=str(exp)) from exp


@app.post("/payments/{payment_id}/reconcile")
def reconcile_payment_endpoint(
    payment_id: int,
    conn: sqlite3.Connection = Depends(get_connection),
    user: auth_module.AuthUser = Depends(get_current_user),
) -> dict:
    """M3.3: reconcile a pending MPESA payment via Daraja STK Push Query.

    Authenticated staff only. Never accepts client-supplied confirmation,
    amount, or receipt — only provider query evidence is used.
    """
    try:
        users_module.require_role(user, "OWNER", "MANAGER", "CASHIER")
        try:
            cfg = load_daraja_config_from_env()
            provider = MpesaDarajaProvider(config=cfg)
        except DarajaConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        result = reconciliation_module.reconcile_payment(
            conn,
            payment_id=payment_id,
            provider=provider,
            user_id=user.id,
            require_min_age=False,
        )
        return result
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PaymentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DukaPosError as exc:
        raise _handle_domain_error(exc) from exc


@app.post("/auth/login", response_model=LoginResponse)
def login(
    body: LoginRequest, conn: sqlite3.Connection = Depends(get_connection)
) -> LoginResponse:
    try:
        user, token = auth_module.authenticate(conn, username=body.username, password=body.password)
        audit_module.record(conn, action="auth.login_success", user_id=user.id, entity_type="user", entity_id=user.id, details={"username": user.username})
    except InvalidCredentials as exp:
        audit_module.record(conn, action="auth.login_failure", details={"username": body.username})
        raise HTTPException(status_code=401, detail=str(exp)) from exp
    return LoginResponse(token=token, user_id=user.id, username=user.username, role=user.role)


@app.get("/me", response_model=UserResponse)
def me(
    user: auth_module.AuthUser = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> UserResponse:
    u = users_module.get_user(conn, user.id)
    return UserResponse(id=u.id, username=u.username, role=u.role, active=u.active, created_at=u.created_at, updated_at=u.updated_at)


@app.post("/users", response_model=UserResponse, status_code=201)
def create_user_endpoint(
    body: UserCreateRequest,
    user: auth_module.AuthUser = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> UserResponse:
    try:
        users_module.require_role(user, "OWNER")
        created = users_module.create_user(conn, username=body.username, password=body.password, role=body.role)
        audit_module.record(conn, action="user.create", user_id=user.id, entity_type="user", entity_id=created.id, details={"username": created.username, "role": created.role})
    except PermissionDenied as exp:
        raise HTTPException(status_code=403, detail=str(exp)) from exp
    except DukaPosError as exp:
        raise _handle_domain_error(exp) from exp
    return UserResponse(id=created.id, username=created.username, role=created.role, active=created.active, created_at=created.created_at, updated_at=created.updated_at)


@app.post("/shifts/open", response_model=ShiftResponse, status_code=201)
def open_shift_endpoint(
    body: ShiftOpenRequest,
    user: auth_module.AuthUser = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> ShiftResponse:
    try:
        shift = shifts_module.open_shift(conn, user_id=user.id, opening_cash_cents=body.opening_cash_cents)
        audit_module.record(conn, action="shift.open", user_id=user.id, entity_type="shift", entity_id=shift.id, details={"opening_cash_cents": body.opening_cash_cents})
    except DukaPosError as exp:
        raise _handle_domain_error(exp) from exp
    return ShiftResponse(**shift.__dict__)


@app.get("/shifts/current", response_model=ShiftResponse)
def current_shift(
    user: auth_module.AuthUser = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> ShiftResponse:
    shift = shifts_module.get_open_shift_for_user(conn, user.id)
    if shift is None:
        raise HTTPException(status_code=404, detail="no open shift")
    return ShiftResponse(**shift.__dict__)


@app.post("/shifts/{shift_id}/close", response_model=ShiftResponse)
def close_shift_endpoint(
    shift_id: int, body: ShiftCloseRequest,
    user: auth_module.AuthUser = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> ShiftResponse:
    try:
        allow_manager = user.role in ("OWNER", "MANAGER")
        shift = shifts_module.close_shift(conn, shift_id=shift_id, closing_cash_cents=body.closing_cash_cents, acting_user_id=user.id, allow_manager=allow_manager)
        audit_module.record(conn, action="shift.close", user_id=user.id, entity_type="shift", entity_id=shift.id, details={"closing_cash_cents": body.closing_cash_cents, "expected_cash_cents": shift.expected_cash_cents, "variance_cents": shift.variance_cents})
    except DukaPosError as exp:
        raise _handle_domain_error(exp) from exp
    return ShiftResponse(**shift.__dict__)


@app.post("/sales/{sale_id}/void", status_code=200)
def void_sale_endpoint(
    sale_id: int, body: VoidRequest,
    user: auth_module.AuthUser = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_connection),
) -> dict:
    try:
        users_module.require_role(user, "OWNER", "MANAGER")
        rev = reversals_module.void_sale(conn, sale_id=sale_id, performed_by=user.id, reason=body.reason)
    except PermissionDenied as exp:
        raise HTTPException(status_code=403, detail=str(exp)) from exp
    except DukaPosError as exp:
        raise _handle_domain_error(exp) from exp
    return {"id": rev.id, "sale_id": rev.sale_id, "reversal_type": rev.reversal_type, "performed_by": rev.performed_by, "performed_at": rev.performed_at}
