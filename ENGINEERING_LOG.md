# Engineering Log

This log records what was actually done, not what was planned.

---

## 2026-09-13 — Milestone 0 foundation

**Author:** Grok
**Authority:** Establishing the repository foundation only.

### What was done

- Created the repository structure with docs, empty package, and environment test.
- Added ARCHITECTURE.md, AI_ENGINEERING_PROTOCOL.md, PROJECT_STATUS.md, ENGINEERING_LOG.md.
- Added ADRs for SQLite and integer money/quantity.
- Python package `duka_pos` is importable at version 0.0.1.
- `tests/test_environment.py` proves the package imports and (at M0) contains only `__init__.py`.
- No business logic, no SQLite schema, no FastAPI app, no products, no sales.

### Tests run

```
pytest
```

Result: 2 passed.

No SQLite database file was created.

Milestone 1 — first vertical slice: login, create product, add stock, sell
weighted rice, deduct stock, record cash payment, generate receipt, view sale.
Wait for architect review of this M0 tree before starting M1.

---

## 2026-09-13 — M1 core POS engine (takeover)

**Author:** Claude (primary implementation engineer, taking over from Grok
per AI_ENGINEERING_PROTOCOL.md; Grok reached its usage limit after M0)
**Authority:** Executing the M1 scope already recorded as PLANNED in this
log and in PROJECT_STATUS.md as of the M0 entry above
**Starting point verified from GitHub, not from any chat summary:** `dev`
and `main` were both at commit `c71669d` (`test: add environment smoke
test`), containing only the M0 tree — `src/duka_pos/__init__.py` and
`tests/test_environment.py`. No business logic existed. This was
confirmed by cloning the repository fresh and listing every tracked file,
then running `pytest` before writing any new code (2 passed).

### M1 scope executed

- `src/duka_pos/db.py` — SQLite connection handling: configurable path via
  `DUKA_POS_DATABASE_PATH` (default `data/duka_pos.sqlite`), `PRAGMA
  foreign_keys = ON`, `PRAGMA journal_mode = WAL`, and an atomic
  `transaction()` context manager (`BEGIN IMMEDIATE` / commit / rollback on
  any exception).
- `src/duka_pos/schema.sql` — tables: `products`, `stock_balances`,
  `stock_movements` (immutable ledger), `sales`, `sale_lines`, `payments`,
  `receipts`. All money columns are integer cents; all quantity columns
  are integer thousandths. Applied via `CREATE TABLE IF NOT EXISTS`
  (sufficient for a pre-production single-file schema; a versioned
  migration tool is future work once real shop data exists).
- `src/duka_pos/money.py` — pure domain arithmetic: `validate_money_cents`,
  `validate_quantity_milli`, `validate_unit`, and `line_total_cents`,
  which implements `unit_price_cents * quantity_milli / 1000` and
  **raises `NonExactLineTotal` instead of rounding** when the division is
  not exact, per ADR-002's explicit instruction not to invent a rounding
  rule that was never approved.
- `src/duka_pos/errors.py` — domain exception hierarchy
  (`ProductNotFound`, `InvalidQuantity`, `InvalidMoney`, `InsufficientStock`,
  `UnsupportedPaymentMethod`, `SaleNotFound`, `ReceiptNotFound`, `EmptySale`,
  `InvalidSaleData`, `NonExactLineTotal`, `InvalidProductData`).
- `src/duka_pos/products.py` — `create_product`, `get_product`,
  `get_stock_balance_milli`, `add_stock` (writes an immutable `RECEIVE`
  stock movement and updates the `stock_balances` projection in one
  transaction).
- `src/duka_pos/sales.py` — `create_sale`: validates payment method (CASH
  only in M1; anything else raises `UnsupportedPaymentMethod` — no fake
  M-Pesa), checks stock and computes each line total inside one atomic
  transaction, writes the sale, sale lines (with historical
  `unit_price_cents`/`unit_cost_cents`), stock deduction, a `SALE` stock
  movement, a `CONFIRMED` cash payment, and a receipt — or rolls back
  everything on any failure. `client_reference` is the idempotency key:
  a UNIQUE constraint plus a fast pre-check means resubmitting the same
  reference returns the original sale rather than creating a duplicate,
  deducting stock twice, or double-paying. Also provides `get_sale` and
  `get_receipt` (receipts intentionally omit cost/profit).
