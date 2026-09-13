# ADR-003: Payment provider abstraction and pending-payment stock rule

**Status:** Accepted  
**Date:** 2026-09-13  
**Milestone:** M3.1

## Context

M1/M2 implement cash-only sales: one SQLite transaction creates the sale,
CONFIRMED payment, stock deduction, and receipt. M-Pesa is asynchronous
(STK Push → callback). The payments table already modelled richer statuses
and methods, but the domain rejected non-cash methods.

## Decision

### 1. Payment provider abstraction

Providers are adapters outside the core sales domain:

```
PaymentProvider
├── CashProvider          (M3.1 — immediate, no network)
└── MpesaDarajaProvider   (M3.2 — not implemented here)
```

Provider-specific HTTP, credentials, and callback verification live only
in provider modules. Domain code owns persistence and state transitions.

### 2. Pending M-Pesa does not deduct stock

When a sale is created with `payment_method=MPESA`:

- sale status = `PENDING_PAYMENT`
- payment status = `PENDING`
- sale lines are recorded (historical prices/costs stamped)
- **stock is not deducted**
- **stock is not reserved**
- **no receipt is created**

Stock is deducted only when payment becomes `CONFIRMED`.
A pending sale may request more quantity than is currently available;
confirmation then fails with `InsufficientStock` and leaves the sale
pending. That is intentional (no false reservations for abandoned STK).

Pending MPESA rows store `provider = DARAJA` as the future adapter
identity only. Cash uses `LOCAL_CASH`. M3.1 does not implement Daraja HTTP.

Confirmation is a domain operation for trusted provider/reconciliation
handlers only — not a cashier/public force-confirm API.

### 3. Confirmed-payment finalization is atomic

`payments.confirm_payment_and_complete_sale` runs in **one** SQLite
transaction. ``expected_amount_cents`` is **mandatory** and must equal
``payment.amount_cents`` (provider amount == local amount). There is no
payment_id-only confirm path.

1. Verify payment is PENDING (or already CONFIRMED → idempotent)
2. Verify mandatory amount equality / sale is PENDING_PAYMENT
3. payment → CONFIRMED
4. sale → COMPLETED
5. stock SALE movements + balance updates
6. receipt
7. audit

On any failure: full rollback. Duplicate confirmation with matching data
is idempotent (one stock deduction, one receipt).

### 4. No network calls inside SQLite transactions

Unchanged from `db.transaction` contract. Daraja HTTP (M3.2) occurs only
after the local pending record is committed, never inside the write
transaction that creates or confirms it.

## Consequences

- Cash path behaviour and M1 rice acceptance values are unchanged.
- Abandoned STK attempts do not require stock restoration.
- Confirmation may still fail with `InsufficientStock` if inventory moved
  between pending create and confirm; that leaves the sale pending.
- Shifts continue to count only `CASH` + `CONFIRMED` toward expected drawer cash.
- M3.1 does **not** implement Daraja, STK Push, callbacks, or eTIMS.

## Non-claims

This ADR does not implement Safaricom Daraja integration. M3.2 remains pending.
