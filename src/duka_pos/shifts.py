"""Cashier shift lifecycle for Duka POS M2.

A user may have at most one OPEN shift. Expected cash is computed from
local CASH payments linked to the shift.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from duka_pos import db as db_module
from duka_pos.errors import (
    NoOpenShift,
    PermissionDenied,
    ShiftAlreadyClosed,
    ShiftAlreadyOpen,
    ShiftNotFound,
)
from duka_pos.money import validate_money_cents


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Shift:
    id: int
    user_id: int
    opened_at: str
    closed_at: str | None
    opening_cash_cents: int
    closing_cash_cents: int | None
    expected_cash_cents: int | None
    variance_cents: int | None
    status: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Shift":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            opened_at=row["opened_at"],
            closed_at=row["closed_at"],
            opening_cash_cents=row["opening_cash_cents"],
            closing_cash_cents=row["closing_cash_cents"],
            expected_cash_cents=row["expected_cash_cents"],
            variance_cents=row["variance_cents"],
            status=row["status"],
        )


def get_open_shift_for_user(conn: sqlite3.Connection, user_id: int) -> Shift | None:
    row = conn.execute(
        "SELECT * FROM shifts WHERE user_id = ? AND status = 'OPEN' ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    return Shift.from_row(row) if row else None


def open_shift(
    conn: sqlite3.Connection, *, user_id: int, opening_cash_cents: int
) -> Shift:
    validate_money_cents(opening_cash_cents, field="opening_cash_cents")
    existing = get_open_shift_for_user(conn, user_id)
    if existing is not None:
        raise ShiftAlreadyOpen(f"user {user_id} already has open shift {existing.id}")

    now = _now_iso()
    with db_module.transaction(conn):
        cursor = conn.execute(
            """
            INSERT INTO shifts (
                user_id, opened_at, closed_at, opening_cash_cents,
                closing_cash_cents, expected_cash_cents, variance_cents, status
            ) VALUES (?, ?, NULL, ?, NULL, NULL, NULL, 'OPEN')
            """,
            (user_id, now, opening_cash_cents),
        )
        shift_id = cursor.lastrowid
    return get_shift(conn, shift_id)


def get_shift(conn: sqlite3.Connection, shift_id: int) -> Shift:
    row = conn.execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()
    if row is None:
        raise ShiftNotFound(f"shift {shift_id} not found")
    return Shift.from_row(row)


def _compute_expected_cash(conn: sqlite3.Connection, shift: Shift) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(p.amount_cents), 0) AS total
        FROM payments p
        JOIN sales s ON s.id = p.sale_id
        WHERE p.method = 'CASH'
          AND p.status = 'CONFIRMED'
          AND s.status = 'COMPLETED'
          AND (
                s.shift_id = ?
             OR (s.shift_id IS NULL AND s.created_at >= ? AND s.created_at <= ?)
          )
        """,
        (shift.id, shift.opened_at, _now_iso()),
    ).fetchone()
    return int(row["total"]) + shift.opening_cash_cents


def close_shift(
    conn: sqlite3.Connection,
    *,
    shift_id: int,
    closing_cash_cents: int,
    acting_user_id: int,
    allow_manager: bool = False,
) -> Shift:
    validate_money_cents(closing_cash_cents, field="closing_cash_cents")
    shift = get_shift(conn, shift_id)
    if shift.status != "OPEN":
        raise ShiftAlreadyClosed(f"shift {shift_id} is already closed")
    if shift.user_id != acting_user_id and not allow_manager:
        raise PermissionDenied("cannot close another user's shift")

    expected = _compute_expected_cash(conn, shift)
    variance = closing_cash_cents - expected
    now = _now_iso()
    with db_module.transaction(conn):
        conn.execute(
            """
            UPDATE shifts
            SET closed_at = ?,
                closing_cash_cents = ?,
                expected_cash_cents = ?,
                variance_cents = ?,
                status = 'CLOSED'
            WHERE id = ? AND status = 'OPEN'
            """,
            (now, closing_cash_cents, expected, variance, shift_id),
        )
    return get_shift(conn, shift_id)


def list_shifts(
    conn: sqlite3.Connection, *, user_id: int | None = None
) -> list[Shift]:
    if user_id is not None:
        rows = conn.execute(
            "SELECT * FROM shifts WHERE user_id = ? ORDER BY id DESC", (user_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM shifts ORDER BY id DESC").fetchall()
    return [Shift.from_row(r) for r in rows]
