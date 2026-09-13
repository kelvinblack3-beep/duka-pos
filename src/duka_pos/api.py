"""FastAPI HTTP boundary for Duka POS M1.

This layer only validates input shape, maps to domain calls, and maps
domain errors to HTTP status codes. No business rules live here — they
live in products.py / sales.py / money.py.

Cashier-facing responses never include cost_price_cents or gross profit.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from duka_pos import db as db_module
from duka_pos import products as products_module
from duka_pos import sales as sales_module
from duka_pos.errors import (
    DukaPosError,
    InsufficientStock,
    ProductNotFound,
    ReceiptNotFound,
    SaleNotFound,
    UnsupportedPaymentMethod,
)
app = FastAPI(title="Duka POS", version="0.1.0")


# ---------------------------------------------------------------------------
# Connection handling
# ---------------------------------------------------------------------------

_connection: sqlite3.Connection | None = None

#: A single SQLite connection is shared across requests in M1 (one shop
#: till, one process). FastAPI runs sync endpoints in a thread pool, so
#: this lock serializes access to that one connection — it is not a
#: substitute for the atomic transaction guarantees inside db.transaction,
#: it just prevents two threads from interleaving statements on the same
#: connection object at once.
_connection_lock = threading.Lock()


def get_connection() -> sqlite3.Connection:
    """Return the process-wide connection, opening/initializing it on first use.

    Tests override this dependency with an isolated per-test connection via
    `app.dependency_overrides`.
    """
    global _connection
    with _connection_lock:
        if _connection is None:
            _connection = db_module.connect_and_init()
        return _connection


def reset_connection_for_testing() -> None:
    """Test-only helper to drop the cached module-level connection."""
    global _connection
    if _connection is not None:
        _connection.close()
    _connection = None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ProductCreateRequest(BaseModel):
    name: str
    unit: Literal[
        "kg", "g", "litre", "ml", "piece", "packet", "bottle", "box", "carton"
    ]
    cost_price_cents: int = Field(ge=0)
    selling_price_cents: int = Field(ge=0)
    barcode: str | None = None


class ProductResponse(BaseModel):
    """Owner/manager view: includes cost. Not for cashier screens."""

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
    payment_method: Literal["CASH"] = "CASH"
    lines: list[SaleLineRequest]


class SaleLineResponse(BaseModel):
    product_id: int
    product_name: str
    quantity_milli: int
    unit_price_cents: int
    line_total_cents: int


class PaymentResponse(BaseModel):
    method: str
    status: str
    amount_cents: int


class SaleResponse(BaseModel):
    """Cashier-facing sale view: no cost/profit fields."""

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


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

_NOT_FOUND_ERRORS = (ProductNotFound, SaleNotFound, ReceiptNotFound)
_CONFLICT_ERRORS = (InsufficientStock,)
_NOT_IMPLEMENTED_ERRORS = (UnsupportedPaymentMethod,)


def _handle_domain_error(exc: DukaPosError) -> HTTPException:
    if isinstance(exc, _NOT_FOUND_ERRORS):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, _CONFLICT_ERRORS):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, _NOT_IMPLEMENTED_ERRORS):
        return HTTPException(status_code=501, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/products", response_model=ProductResponse, status_code=201)
def create_product(
    body: ProductCreateRequest, conn: sqlite3.Connection = Depends(get_connection)
) -> ProductResponse:
    try:
        product = products_module.create_product(
            conn,
            name=body.name,
            unit=body.unit,
            cost_price_cents=body.cost_price_cents,
            selling_price_cents=body.selling_price_cents,
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
    product_id: int,
    body: StockAddRequest,
    conn: sqlite3.Connection = Depends(get_connection),
) -> StockAddResponse:
    try:
        new_balance = products_module.add_stock(
            conn,
            product_id=product_id,
            quantity_milli=body.quantity_milli,
            unit_cost_cents=body.unit_cost_cents,
            reference_type=body.reference_type,
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
            conn,
            client_reference=body.client_reference,
            lines=[line.model_dump() for line in body.lines],
            payment_method=body.payment_method,
        )
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
    except DukaPosError as exc:
        raise _handle_domain_error(exc) from exc
    return ReceiptResponse(
        sale_id=receipt.sale_id,
        receipt_number=receipt.receipt_number,
        created_at=receipt.created_at,
        lines=[
            ReceiptLineResponse(
                product_name=line.product_name,
                quantity_milli=line.quantity_milli,
                unit_price_cents=line.unit_price_cents,
                line_total_cents=line.line_total_cents,
            )
            for line in receipt.lines
        ],
        subtotal_cents=receipt.subtotal_cents,
        total_cents=receipt.total_cents,
        payment_method=receipt.payment_method,
        payment_status=receipt.payment_status,
    )


def _sale_to_response(sale: sales_module.Sale) -> SaleResponse:
    return SaleResponse(
        id=sale.id,
        client_reference=sale.client_reference,
        status=sale.status,
        subtotal_cents=sale.subtotal_cents,
        total_cents=sale.total_cents,
        created_at=sale.created_at,
        lines=[
            SaleLineResponse(
                product_id=line.product_id,
                product_name=line.product_name,
                quantity_milli=line.quantity_milli,
                unit_price_cents=line.unit_price_cents,
                line_total_cents=line.line_total_cents,
            )
            for line in sale.lines
        ],
        payment=(
            PaymentResponse(
                method=sale.payment.method,
                status=sale.payment.status,
                amount_cents=sale.payment.amount_cents,
            )
            if sale.payment
            else None
        ),
    )
