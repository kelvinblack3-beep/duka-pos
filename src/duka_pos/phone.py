"""Kenyan M-Pesa phone number validation and normalization.

Daraja requires digits in international form without '+', e.g. 2547XXXXXXXX.
"""

from __future__ import annotations

import re

from duka_pos.errors import InvalidSaleData


_DIGITS = re.compile(r"\D+")


def normalize_ke_msisdn(raw: str | None) -> str:
    """Normalize a Kenyan mobile number to 254XXXXXXXXX (12 digits).

    Accepts common forms:
      07XXXXXXXX, 01XXXXXXXX
      2547XXXXXXXX, 2541XXXXXXXX
      +2547XXXXXXXX, +2541XXXXXXXX

    Raises InvalidSaleData for empty, non-Kenyan, or malformed numbers.
    Does not silently invent a valid number from garbage.
    """
    if raw is None or not isinstance(raw, str) or not raw.strip():
        raise InvalidSaleData("phone_number is required for MPESA")
    digits = _DIGITS.sub("", raw.strip())
    if digits.startswith("0") and len(digits) == 10 and digits[1] in "17":
        digits = "254" + digits[1:]
    elif digits.startswith("254") and len(digits) == 12 and digits[3] in "17":
        pass
    elif len(digits) == 9 and digits[0] in "17":
        digits = "254" + digits
    else:
        raise InvalidSaleData(
            f"phone_number {raw!r} is not a valid Kenyan M-Pesa MSISDN "
            "(expected 07/01… or 2547/2541…)"
        )
    if not digits.isdigit() or len(digits) != 12:
        raise InvalidSaleData(f"phone_number {raw!r} is not a valid Kenyan M-Pesa MSISDN")
    if digits[3] not in "17":
        raise InvalidSaleData(f"phone_number {raw!r} is not a Safaricom/Airtel KE mobile prefix")
    return digits
