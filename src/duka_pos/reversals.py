"""Sale void / return (reversal) for Duka POS M2.

Historical sales are never deleted. A single reversal record is created;
stock is restored via REVERSAL movements; payment is marked REVERSED;
sale status becomes VOID. Fully atomic.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from duka_pos import audit as audit_module
from duka_pos import db as db_module
from duka_pos.errors import (
    InvalidReversal,
    SaleAlreadyReversed,
    SaleNotFound,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Reversal:
    id: int
    sale_id: int
    reversal_type: str
    reason: str | None
    performed_by: int
    performed_at: str


def void_sale(
    conn: sqlite3.Connection,
    *,
    sale_id: int,
    performed_by: int,
    reason: str | None = None,
    reversal_type: str = "VOID",
) -> Reversal:
    if reversal_type not in ("VOID", "RETURN"):
        raise InvalidReversal(f"unsupported reversal_type {reversal_type!r}")

    sale_row = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if sale_row is None:
        raise SaleNotFound(f"sale {sale_id} not found")

    existing = conn.execute(
        "SELECT id FROM sale_reversals WHERE sale_id = ?", (sale_id,)
    ).fetchone()
    if existing is not None or sale_row["status"] == "VOID":
        raise SaleAlreadyReversed(f"sale {sale_id} has already been reversed")

    prior_status = sale_row["status"]
    # PENDING_PAYMENT never deducted stock; COMPLETED did.
    restore_stock = prior_status == "COMPLETED"

    now = _now_iso()
    with db_module.transaction(conn):
        if restore_stock:
            lines = conn.execute(
                "SELECT * FROM sale_lines WHERE sale_id = ?", (sale_id,)
            ).fetchall()
            for line in lines:
                qty = line["quantity_milli"]
                conn.execute(
                    """
                    UPDATE stock_balances
                    SET quantity_milli = quantity_milli + ?
                    WHERE product_id = ?
                    """,
                    (qty, line["product_id"]),
                )
                conn.execute(
                    """
                    INSERT INTO stock_movements (
                        product_id, movement_type, quantity_milli, unit_cost_cents,
                        reference_type, reference_id, occurred_at, user_id
                    ) VALUES (?, 'REVERSAL', ?, ?, 'SALE', ?, ?, ?)
                    """,
                    (
                        line["product_id"],
                        qty,
                        line["unit_cost_cents"],
                        sale_id,
                        now,
                        performed_by,
                    ),
                )

        # Confirmed → REVERSED; pending/initiated → CANCELLED.
        conn.execute(
            """
            UPDATE payments SET status = 'REVERSED', updated_at = ?
            WHERE sale_id = ? AND status = 'CONFIRMED'
            """,
            (now, sale_id),
        )
        conn.execute(
            """
            UPDATE payments SET status = 'CANCELLED', updated_at = ?
            WHERE sale_id = ? AND status IN ('PENDING', 'INITIATED')
            """,
            (now, sale_id),
        )

        # Mark sale VOID (original totals preserved).
        conn.execute(
            "UPDATE sales SET status = 'VOID' WHERE id = ?", (sale_id,)
        )

        cursor = conn.execute(
            """
            INSERT INTO sale_reversals (
                sale_id, reversal_type, reason, performed_by, performed_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (sale_id, reversal_type, reason, performed_by, now),
        )
        reversal_id = cursor.lastrowid

        audit_module.record(
            conn,
            action=f"sale.{reversal_type.lower()}",
            user_id=performed_by,
            entity_type="sale",
            entity_id=sale_id,
            details={"reversal_id": reversal_id, "reason": reason},
        )

    row = conn.execute(
        "SELECT * FROM sale_reversals WHERE id = ?", (reversal_id,)
    ).fetchone()
    return Reversal(
        id=row["id"],
        sale_id=row["sale_id"],
        reversal_type=row["reversal_type"],
        reason=row["reason"],
        performed_by=row["performed_by"],
        performed_at=row["performed_at"],
    )
