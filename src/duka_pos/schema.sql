-- Duka POS M1 schema.
--
-- All money columns are integer KES cents. All quantity columns are
-- integer thousandths of the product's unit. See ADR-002.
--
-- This schema is applied idempotently via `CREATE TABLE IF NOT EXISTS`,
-- which is sufficient for the single-file M1 migration mechanism. A
-- versioned migration tool can be introduced in a later milestone if the
-- schema needs to evolve after real shop data exists.

CREATE TABLE IF NOT EXISTS products (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT NOT NULL,
    barcode              TEXT UNIQUE,
    unit                 TEXT NOT NULL CHECK (unit IN (
                             'kg', 'g', 'litre', 'ml', 'piece',
                             'packet', 'bottle', 'box', 'carton'
                         )),
    cost_price_cents     INTEGER NOT NULL CHECK (cost_price_cents >= 0),
    selling_price_cents  INTEGER NOT NULL CHECK (selling_price_cents >= 0),
    active               INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_balances (
    product_id     INTEGER PRIMARY KEY REFERENCES products (id),
    quantity_milli INTEGER NOT NULL DEFAULT 0 CHECK (quantity_milli >= 0)
);

-- Immutable stock movement ledger. Every stock change is traceable here.
-- quantity_milli is signed: positive for receiving/adding stock, negative
-- for sales/deductions.
CREATE TABLE IF NOT EXISTS stock_movements (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id       INTEGER NOT NULL REFERENCES products (id),
    movement_type    TEXT NOT NULL CHECK (movement_type IN (
                          'RECEIVE', 'SALE', 'ADJUSTMENT', 'REVERSAL'
                      )),
    quantity_milli   INTEGER NOT NULL,
    unit_cost_cents  INTEGER,
    reference_type   TEXT,
    reference_id     INTEGER,
    occurred_at      TEXT NOT NULL,
    user_id          INTEGER,
    reversal_of      INTEGER REFERENCES stock_movements (id)
);

CREATE INDEX IF NOT EXISTS idx_stock_movements_product
    ON stock_movements (product_id);

-- client_reference is the idempotency key: submitting the same reference
-- twice must not create a second sale, deduct stock twice, or pay twice.
CREATE TABLE IF NOT EXISTS sales (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    client_reference  TEXT NOT NULL UNIQUE,
    status            TEXT NOT NULL DEFAULT 'COMPLETED' CHECK (status IN (
                          'COMPLETED', 'VOID'
                      )),
    subtotal_cents    INTEGER NOT NULL CHECK (subtotal_cents >= 0),
    total_cents       INTEGER NOT NULL CHECK (total_cents >= 0),
    created_at        TEXT NOT NULL
);

-- Sale lines preserve price and cost AT THE TIME OF SALE. Later product
-- price changes must never alter historical sales.
CREATE TABLE IF NOT EXISTS sale_lines (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id            INTEGER NOT NULL REFERENCES sales (id),
    product_id         INTEGER NOT NULL REFERENCES products (id),
    quantity_milli     INTEGER NOT NULL CHECK (quantity_milli > 0),
    unit_price_cents   INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    unit_cost_cents    INTEGER NOT NULL CHECK (unit_cost_cents >= 0),
    line_total_cents   INTEGER NOT NULL CHECK (line_total_cents >= 0)
);

CREATE INDEX IF NOT EXISTS idx_sale_lines_sale ON sale_lines (sale_id);

-- CASH is CONFIRMED immediately in M1. MPESA/CARD/OTHER are modelled for
-- future adapters but are rejected by the domain layer in M1 — no fake
-- M-Pesa is implemented. See errors.UnsupportedPaymentMethod.
CREATE TABLE IF NOT EXISTS payments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id        INTEGER NOT NULL REFERENCES sales (id),
    method         TEXT NOT NULL CHECK (method IN ('CASH', 'MPESA', 'CARD', 'OTHER')),
    status         TEXT NOT NULL CHECK (status IN (
                       'INITIATED', 'PENDING', 'CONFIRMED', 'FAILED',
                       'CANCELLED', 'REVERSED', 'REFUNDED'
                   )),
    amount_cents   INTEGER NOT NULL CHECK (amount_cents >= 0),
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_payments_sale ON payments (sale_id);

CREATE TABLE IF NOT EXISTS receipts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id          INTEGER NOT NULL UNIQUE REFERENCES sales (id),
    receipt_number   TEXT NOT NULL UNIQUE,
    created_at       TEXT NOT NULL
);
