# Architecture — Duka POS

Status: **PLANNED** application architecture, with Milestone 0–3.1 foundation
**IMPLEMENTED** where noted.

## Shape

Local-first **modular monolith** on the shop computer. One process. One
SQLite file. Integrations as optional adapters.

## Money and quantity

- Money: integer Kenya cents. `KSh 160.00` = `16000`
- Quantity: integer thousandths. `1.350 kg` = `1350`

Rice example:

```
line total  = 16000 * 1350 / 1000 = 21600 cents = KSh 216.00
stock left  = 50000 - 1350        = 48650 milli-kg = 48.65 kg
gross profit = (16000 - 12000) * 1350 / 1000 = 5400 cents = KSh 54.00
```

## Sale path

Cash:

```
SELL → COMPLETED + CONFIRMED + stock + receipt (one SQLite transaction)
```

M-Pesa (M3.1 local foundation; Daraja is M3.2):

```
LOCAL SALE RECORD (status=PENDING_PAYMENT)
  → payment PENDING, provider=DARAJA (identity only)
  → NO stock deduction, NO reservation, NO receipt
  → [M3.2] Daraja adapter outside SQLite transaction
  → confirm_payment_and_complete_sale(
        expected_amount_cents=…  # mandatory
      )
  → atomic: CONFIRMED + stock + receipt + COMPLETED
```

Pending M-Pesa does **not** deduct stock. Confirmation requires mandatory
amount equality. There is no cashier force-confirm API.

See [ADR-003](docs/decisions/ADR-003-payment-abstraction-and-pending-stock.md).

## What this architecture is not

- Not microservices
- Not Docker-mandatory
- Not a live Daraja integration (M3.2 not implemented)
- Not eTIMS
- Not a fake M-Pesa network path
