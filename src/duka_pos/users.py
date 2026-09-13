"""User management for Duka POS M2.

Roles: OWNER, MANAGER, CASHIER.
Password hashes only; never plaintext.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from duka_pos import auth as auth_module
from duka_pos import db as db_module
from duka_pos.errors import DuplicateUsername, InvalidProductData, PermissionDenied, UserNotFound

ROLES = frozenset({"OWNER", "MANAGER", "CASHIER"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: str
    active: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "User":
        return cls(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            active=bool(row["active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def create_user(
    conn: sqlite3.Connection,
    *,
    username: str,
    password: str,
    role: str,
    active: bool = True,
) -> User:
    if not isinstance(username, str) or not username.strip():
        raise InvalidProductData("username must be a non-empty string")
    if role not in ROLES:
        raise InvalidProductData(f"role must be one of {sorted(ROLES)}")
    if not isinstance(password, str) or len(password) < 8:
        raise InvalidProductData("password must be at least 8 characters")

    password_hash = auth_module.hash_password(password)
    now = _now_iso()
    with db_module.transaction(conn):
        try:
            cursor = conn.execute(
                """
                INSERT INTO users (username, password_hash, role, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (username.strip(), password_hash, role, 1 if active else 0, now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateUsername(f"username {username!r} already exists") from exc
        user_id = cursor.lastrowid
    return get_user(conn, user_id)


def get_user(conn: sqlite3.Connection, user_id: int) -> User:
    row = conn.execute(
        "SELECT id, username, role, active, created_at, updated_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        raise UserNotFound(f"user {user_id} not found")
    return User.from_row(row)


def list_users(conn: sqlite3.Connection) -> list[User]:
    rows = conn.execute(
        "SELECT id, username, role, active, created_at, updated_at FROM users ORDER BY id"
    ).fetchall()
    return [User.from_row(r) for r in rows]


def set_user_active(conn: sqlite3.Connection, user_id: int, *, active: bool) -> User:
    get_user(conn, user_id)
    now = _now_iso()
    with db_module.transaction(conn):
        conn.execute(
            "UPDATE users SET active = ?, updated_at = ? WHERE id = ?",
            (1 if active else 0, now, user_id),
        )
        if not active:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return get_user(conn, user_id)


def set_user_role(conn: sqlite3.Connection, user_id: int, *, role: str) -> User:
    if role not in ROLES:
        raise InvalidProductData(f"role must be one of {sorted(ROLES)}")
    get_user(conn, user_id)
    now = _now_iso()
    with db_module.transaction(conn):
        conn.execute(
            "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
            (role, now, user_id),
        )
    return get_user(conn, user_id)


def require_role(user: auth_module.AuthUser, *allowed: str) -> None:
    if user.role not in allowed:
        raise PermissionDenied(
            f"role {user.role!r} is not permitted; requires one of {list(allowed)}"
        )
