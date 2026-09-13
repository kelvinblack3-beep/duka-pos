# Duka POS

Local-first point of sale for Kenyan mini-marts.

Duka POS is being built so a real shop till can keep selling when the internet
is down. The shop computer is the primary source of truth. This is not a cloud
POS, not a Frappe/ERPNext project, and not part of [kifaa](https://github.com/kelvinblack3-beep/kifaa).

**Current stage: Milestone 1 — core deterministic POS engine. No UI.**

Products, weighted inventory, atomic/idempotent cash sales, and receipts
work end-to-end through a FastAPI HTTP API and are covered by an automated
test suite (see PROJECT_STATUS.md for the exact list and
ENGINEERING_LOG.md for the exact test command and result). There is still
no cashier UI, no login, no M-Pesa, and no eTIMS. Do not treat this README
as a feature list — see PROJECT_STATUS.md for the honest, current status.

### Running M1 locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest        # runs the full test suite
uvicorn duka_pos.api:app --reload   # starts the local API on 127.0.0.1:8000
```

Minimum API surface: `GET /health`, `POST /products`,
`GET /products/{id}`, `POST /products/{id}/stock`, `POST /sales`,
`GET /sales/{id}`, `GET /sales/{id}/receipt`.

## Who it is for

A dedicated shop PC in a Kenyan mini-mart:

* Cashier sells packaged and loose/weighted goods
* USB barcode scanner behaves like a keyboard
* Cash first; M-Pesa and card later, as adapters
* Owner/manager reporting later
* Backup = copy the application, the SQLite file, and configuration to another compatible computer

## Local-first rule

Core till operations must work without internet:

* login, product lookup, cart, quantity/weight, pricing, cash sale
* stock deduction, receipts, shifts, local reports, local backups

Internet-dependent services are **integrations**, not the database:

* Safaricom Daraja (M-Pesa) — **PLANNED**
* KRA eTIMS — **PLANNED**
* remote owner access — **PLANNED**
* optional off-site backups — **PLANNED**

If M-Pesa or eTIMS is unreachable, the local sale must remain recoverable.
External services must not own the local sale lifecycle.

## Planned architecture

```
Cashier browser (kiosk)
        ↓
Application / API  (FastAPI)
        ↓
Domain
        ↓
Persistence
        ↓
SQLite  (local source of truth)
        ↓
Optional adapters: M-Pesa | eTIMS | printer | scale | backup
```

Approved technical decisions:

* Python 3.12+, FastAPI, Uvicorn, pytest
* Modular monolith
* SQLite with foreign keys, WAL, and transactions
* Money stored as integer Kenya cents (KSh 160.00 = 16000)
* Quantity stored as integer thousandths of the unit (1.350 kg = 1350)
* Docker is **optional** infrastructure, not a requirement
* No cloud database as source of truth

See [ARCHITECTURE.md](ARCHITECTURE.md) and [docs/decisions/](docs/decisions).

## Honesty labels

Every capability is labelled as one of:

| Label | Meaning |
|---|---|
| **PLANNED** | Approved direction, not built |
| **IMPLEMENTED** | Code exists in this repository |
| **TESTED** | Automated or documented tests have actually been run |
| **PRODUCTION-READY** | Tested against real shop conditions; not just sandbox |

Current status is tracked in [PROJECT_STATUS.md](PROJECT_STATUS.md).
Nothing is IMPLEMENTED merely because this documentation exists.

## Development status (Milestone 1)

| Area | Status |
|---|---|
| Repository, docs, Python package, environment test | IMPLEMENTED / TESTED (M0) |
| Core POS engine (products, stock, atomic cash sales, receipts, FastAPI) | IMPLEMENTED / TESTED (M1) |
| Login, users/roles, cashier UI | PLANNED |
| Weighted goods, barcode, printer, scale | PLANNED (weighted quantities already supported in M1) |
| M-Pesa Daraja, eTIMS, remote access, backup engine | PLANNED |

M-Pesa will eventually use official Safaricom Daraja APIs. eTIMS will eventually
be a real KRA integration. Neither is implemented. There is no fake payment
provider in this repository.

## Python environment

Requires **Python 3.12 or newer**. Docker is not required.

```bash
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Copy environment template (optional until later milestones):

```bash
cp .env.example .env
```

Do not put Safaricom, Daraja, or eTIMS secrets in git.

## Tests

```bash
python -m pytest -v
```

64 tests covering the full M1 surface (see PROJECT_STATUS.md and
ENGINEERING_LOG.md).

## What this repository is not

* Not KIFAA, and not a fork of KIFAA
* Not Frappe / ERPNext / Frappe Cloud
* Not a SaaS that dies without internet
* Not production software yet

## License and third-party code

Project licensing is not finalised. Third-party packages used by this
foundation are listed in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
Do not copy GPL/AGPL code into this tree without an explicit license review.

## AI engineering

GitHub is the single source of truth. Chat transcripts are not project state.
See [AI_ENGINEERING_PROTOCOL.md](AI_ENGINEERING_PROTOCOL.md).
