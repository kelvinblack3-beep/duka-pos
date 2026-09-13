"""Payment provider adapters.

Providers sit *outside* SQLite transactions. They must never be called
from inside ``db.transaction``.

M3.1: CashProvider (LOCAL_CASH); MpesaDarajaProvider identity (DARAJA).
M3.2: MpesaDarajaProvider OAuth + STK Push HTTP (config + injectable transport).
"""

from duka_pos.providers.base import PaymentProvider, ProviderInitiateResult
from duka_pos.providers.cash import CashProvider
from duka_pos.providers.mpesa_daraja import (
    MpesaDarajaProvider,
    PROVIDER_NAME as DARAJA_PROVIDER_NAME,
)

__all__ = [
    "PaymentProvider",
    "ProviderInitiateResult",
    "CashProvider",
    "MpesaDarajaProvider",
    "DARAJA_PROVIDER_NAME",
]
