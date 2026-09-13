# ADR-002 — Integer money and quantity

- Status: **Accepted** (architect sign-off 2026-09-13)
- Milestone: 0 (decision recorded; no money fields exist in code yet)

## Context

The first acceptance test is a weighted rice sale:

- Selling price KSh 160/kg
- Cost KSh 120/kg
- Quantity 1.35 kg
- Expected total KSh 216.00
- Expected remaining stock 48.65 kg after 50 kg opening stock
- Expected gross profit KSh 54.00

Binary floating-point (`float` / IEEE-754) cannot be trusted for persisted
currency or stock. SQLite has no true DECIMAL type: a SQLite `NUMERIC`
value is stored as integer or as float. That is a trap.

## Decision

### Money

Persist money as **integer Kenya cents**.

```
KSh 160.00 = 16000 cents
KSh 216.00 = 21600 cents
KSh 54.00  =  5400 cents
```

One shilling = 100 cents. Do not persist shillings as a fractional type.

### Quantity

Persist quantity as **integer thousandths of the product's unit**.

```
1.350 kg     = 1350 milli-kg
50.000 kg    = 50000 milli-kg
1.000 piece  = 1000 milli-piece
1.000 litre  = 1000 milli-litre
```

The unit itself (kg, litre, piece, packet, bottle, …) is metadata on the
product. The stored integer is always thousandths of that unit.

### Arithmetic

Line total in cents:

```
unit_price_cents * quantity_milli / 1000
16000 * 1350 / 1000 = 21600 cents
```

Therefore: **KSh 216.00**

Stock remaining:

```
50000 - 1350 = 48650 milli-kg
```

Therefore: **48.65 kg**

Gross profit in cents (owner/manager only; never a cashier default):

```
(16000 - 12000) * 1350 / 1000 = 5400 cents
```

Therefore: **KSh 54.00**

Division by 1000 must be exact for quantities we accept. Domain rules in a
later milestone must reject quantities that would produce a remainder, or
define rounding in a new ADR. Do not silently use float to “fix” remainders.

## Prohibition

**Floating-point arithmetic must not be used for persisted financial values
or persisted stock quantities.**

Forbidden for money/quantity storage and for the sale/stock calculations
that produce those stored values:

- Python `float`
- SQLite `REAL`
- SQLite `NUMERIC` used as a decimal
- JavaScript `Number` if a UI later displays money (format from integers)

Display layer may format integers as `KSh 216.00` or `1.35 kg`. Formatting
is not storage.

## Consequences

- Schema (when added) uses integer columns for cents and milli-quantities.
- Tests must assert integer results (`21600`, `48650`, `5400`), not floats.
- Cashiers never need cost cents; authorization must keep cost/GP off the
  till API.

## Non-claims

This ADR does not implement products, sales, or the rice test. It only
locks the representation so Milestone 1 cannot “round” its way to 216.
