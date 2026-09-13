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

Last updated: 2026-09-13 (Milestone 3.3 payment reconciliation)

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
| Payment provider abstraction; pending MPESA without stock/receipt | IMPLEMENTED / TESTED |
| `confirm_payment_and_complete_sale` mandatory amount check | IMPLEMENTED / TESTED |
| No public force-confirm API | IMPLEMENTED / TESTED |

## Milestone 3.2 — Daraja STK + callback

| Item | Status |
|---|---|
| OAuth + STK Push HTTP client | IMPLEMENTED / TESTED |
| STK callback endpoint + correlation (checkout/merchant/phone) | IMPLEMENTED / TESTED |
| Idempotent confirm; pending stock-neutral | IMPLEMENTED / TESTED |

## Milestone 3.3 — payment reconciliation

| Item | Status |
|---|---|
| STK Push Query client (`/mpesa/stkpushquery/v1/query`) | IMPLEMENTED / TESTED |
| `reconciliation.reconcile_payment` domain service | IMPLEMENTED / TESTED |
| Lost-callback recovery via provider query | IMPLEMENTED / TESTED |
| Correlation on query (checkout/merchant/phone) | IMPLEMENTED / TESTED |
| Terminal cancel (1032) / failure codes; ambiguous stays PENDING | IMPLEMENTED / TESTED |
| Callback + reconcile race safe (one stock, one receipt) | IMPLEMENTED / TESTED |
| Authenticated `POST /payments/{id}/reconcile` | IMPLEMENTED / TESTED |
| Transaction Status API (initiator credentials) | **NOT IMPLEMENTED** |
| eTIMS | **NOT IMPLEMENTED** |

## Explicit non-claims

- Not claimed production-ready without live Safaricom validation
- No eTIMS, no UI, no Docker requirement
- No PostgreSQL / Redis / Celery / microservices
- No client force-confirm; confirmation only from trusted provider evidence
