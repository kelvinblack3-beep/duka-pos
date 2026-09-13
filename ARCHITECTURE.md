# Architecture — Duka POS

Status: **PLANNED** application architecture, with Milestone 0 foundation
**IMPLEMENTED** (package + docs + environment test only).

This document records the architecture approved by the lead architect.
It is not a claim that the layers below already run.

## Shape

Local-first **modular monolith** on the shop computer. One process. One
SQLite file. Integrations as optional adapters.

```
Cashier Browser
       ↓
Application/API
       ↓
Domain
       ↓
Persistence
       ↓
SQLite
       ↓
Optional Integration Adapters
```

Cashier and manager UIs talk to the same local application over HTTP on the
shop LAN (or localhost). There is no public database. There is no cloud
source of truth.

## Layers

### Cashier browser

Dedicated, simple till screen. USB/Bluetooth scanners are keyboard input.
Camera scanning is extra, not required for the basic flow. The cashier UI
must not become an ERP.

Not implemented in M0.

### Application / API

FastAPI + Uvicorn. Thin HTTP boundary: authentication, validation, mapping
to domain commands. No business rules live only in the API layer.

Declared as a dependency in M0. No routes yet.

### Domain

Products, inventory, sales, payments, receipts, shifts, audit. Pure rules
and invariants. The domain must not import Daraja, eTIMS, printer, or scale
SDKs.

Not implemented in M0.

### Persistence

SQLite is the local source of truth. See
[ADR-001](docs/decisions/ADR-001-sqlite-local-source-of-truth.md).

Required when the database is introduced:

- foreign keys enabled
- WAL mode
- real transactions around sale + stock + payment writes

No database file exists in M0.

### Optional integration adapters

Adapters sit **below** persistence of the local sale:

- M-Pesa Daraja
- KRA eTIMS
- ESC/POS receipt printer
- electronic scale
- backup / remote access

Adapters may fail. The local sale remains.

**External services must not own the local sale lifecycle.**

## Money and quantity

Floating-point must not be used for persisted money or quantity.

- Money: integer Kenya cents. `KSh 160.00` = `16000`
- Quantity: integer thousandths. `1.350 kg` = `1350`

Rice example:

```
line total  = 16000 * 1350 / 1000 = 21600 cents = KSh 216.00
stock left  = 50000 - 1350        = 48650 milli-kg = 48.65 kg
gross profit = (16000 - 12000) * 1350 / 1000 = 5400 cents = KSh 54.00
```

See [ADR-002](docs/decisions/ADR-002-integer-money-and-quantity.md).

## Sale path (planned)

```
LOGIN → CREATE/LOOKUP PRODUCT → ADD STOCK → SELL
  → persist sale + lines in one SQLite transaction
  → deduct stock
  → record payment (cash CONFIRMED immediately)
  → generate receipt
  → VIEW SALE
```

Later, if the tender is M-Pesa:

```
LOCAL SALE RECORD
  → payment INITIATED / PENDING
  → Daraja adapter
  → callback / query
  → local payment CONFIRMED | FAILED | …
```

The row in SQLite is created before any network call.

eTIMS follows the same idea: local record, queue, submit, store KRA response,
retry. Lack of KRA connectivity must not erase the shop sale.

## What this architecture is not

- Not microservices
- Not KIFAA and not a Postgres ledger platform
- Not Frappe / ERPNext
- Not Docker-mandatory
- Not Electron/Tauri in M0/M1
- Not a fake M-Pesa or fake eTIMS implementation

## Deployment (planned, untested)

Native Python install on the shop PC is the default path. Docker may be
offered later as optional packaging. A shop owner must be able to copy:

- application
- SQLite file
- configuration (without leaking secrets in git)
- later: assets, reports, backups

to another compatible computer.

This deployment path is **PLANNED**. It has not been tested on shop hardware.

## Security (planned)

- secrets only in environment / local config, never in git
- password hashing
- server-side authorization (cashiers do not receive cost/GP)
- audit log for sensitive actions

Not implemented in M0.
