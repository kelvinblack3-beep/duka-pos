"""Authentication and session management for Duka POS M2.

Passwords are hashed with bcrypt. Sessions are opaque tokens stored in
SQLite. No secrets are returned in API responses. Authentication failures
do not reveal whether a username exists.
"""

from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt

from duka_pos import db as db_module
from duka_pos.errors import AuthenticationError, DisabledUser, InvalidCredentials

SESSION_TTL_HOURS = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str
    role: str
    active: bool


def authenticate(
    conn: sqlite3.Connection, *, username: str, password: str
) -> tuple[AuthUser, str]:
    """Validate credentials and return (user, session_token).

    Raises InvalidCredentials for any failure that should look identical
    to the client (unknown user, bad password, disabled).
    """
    if not isinstance(username, str) or not username.strip():
        raise InvalidCredentials("invalid username or password")
    if not isinstance(password, str) or not password:
        raise InvalidCredentials("invalid username or password")

    row = conn.execute(
        "SELECT id, username, password_hash, role, active FROM users WHERE username = ?",
        (username.strip(),),
    ).fetchone()
    if row is None:
        raise InvalidCredentials("invalid username or password")
    if not row["active"]:
        raise InvalidCredentials("invalid username or password")
    if not verify_password(password, row["password_hash"]):
        raise InvalidCredentials("invalid username or password")

    token = secrets.token_urlsafe(32)
    now = _now()
    expires = now + timedelta(hours=SESSION_TTL_HOURS)
    with db_module.transaction(conn):
        conn.execute(
            """
            INSERT INTO sessions (token, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token, row["id"], now.isoformat(), expires.isoformat()),
        )
    user = AuthUser(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        active=bool(row["active"]),
    )
    return user, token


def get_user_for_token(conn: sqlite3.Connection, token: str) -> AuthUser:
    if not token:
        raise AuthenticationError("authentication required")
    row = conn.execute(
        """
        SELECT u.id, u.username, u.role, u.active, s.expires_at
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = ?
        """,
        (token,),
    ).fetchone()
    if row is None:
        raise AuthenticationError("authentication required")
    if row["expires_at"] < _now_iso():
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        raise AuthenticationError("authentication required")
    if not row["active"]:
        raise DisabledUser("user is disabled")
    return AuthUser(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        active=bool(row["active"]),
    )


def logout(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
