"""M-Pesa Daraja provider identity (foundation only).

M3.1 does **not** implement Daraja HTTP, STK Push, or callbacks.
This module only defines the explicit provider identity string that
pending local MPESA payments carry so M3.2 can attach the real adapter
without ambiguity.

Cash uses LOCAL_CASH. Pending M-Pesa uses DARAJA (not a live integration).
"""

from __future__ import annotations

# Explicit provider name stored on payments.provider for method=MPESA.
# Not a network client. M3.2 will implement STK / callback against this name.
PROVIDER_NAME = "DARAJA"


class MpesaDarajaProvider:
    """Placeholder adapter identity for future M3.2 implementation.

    ``is_immediate`` is False: confirmation is asynchronous and must go
    through ``payments.confirm_payment_and_complete_sale`` after a trusted
    provider/reconciliation signal — never via a cashier force-confirm API.
    """

    method = "MPESA"
    provider_name = PROVIDER_NAME

    def is_immediate(self) -> bool:
        return False


mpesa_daraja_provider = MpesaDarajaProvider()
