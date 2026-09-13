from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from duka_pos import db as db_module


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """A fresh, isolated, schema-initialized SQLite connection per test."""
    db_path = tmp_path / "duka_pos_test.sqlite"
    connection = db_module.connect_and_init(db_path)
    yield connection
    connection.close()