- `src/duka_pos/api.py` — FastAPI app: `GET /health`, `POST /products`,
  `GET /products/{id}`, `POST /products/{id}/stock`, `POST /sales`,
  `GET /sales/{id}`, `GET /sales/{id}/receipt`. Domain errors are mapped to
  404 (not found), 409 (insufficient stock), 501 (unsupported payment
  method), and 422 (other validation errors). Cashier-facing response
  models never include `cost_price_cents` or gross profit.
- Updated `tests/test_environment.py`: the M0 version asserted that
  `duka_pos` contained *only* `__init__.py`, to prove M0 shipped no
  business logic. That assertion is now intentionally false by design —
  it was replaced with an M1-appropriate check that the expected M1
  modules exist. This is a deliberate, documented change, not silent
  scope creep.
- Test suite added: `tests/conftest.py` (isolated per-test SQLite DB via
  `tmp_path`), `tests/test_db.py`, `tests/test_products.py`,
  `tests/test_sales_rice.py` (the locked Rice acceptance test),
  `tests/test_idempotency.py`, `tests/test_rollback.py`,
  `tests/test_validation.py`, `tests/test_api.py`.
- `pyproject.toml`: added `httpx` to the `dev` optional dependency group
  (required by FastAPI's `TestClient`).

### Tests actually run

```
cd duka-pos
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -v
```

Result: **64 passed**, 0 failed (2 pre-existing Starlette/anyio deprecation
warnings, unrelated to this project's code).

Rice acceptance, run explicitly outside pytest to double-check no test
artifact was masking anything:

```
sale total cents: 21600
remaining stock milli: 48650
gross profit cents: 5400
RICE ACCEPTANCE: PASS
```

### Rollback and idempotency, explicitly verified

- `tests/test_rollback.py`: a two-line sale where the second line has
  insufficient stock leaves the first (otherwise-valid) product's stock
  balance completely untouched, and creates zero rows in `sales`,
  `sale_lines`, `payments`, and `receipts`. Same for a sale referencing a
  missing product.
- `tests/test_idempotency.py`: submitting the same `client_reference`
  twice returns the same sale id, deducts stock exactly once, and creates
  exactly one payment and one receipt row.

### Security review performed

- Every SQL statement uses `?` parameter placeholders; grepped the whole
  `src/duka_pos` tree for f-string/`%`/`.format` SQL construction — none
  found.
- Grepped for secrets/credentials/tokens in `src/`, `pyproject.toml`, and
  `.env.example` — none found; `.env.example` only documents the shape of
  local config.
- `.venv/` and `*.egg-info/` are not tracked by git (already covered by
  `.gitignore`).
- Negative/zero money and quantity are rejected at the domain layer
  (`InvalidMoney`, `InvalidQuantity`) and enforced again by `CHECK`
  constraints in the schema as a second line of defense.
- Cashier-facing `SaleResponse` and `ReceiptResponse` schemas in `api.py`
  do not include `cost_price_cents` or gross profit.

### Deliberately not implemented in M1 (unchanged from the approved scope)

Login, users/roles, authentication, cart/cashier UI, returns, shifts,
M-Pesa/Daraja adapter, eTIMS adapter, receipt printing, barcode scanner
integration, scale integration, remote access, backups, reporting,
dashboard, PostgreSQL, Redis, Docker Compose, Kubernetes, React, Electron,
Tauri, multi-branch sync.

### Notes

- Python 3.12.3 was used to run the test suite in this session
  (`pyproject.toml` already required `>=3.12`; unlike the M0 entry above,
  no version mismatch needed to be recorded here).
- A single process-wide SQLite connection is used by the FastAPI app in
  M1 (`check_same_thread=False`, serialized by a `threading.Lock` in
  `api.py`), matching the single-shop-till, single-process architecture.
  This is not a claim that concurrent-write load has been tested.
- These changes were made in a local clone during this session. **They
  have not been pushed to GitHub.** The acting AI in this session does not
  have GitHub write access. A patch/diff is provided for the project
  owner to apply and push to `dev`.

### Next milestone (not started)

Wait for architect review of this M1 tree before starting M2. Candidate
M2 scope (not approved, not started): cashier authentication/roles and a
minimal cashier UI over the existing M1 API — still no M-Pesa, no eTIMS,
no hardware integration.
