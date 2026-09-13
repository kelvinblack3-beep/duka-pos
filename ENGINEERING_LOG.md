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

**Author:** Claude (primary implementation engineer)
**Authority:** Executing the M1 scope already recorded as PLANNED.

M1 core POS engine: products, stock ledger, atomic idempotent cash sales,
receipts, FastAPI, 64 tests. See prior log entries for full detail.

---

## 2026-09-13 — M2 shop operations (domain + API foundation)

**Author:** Grok (implementation engineer)
**Authority:** M2 scope as specified — authentication, users/roles, shifts, returns/voids, audit logging on top of locked M1.

### Implemented

- Schema: `users`, `sessions`, `shifts`, `sale_reversals`, `audit_log`; sales gain nullable `shift_id` / `user_id` via deterministic migration in `db.init_db`.
- `auth.py`: bcrypt password hashing, opaque session tokens, generic login failure messages (no user enumeration).
- `users.py`: create/list/disable/role-change; roles OWNER / MANAGER / CASHIER; `require_role` helper.
- `shifts.py`: open (one OPEN per user), close with server-computed expected cash and variance.
- `reversals.py`: atomic VOID/RETURN — restore stock via REVERSAL movements, mark payment REVERSED, set sale status VOID, single reversal row, audit entry. Original sale totals preserved.
- `audit.py`: append-only log; never records passwords/hashes/tokens.
- API: `POST /auth/login`, `GET /me`, `POST /users` (OWNER), `POST /shifts/open`, `GET /shifts/current`, `POST /shifts/{id}/close`, `POST /sales/{id}/void` (OWNER/MANAGER).
- Tests: 12 new M2 domain tests; full suite **76 passed** (64 M1 + 12 M2).

### Intentionally limited / deferred

- M1 product/sale endpoints remain unauthenticated so existing M1 tests stay green without a seed owner. Full route lock-down is a follow-up once seed/bootstrap is defined.
- No UI, no M-Pesa, no eTIMS, no hardware.
- Return type is currently the same path as void (stock restore + VOID status); finer-grained partial returns are M3+.

### Security notes

- bcrypt only; no plaintext passwords.
- Authorization is server-side via role checks on privileged endpoints.
- Cashier-facing sale/receipt schemas still omit cost/profit.
