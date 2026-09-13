"""Integer money (KES cents) and quantity (thousandths of a unit) helpers.

Per ADR-002: money is never a Python float, never a SQLite REAL, and never
a SQLite NUMERIC used as decimal. Quantity is always an integer number of
thousandths of the product's unit (e.g. 1.350 kg == 1350).

This module contains no I/O. It is pure domain arithmetic so it can be
tested independently of SQLite or FastAPI.
"""

from __future__ import annotations

from duka_pos.errors import InvalidMoney, InvalidQuantity, NonExactLineTotal

#: Supported product units (ADR/README locked list).
SUPPORTED_UNITS = frozenset(
    {"kg", "g", "litre", "ml", "piece", "packet", "bottle", "box", "carton"}
)

#: Thousandths scale used for all persisted quantities.
QUANTITY_SCALE = 1000


def validate_money_cents(value: object, *, field: str) -> int:
    """Validate a money value is a non-negative integer number of cents.

    Rejects bool (a bool is technically an int in Python but must never be
    accepted as a money value), float, and negative values.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidMoney(f"{field} must be an integer number of KES cents, got {value!r}")
    if value < 0:
        raise InvalidMoney(f"{field} must not be negative, got {value}")
    return value


def validate_quantity_milli(value: object, *, field: str, allow_zero: bool = False) -> int:
    """Validate a quantity value is an integer number of thousandths."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidQuantity(f"{field} must be an integer number of thousandths, got {value!r}")
    if allow_zero:
        if value < 0:
            raise InvalidQuantity(f"{field} must not be negative, got {value}")
    else:
        if value <= 0:
            raise InvalidQuantity(f"{field} must be a positive quantity, got {value}")
    return value


def validate_unit(unit: object) -> str:
    if not isinstance(unit, str) or unit not in SUPPORTED_UNITS:
        raise InvalidProductUnit(unit)
    return unit


class InvalidProductUnit(InvalidMoney):
    """Raised when a product unit is not one of the supported units."""

    def __init__(self, unit: object) -> None:
        super().__init__(f"unsupported unit {unit!r}; must be one of {sorted(SUPPORTED_UNITS)}")


def line_total_cents(unit_price_cents: int, quantity_milli: int) -> int:
    """Compute an exact line total in cents.

    line_total_cents = (unit_price_cents * quantity_milli) / 1000

    Per ADR-002, this division must be exact. If the product is not
    divisible by 1000, the sale line is rejected rather than silently
    rounded, per the explicit domain rule in ADR-002.
    """
    product = unit_price_cents * quantity_milli
    if product % QUANTITY_SCALE != 0:
        raise NonExactLineTotal(
            "line total is not an exact number of cents: "
            f"unit_price_cents={unit_price_cents} * quantity_milli={quantity_milli} "
            f"= {product}, which is not divisible by {QUANTITY_SCALE}. "
            "Adjust the quantity or price so the result is exact."
        )
    return product // QUANTITY_SCALE


def cents_to_shillings_display(cents: int) -> str:
    """Format integer cents as a KSh display string. Formatting only, not storage."""
    shillings, remainder = divmod(cents, 100)
    return f"KSh {shillings}.{remainder:02d}"


def milli_to_unit_display(quantity_milli: int) -> str:
    """Format integer thousandths as a decimal display string. Formatting only."""
    whole, remainder = divmod(quantity_milli, QUANTITY_SCALE)
    return f"{whole}.{remainder:03d}"
