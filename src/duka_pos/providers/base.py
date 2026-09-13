"""Payment provider protocol (adapter boundary).

No provider-specific HTTP or credentials live here. Implementations
must not open SQLite transactions; the domain layer owns persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ProviderInitiateResult:
    """Result of asking a provider to start an asynchronous payment.

    Cash never produces this; M-Pesa (M3.2) will.
    """

    provider: str
    provider_checkout_request_id: str | None = None
    provider_merchant_request_id: str | None = None
    raw_status: str | None = None
    message: str | None = None


@runtime_checkable
class PaymentProvider(Protocol):
    """Adapter interface for tender-specific payment behaviour.

    ``method`` is the local payments.method value (CASH, MPESA, …).
    ``provider_name`` is the adapter identity (e.g. LOCAL_CASH, DARAJA).
    """

    method: str
    provider_name: str

    def is_immediate(self) -> bool:
        """True if payment is confirmed in the same local transaction (cash)."""
        ...
