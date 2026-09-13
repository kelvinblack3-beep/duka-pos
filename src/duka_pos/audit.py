"""Append-only audit log for Duka POS M2.

Never logs passwords, password hashes, tokens, or secrets.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AuditEntry:
    id: int
    occurred_at: str
    user_id: int | None
    action: str
    entity_type: str | None
    entity_id: int | None
    details: str | None
    client_reference: str | None


def record(
    conn: sqlite3.Connection,
    *,
    action: str,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
    client_reference: str | None = None,
) -> None:
    safe_details = None
    if details is not None:
        blocked = {"password", "password_hash", "token", "secret", "api_key"}
        cleaned = {k: v for k, v in details.items() if k.lower() not in blocked}
        safe_details = json.dumps(cleaned, default=str)
    conn.execute(
        """
        INSERT INTO audit_log (
            occurred_at, user_id, action, entity_type, entity_id, details, client_reference
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _now_iso(),
            user_id,
            action,
            entity_type,
            entity_id,
            safe_details,
            client_reference,
        ),
    )


def list_entries(
    conn: sqlite3.Connection, *, limit: int = 100, user_id: int | None = None
) -> list[AuditEntry]:
    if user_id is not None:
        rows = conn.execute(
            """
            SELECT * FROM audit_log WHERE user_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        AuditEntry(
            id=r["id"],
            occurred_at=r["occurred_at"],
            user_id=r["user_id"],
            action=r["action"],
            entity_type=r["entity_type"],
            entity_id=r["entity_id"],
            details=r["details"],
            client_reference=r["client_reference"],
        )
        for r in rows
    ]
