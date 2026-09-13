# Engineering log — Duka POS

Append-only record of engineering work. GitHub remains the source of truth.

---

## 2026-09-13 — M0 repository foundation

**Author:** Grok (primary implementation engineer)
**Authority:** Lead architect (ChatGPT) sign-off to execute Milestone 0
**GitHub owner:** kelvinblack3-beep
**Repository:** duka-pos (private), independent of kifaa

### Architect-approved locked decisions

- Repository name: `duka-pos`
- Visibility: private
- Completely separate from kifaa; kifaa must not be modified or used as the POS database/backend
- Stack: Python 3.12+, FastAPI, Uvicorn, SQLite, pytest
- Architecture: local-first modular monolith
- SQLite is the local source of truth
- Money: integer Kenya cents
- Quantity: integer thousandths of the product unit
- Docker: optional infrastructure only, not a requirement
- No Frappe / ERPNext / Frappe Cloud
- No cloud database as source of truth
- M-Pesa will eventually use official Safaricom Daraja APIs
- eTIMS will eventually be a real integration
- External integrations must never become the source of truth for local sales
- Sequence: M0 then M1; do not skip M0

### M0 scope executed

- Created private GitHub repository `kelvinblack3-beep/duka-pos`
- Created branches `main` (stable) and `dev` (integration)
- Added project documentation, ADRs, `.gitignore`, `.env.example`, `pyproject.toml`
- Added importable package `src/duka_pos`
- Added and **ran** `tests/test_environment.py` with pytest

### Deliberately not implemented in M0

Login, users, authentication, products, inventory, stock, sales, cart,
payments, M-Pesa, eTIMS, receipts, returns, purchasing, suppliers, reports,
dashboard, barcode scanning, camera scanning, scale integration, receipt
printer, remote access, VPN, backup engine, UI, frontend, mobile app,
Electron, Tauri, PostgreSQL, Redis, Docker Compose, cloud deployment,
product catalogue, Daraja credentials.

No SQLite database file was created.

### Notes

- FastAPI and Uvicorn are declared as dependencies so the foundation can grow.
  No application instance or HTTP routes were added.
- `requires-python = ">=3.12"` is set in `pyproject.toml` as approved.
  The implementation sandbox that ran pytest reported CPython 3.10.21. The
  smoke test uses no 3.12-only syntax. Shop and developer installs must use
  Python 3.12+.
- Docker was not installed and is not referenced as a requirement.

### Next milestone (not started)

Milestone 1 — first vertical slice: login, create product, add stock, sell
weighted rice, deduct stock, record cash payment, generate receipt, view sale.
Wait for architect review of this M0 tree before starting M1.
