"""Milestone 0 environment smoke tests.

These tests prove the Python package can be imported.
They do not exercise POS business logic — none exists yet.
"""

from __future__ import annotations

from pathlib import Path


def test_duka_pos_package_is_importable() -> None:
    import duka_pos

    assert duka_pos.__version__ == "0.0.1"


def test_package_is_foundation_only() -> None:
    """M0 must not ship sales, inventory, or payment modules."""
    import duka_pos

    package_dir = Path(duka_pos.__file__).resolve().parent
    python_files = sorted(path.name for path in package_dir.glob("*.py"))
    assert python_files == ["__init__.py"]
