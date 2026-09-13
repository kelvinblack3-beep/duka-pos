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

Last updated: 2026-09-13 (Milestone 1)

## Milestone 0 foundation

| Capability | Status |
|---|---|
| Repository structure, .gitignore, license notes | IMPLEMENTED |
| Architecture / ADR documentation | IMPLEMENTED |
| Python package `duka_pos` importable | IMPLEMENTED / TESTED |
| Environment smoke test (`tests/test_environment.py`) | IMPLEMENTED / TESTED |
| Architecture and ADR documentation | IMPLEMENTED |
| Docker | Not required. Optional later. Not present. |

## Milestone 1 — core POS engine

M1 was implemented on top of the M0 foundation. **No UI.** All of the
following is exercised by the automated test suite (`pytest`, 64 tests,
all passing at the time of writing — see ENGINEERING_LOG.md for the exact
command and result).

| Item | Status |
|---|---|
| SQLite schema (`src/duka_pos/schema.sql`) — products, stock_balances, stock_movements, sales, sale_lines, payments, receipts | IMPLEMENTED / TESTED |
| SQLite connection handling: configurable path, default `data/duka_pos.sqlite`, WAL, `foreign_keys=ON`, atomic transaction context manager | IMPLEMENTED / TESTED |
| Integer-cents money, integer-thousandths quantity (`src/duka_pos/money.py`) | IMPLEMENTED / TESTED |
| Product create/retrieve, supported units | IMPLEMENTED / TESTED |
| Stock movement ledger + stock balance projection, `add_stock` | IMPLEMENTED / TESTED |
| Weighted/loose product quantities (integer milli-kg) | IMPLEMENTED / TESTED |
| Sale creation: atomic (sale + lines + stock deduction + stock movement + payment + receipt in one SQLite transaction) | IMPLEMENTED / TESTED |
| Historical price/cost preserved on sale lines | IMPLEMENTED / TESTED |
| Cash payment, auto-CONFIRMED | IMPLEMENTED / TESTED |
| Payment model extensible to MPESA/CARD/OTHER at the schema level; those methods are explicitly rejected by the domain layer in M1 (`UnsupportedPaymentMethod`) | IMPLEMENTED (schema) / PLANNED (real adapters) |
| Idempotent sale creation via `client_reference` | IMPLEMENTED / TESTED |
| Rollback of the entire sale transaction on any failure (insufficient stock, missing product) | IMPLEMENTED / TESTED |
| Receipt retrieval (no cost/profit fields) | IMPLEMENTED / TESTED |
| FastAPI app: health, create/get product, add stock, create/get sale, get receipt | IMPLEMENTED / TESTED |
| Rice acceptance test (below) | IMPLEMENTED / TESTED |
| Login | PLANNED |
| Users / roles (owner, manager, cashier) | PLANNED |
| Cart / cashier UI | PLANNED |
| Returns | PLANNED |
| Cashier shifts | PLANNED |

### Rice acceptance test (now implemented and passing)

`tests/test_sales_rice.py`:

1. Create Rice at KSh 160/kg (selling_price_cents=16000), cost KSh 120/kg (cost_price_cents=12000)
2. Add 50 kg stock (quantity_milli=50000)
3. Sell 1.35 kg (quantity_milli=1350)
4. Observed: sale total 21600 cents (KSh 216.00), remaining stock 48650 milli-kg (48.65 kg), gross profit 5400 cents (KSh 54.00)

This matches the required result exactly.

## Kenyan integrations

| Capability | Status |
|---|---|
| M-Pesa / Daraja | PLANNED |
| eTIMS | PLANNED |

## Explicit non-goals for current code

The following are **not** in the repository as running software, even
after Milestone 1:

- authentication / login / roles
- a seeded product catalogue (products are created via the API/tests only;
  no real shop products are pre-loaded)
- a committed SQLite database file (`.gitignore` excludes `data/*`;
  `data/duka_pos.sqlite` is created at runtime, never checked in)
- M-Pesa credentials, Daraja adapter, or any M-Pesa payment path (payment
  method is schema-ready for `MPESA` but the domain layer explicitly
  rejects it with `UnsupportedPaymentMethod`)
- eTIMS credentials or adapter
- receipt printer, barcode scanner, or scale integration
- UI / frontend / Electron / Tauri / cashier screen
- PostgreSQL, Redis, Docker Compose, cloud deploy
- authentication on the API endpoints (M1 is the core engine milestone,
  not the cashier-authentication milestone — see AI_ENGINEERING_PROTOCOL.md)
