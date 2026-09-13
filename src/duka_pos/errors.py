"""Domain error types for Duka POS.

These are deterministic, local domain errors. They are raised by the
persistence/domain layer in `db.py`, `products.py`, and `sales.py`, and
translated to HTTP status codes in `api.py`. None of these errors involve
network calls or external integrations.
"""

from __future__ import annotations


class DukaPosError(Exception):
    """Base class for all Duka POS domain errors."""


class InvalidProductData(DukaPosError):
    """Raised when product creation data violates a domain rule."""


class ProductNotFound(DukaPosError):
    """Raised when a product id does not exist."""


class InvalidQuantity(DukaPosError):
    """Raised when a quantity is zero, negative, or otherwise invalid."""


class InvalidMoney(DukaPosError):
    """Raised when a money value is negative or otherwise invalid."""


class NonExactLineTotal(DukaPosError):
    """Raised when unit_price_cents * quantity_milli is not divisible by 1000.

    Per ADR-002, the line-total formula must produce an exact integer
    number of cents. Silent float-based rounding is prohibited. Rather than
    guess at a rounding rule that was never approved by the lead architect,
    Duka POS rejects the sale line outright and reports which values caused
    the non-exact result.
    """


class InsufficientStock(DukaPosError):
    """Raised when a requested sale/deduction exceeds available stock."""


class UnsupportedPaymentMethod(DukaPosError):
    """Raised when a payment method other than CASH is requested in M1.

    M1 intentionally implements CASH only. M-Pesa and card are future,
    real-adapter work — never faked. See ARCHITECTURE.md and
    AI_ENGINEERING_PROTOCOL.md.
    """


class SaleNotFound(DukaPosError):
    """Raised when a sale id does not exist."""


class ReceiptNotFound(DukaPosError):
    """Raised when a receipt for a sale id does not exist."""


class EmptySale(DukaPosError):
    """Raised when a sale is submitted with zero lines."""


class InvalidSaleData(DukaPosError):
    """Raised when sale request data (e.g. client_reference) is invalid."""


# ---------------------------------------------------------------------------
# M2 errors
# ---------------------------------------------------------------------------


class AuthenticationError(DukaPosError):
    """Raised when a request lacks valid authentication."""


class InvalidCredentials(DukaPosError):
    """Raised for failed login (generic message to avoid user enumeration)."""


class DisabledUser(DukaPosError):
    """Raised when an authenticated user account is disabled."""


class PermissionDenied(DukaPosError):
    """Raised when the authenticated user lacks the required role/permission."""


class UserNotFound(DukaPosError):
    """Raised when a user id does not exist."""


class DuplicateUsername(DukaPosError):
    """Raised when creating a user with an existing username."""


class ShiftNotFound(DukaPosError):
    """Raised when a shift id does not exist."""


class ShiftAlreadyOpen(DukaPosError):
    """Raised when a user already has an OPEN shift."""


class NoOpenShift(DukaPosError):
    """Raised when an operation requires an open shift but none exists."""


class ShiftAlreadyClosed(DukaPosError):
    """Raised when attempting to close an already-closed shift."""


class SaleAlreadyReversed(DukaPosError):
    """Raised when a sale has already been voided or returned."""


class InvalidReversal(DukaPosError):
    """Raised when a void/return request is invalid."""
