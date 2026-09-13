# Project status — Duka POS

GitHub is authoritative. Conversation claims are not project state.

Labels used in this file:

| Label | Meaning |
|---|---|
| **PLANNED** | Direction is approved. No implementation in this repository. |
| **IMPLEMENTED** | Working code exists in this repository. |
| **TESTED** | Tests have actually been executed against that code. |
| **PRODUCTION-READY** | Proven in real shop conditions. Nothing is PRODUCTION-READY yet. |

Documentation, empty folders, and architecture decisions do **not** make a
feature IMPLEMENTED.

Last updated: 2026-09-13 (Milestone 0)

## Milestone 0 foundation

| Item | Status |
|---|---|
| Private GitHub repository `kelvinblack3-beep/duka-pos` | IMPLEMENTED |
| Branches `main` and `dev` | IMPLEMENTED |
| Python package `duka_pos` importable | IMPLEMENTED / TESTED |
| Environment smoke test (`tests/test_environment.py`) | IMPLEMENTED / TESTED |
| Architecture and ADR documentation | IMPLEMENTED |
| FastAPI application / routes | PLANNED |
| SQLite schema / migrations | PLANNED |
| Docker | Not required. Optional later. Not present. |

## Core POS lifecycle

| Capability | Status |
|---|---|
| Login | PLANNED |
| Users / roles (owner, manager, cashier) | PLANNED |
| Products | PLANNED |
| Inventory / stock movements | PLANNED |
| Weighted / loose products | PLANNED |
| Cart | PLANNED |
| Cash sales | PLANNED |
| Payment state machine | PLANNED |
| Receipts | PLANNED |
| View sale | PLANNED |
| Returns | PLANNED |
| Cashier shifts | PLANNED |

First acceptance test (not written):

1. Create Rice at KSh 160/kg, cost KSh 120/kg
2. Add 50 kg stock
3. Sell 1.35 kg
4. Expect total KSh 216.00, remaining stock 48.65 kg, gross profit KSh 54.00

That test belongs to Milestone 1.

## Kenyan integrations

| Capability | Status |
|---|---|
| M-Pesa Daraja (official Safaricom APIs) | PLANNED |
| Fake M-Pesa | Must not be added |
| KRA eTIMS | PLANNED |
| Fake eTIMS compliance | Must not be added |

## Hardware

| Capability | Status |
|---|---|
| USB / Bluetooth barcode scanner as keyboard input | PLANNED |
| Camera barcode scanning | PLANNED |
| Receipt printer (ESC/POS) | PLANNED |
| Electronic weighing scale | PLANNED |
| Manual weight entry | PLANNED |

## Operations

| Capability | Status |
|---|---|
| Local reporting | PLANNED |
| Owner dashboard | PLANNED |
| Remote access (VPN / mesh to shop server) | PLANNED |
| Backup / restore / migration | PLANNED |
| Purchasing / suppliers | PLANNED |

## Explicit non-goals for current code

The following are **not** in the repository as running software:

- authentication
- product catalogue (including the seven test products)
- SQLite database file
- M-Pesa credentials or adapters
- eTIMS credentials or adapters
- UI / frontend / Electron / Tauri
- PostgreSQL, Redis, Docker Compose, cloud deploy
