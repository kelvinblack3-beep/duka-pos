# ADR-001 — SQLite as the local source of truth

- Status: **Accepted** (architect sign-off 2026-09-13)
- Milestone: 0 (decision recorded; database not created yet)

## Context

Duka POS must keep a Kenyan mini-mart selling when the internet is down. The
shop computer is the primary system of record. The shop must be able to move
the whole POS — application, data, configuration — to another compatible
computer. Docker and cloud hosting must not be mandatory.

KIFAA uses Postgres for a payment orchestration platform. That choice is
correct for KIFAA and **wrong** to copy here. This repository is independent.

## Decision

Use **SQLite** as the local source of truth for Duka POS.

The canonical database is a file on the shop computer (planned path:
`data/duka_pos.sqlite`, configurable). Core till operations read and write
that file only.

When the database is introduced, the application must:

1. Enable **foreign keys** on every connection (`PRAGMA foreign_keys = ON`).
2. Use **WAL** journal mode (`PRAGMA journal_mode = WAL`) so a cashier
   session and a manager session can read concurrently without pretending
   this is a multi-writer cluster.
3. Write sale + stock + payment changes in a **single transaction**. A
   crash mid-sale must not leave stock deducted without a sale, or a sale
   without stock movement.

Backup of shop data is, at minimum, a consistent copy of that file (and
WAL/SHM companions if the process is running — later milestones must
document a safe backup procedure). That procedure is **PLANNED**, not
implemented.

## Why SQLite for a single-shop POS

- Works offline with no database server to install or keep running
- One file to copy for migration and disaster recovery
- No cloud account, no Frappe Cloud, no hosted Postgres as source of truth
- Suitable for one dedicated shop PC and, later, a small number of LAN
  clients talking to that same process
- Transactions and foreign keys are enough for the first vertical slice

## Consequences

- Do not point `DUKA_POS_DATABASE_PATH` at a cloud database.
- Do not make Postgres, MySQL, or Docker a requirement for the shop till.
- Postgres may be re-evaluated only with a new ADR if a genuinely different
  deployment (many concurrent writers, central multi-branch) is approved.
- SQLite `NUMERIC` / `REAL` must not be used for money or quantity. See
  ADR-002. Store integers.

## Non-claims

This ADR does not claim:

- that SQLite has been load-tested for this POS (no schema exists yet)
- that SQLite will scale to a supermarket chain
- that backup/restore is production-ready
- that multi-terminal contention has been measured

Those require implementation and tests in later milestones.
