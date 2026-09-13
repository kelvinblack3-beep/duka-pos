"""Environment smoke tests.

These tests prove the Python package can be imported. Business logic is
now exercised by the M1 test modules (test_db.py, test_products.py,
test_sales_rice.py, etc.) — this file intentionally stays minimal.

Historical note: the original Milestone 0 version of this file asserted
that `duka_pos` contained only `__init__.py`, to prove M0 shipped no
business logic. That assertion is no longer true by design now that M1
has been implemented (see ENGINEERING_LOG.md, M1 entry) and has been
replaced with an M1-appropriate check below.
"""

from __future__ import annotations

from pathlib import Path


def test_duka_pos_package_is_importable() -> None:
    import duka_pos

    assert duka_pos.__version__ == "0.1.0"


def test_package_exposes_m1_modules() -> None:
    """M1 ships the core deterministic POS engine modules."""
    import duka_pos

    package_dir = Path(duka_pos.__file__).resolve().parent
    python_files = {path.name for path in package_dir.glob("*.py")}
    expected = {
        "__init__.py",
        "db.py",
        "money.py",
        "errors.py",
        "products.py",
        "sales.py",
        "api.py",
    }
    assert expected.issubset(python_files)
