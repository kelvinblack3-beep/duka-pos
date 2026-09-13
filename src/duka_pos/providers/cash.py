"""Cash payment provider.

Cash is confirmed immediately inside the local SQLite transaction that
creates the sale. This adapter documents that behaviour; it performs no
network I/O.
"""

from __future__ import annotations

from duka_pos.providers.base import PaymentProvider


class CashProvider:
    method = "CASH"
    provider_name = "LOCAL_CASH"

    def is_immediate(self) -> bool:
        return True


# Singleton used by domain code.
cash_provider: PaymentProvider = CashProvider()
