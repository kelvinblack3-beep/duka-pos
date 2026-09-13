# Project Status

Labels used in this file:

| Label | Meaning |
|---|---|
| **PLANNED** | Approved direction, not built |
| **IMPLEMENTED** | Code exists in this repository |
| **TESTED** | Automated or documented tests have actually been run |
| **PRODUCTION-READY** | Tested against real shop conditions; not just sandbox |

Documentation, empty folders, and architecture decisions do **not** make a
feature IMPLEMENTED.

Last updated: 2026-09-13 (Milestone 3.1 payment foundation — hardened)

## Milestone 0 foundation

| Capability | Status |
|---|---|
| Repository structure, .gitignore, license notes | IMPLEMENTED |
| Architecture / ADR documentation | IMPLEMENTED |
| Python package `duka_pos` importable | IMPLEMENTED / TESTED |
| Environment smoke test (`tests/test_environment.py`) | IMPLEMENTED / TESTED |
| Docker | Not required. Optional later. Not present. |

## Milestone 1 — core POS engine

| Item | Status |
|---|---|
| SQLite schema, integer cents/milli, products, stock, cash sales | IMPLEMENTED / TESTED |
| Rice acceptance: total 21600, stock 48650, GP 5400 | IMPLEMENTED / TESTED |

## Milestone 2 — shop operations

| Item | Status |
|---|---|
| Auth, users, shifts, voids, audit | IMPLEMENTED / TESTED |

## Milestone 3.1 — payment foundation (hardened)

| Item | Status |
|---|---|
| Payment provider abstraction (`PaymentProvider`, `CashProvider`) | IMPLEMENTED / TESTED |
| Explicit pending MPESA provider identity `DARAJA` (no HTTP) | IMPLEMENTED / TESTED |
| Cash remains `LOCAL_CASH` | IMPLEMENTED / TESTED |
| Sale status `PENDING_PAYMENT`; payment status `PENDING` | IMPLEMENTED / TESTED |
| Pending MPESA: **no stock deduction**, **no reservation**, **no receipt** | IMPLEMENTED / TESTED |
| `confirm_payment_and_complete_sale` with **mandatory** `expected_amount_cents` | IMPLEMENTED / TESTED |
| Amount mismatch leaves PENDING; audits conflict | IMPLEMENTED / TESTED |
| Provider ref uniqueness (checkout / merchant / receipt) | IMPLEMENTED / TESTED |
| No public force-confirm API; domain-only confirmation | IMPLEMENTED / TESTED |
| Atomic confirm: stock + payment + sale + receipt | IMPLEMENTED / TESTED |
| Idempotent duplicate confirmation | IMPLEMENTED / TESTED |
| Insufficient-stock rollback on confirm | IMPLEMENTED / TESTED |
| Safaricom Daraja / STK / callback | **NOT IMPLEMENTED** (M3.2) |
| eTIMS | **NOT IMPLEMENTED** |

## Explicit non-claims

- No Daraja HTTP, STK Push, callbacks, or credentials in this repository
- No eTIMS
- No UI
- No Docker requirement
- No PostgreSQL / Redis / microservices
