# M-Pesa (Safaricom Daraja)

Status: **PLANNED**

- Will use official Safaricom Daraja APIs.
- Credentials will live in local environment configuration, never in git
  and never in frontend code.
- Payment states (planned): INITIATED, PENDING, CONFIRMED, FAILED,
  CANCELLED, REVERSED, REFUNDED.
- Sandbox first. A passing sandbox test is not production-ready.

This folder has no adapter code and no credentials. Do not add a fake
M-Pesa implementation that is described as the real integration.
