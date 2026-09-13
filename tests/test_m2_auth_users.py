"""M2 authentication and user management tests."""

from __future__ import annotations

import sqlite3

import pytest

from duka_pos import auth as auth_module
from duka_pos import users as users_module
from duka_pos.errors import (
    DuplicateUsername,
    InvalidCredentials,
    PermissionDenied,
    UserNotFound,
)


def test_create_and_authenticate_user(conn: sqlite3.Connection) -> None:
    user = users_module.create_user(
        conn, username="owner1", password="securepass1", role="OWNER"
    )
    assert user.username == "owner1"
    assert user.role == "OWNER"
    assert user.active is True

    auth_user, token = auth_module.authenticate(
        conn, username="owner1", password="securepass1"
    )
    assert auth_user.id == user.id
    assert token
    loaded = auth_module.get_user_for_token(conn, token)
    assert loaded.id == user.id


def test_invalid_password_rejected(conn: sqlite3.Connection) -> None:
    users_module.create_user(
        conn, username="cashier1", password="securepass1", role="CASHIER"
    )
    with pytest.raises(InvalidCredentials):
        auth_module.authenticate(conn, username="cashier1", password="wrong")


def test_unknown_username_rejected(conn: sqlite3.Connection) -> None:
    with pytest.raises(InvalidCredentials):
        auth_module.authenticate(conn, username="nobody", password="whatever12")


def test_disabled_user_cannot_login(conn: sqlite3.Connection) -> None:
    user = users_module.create_user(
        conn, username="disabled1", password="securepass1", role="CASHIER"
    )
    users_module.set_user_active(conn, user.id, active=False)
    with pytest.raises(InvalidCredentials):
        auth_module.authenticate(conn, username="disabled1", password="securepass1")


def test_duplicate_username_rejected(conn: sqlite3.Connection) -> None:
    users_module.create_user(
        conn, username="dup", password="securepass1", role="CASHIER"
    )
    with pytest.raises(DuplicateUsername):
        users_module.create_user(
            conn, username="dup", password="securepass2", role="MANAGER"
        )


def test_password_hash_not_plaintext(conn: sqlite3.Connection) -> None:
    users_module.create_user(
        conn, username="hashcheck", password="securepass1", role="OWNER"
    )
    row = conn.execute(
        "SELECT password_hash FROM users WHERE username = ?", ("hashcheck",)
    ).fetchone()
    assert row["password_hash"] != "securepass1"
    assert row["password_hash"].startswith("$2")  # bcrypt


def test_require_role(conn: sqlite3.Connection) -> None:
    user = users_module.create_user(
        conn, username="c1", password="securepass1", role="CASHIER"
    )
    auth_user, _ = auth_module.authenticate(
        conn, username="c1", password="securepass1"
    )
    with pytest.raises(PermissionDenied):
        users_module.require_role(auth_user, "OWNER", "MANAGER")
    users_module.require_role(auth_user, "CASHIER")  # must not raise
