"""Pytest fixtures for SoraLink tests.

Provides isolated test database configuration and application test client.
Tests run against temporary SQLite databases and never mutate instance/soralink.db.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Generator

import pytest

# Ensure repository root is in sys.path when invoked via `pytest` directly.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config
from database import get_connection, init_db
from seed_db import seed_seat_invites


@pytest.fixture
def isolated_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """Set up an isolated SQLite database path for a test.

    Ensures SORALINK_DB_PATH points to a temporary file unique to each test,
    preventing any test from reading or modifying the development database
    at instance/soralink.db.
    """
    db_file = tmp_path / "soralink_test.db"
    monkeypatch.setenv("SORALINK_DB_PATH", str(db_file))
    monkeypatch.setenv("SORALINK_TEST_DB_PATH", str(db_file))
    importlib.reload(config)
    try:
        yield db_file
    finally:
        importlib.reload(config)


@pytest.fixture
def initialized_db(isolated_db_path: Path) -> Path:
    """Initialize schema tables and indexes in the isolated database."""
    init_db()
    return isolated_db_path


@pytest.fixture
def seeded_db(initialized_db: Path) -> Path:
    """Seed demo seat invitations into the isolated test database."""
    seed_seat_invites()
    return initialized_db


@pytest.fixture
def db_connection(initialized_db: Path) -> Generator:
    """Yield a SQLite connection to the isolated test database and ensure it is closed."""
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def app(seeded_db: Path):
    """Create a Flask test application instance bound to the isolated database."""
    from app import create_app

    test_app = create_app("test")
    test_app.config["TESTING"] = True
    return test_app


@pytest.fixture
def client(app):
    """Provide a test client for the test application."""
    return app.test_client()
