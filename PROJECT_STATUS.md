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

Last updated: 2026-09-14 (Milestone 4 Inventory + Catalogue Expansion)

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
| Payment states, cash + local MPESA pending | IMPLEMENTED / TESTED |

## Milestone 3.2 — Daraja STK

| Item | Status |
|---|---|
| STK push + callback | IMPLEMENTED / TESTED |

## Milestone 3.3 — reconciliation

| Item | Status |
|---|---|
| STK query recovery | IMPLEMENTED / TESTED |

## Milestone 4 — Inventory + Catalogue Expansion

| Item | Status |
|---|---|
| Product catalogue: SKU, brand, category, reorder_level_milli | IMPLEMENTED / TESTED |
| SKU/barcode uniqueness + empty normalization | IMPLEMENTED / TESTED |
| Product update, activate/deactivate | IMPLEMENTED / TESTED |
| Inactive products not sellable | IMPLEMENTED / TESTED |
| Search (name/barcode/SKU/category/brand) | IMPLEMENTED / TESTED |
| Stock receive (supplier optional, receipt, ledger) | IMPLEMENTED / TESTED |
| Stock adjustment (signed, reasons, no negative stock) | IMPLEMENTED / TESTED |
| Movement history + ledger/balance consistency | IMPLEMENTED / TESTED |
| Low-stock query | IMPLEMENTED / TESTED |
| Minimal suppliers + stock receipts | IMPLEMENTED / TESTED |
| Server-side role auth on catalogue/inventory | IMPLEMENTED / TESTED |
| Cashier responses hide cost | IMPLEMENTED / TESTED |
| Historical sale price/cost immutability | IMPLEMENTED / TESTED |
| Additive idempotent migration | IMPLEMENTED / TESTED |
| Cashier UI / barcode hardware / eTIMS / PO system | Not in M4 |
