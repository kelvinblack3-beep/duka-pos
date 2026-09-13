# Project Status

## M3.1 Hardened Payment Foundation (in progress on dev)

- payments.py domain with atomic confirm_payment_and_complete_sale, mandatory expected_amount_cents
- schema PENDING_PAYMENT + provider columns + unique indexes
- db migrations for payment columns
- providers (Cash, DARAJA identity)
- ADR-003

Remaining to complete push: sales.py MPESA pending path, api.py GET /payments, test_m3_payments.py full suite, ENGINEERING_LOG/PROJECT_STATUS final, reversals pending path.
