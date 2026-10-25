"""Database initialization and offline readiness tests.

Validates clean SQLite database initialization (DB-01), connection PRAGMAs,
table and index existence, demo invitation seeding, and path configuration
isolation without touching the developer's development database.
"""

from __future__ import annotations

import importlib
import os
import sqlite3
from pathlib import Path

import pytest

import config
import database
from database import get_connection, get_db_path, init_db
from seed_db import DEMO_INVITES, seed_seat_invites


def test_default_database_paths_agree(monkeypatch: pytest.MonkeyPatch):
    """Verify default database paths in config.py and database.py match instance/soralink.db."""
    monkeypatch.delenv("SORALINK_DB_PATH", raising=False)
    monkeypatch.delenv("SORALINK_TEST_DB_PATH", raising=False)
    importlib.reload(config)

    expected_prod_path = database.BASE_DIR / "instance" / "soralink.db"
    expected_test_path = database.BASE_DIR / "instance" / "soralink-test.db"

    assert database.DEFAULT_DB_PATH == expected_prod_path
    assert get_db_path() == expected_prod_path

    # Reload/inspect config defaults without env overrides
    prod_config = config.Config
    test_config = config.TestConfig

    assert prod_config.DATABASE_PATH == expected_prod_path
    assert test_config.DATABASE_PATH == expected_test_path


def test_database_path_environment_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Verify SORALINK_DB_PATH and SORALINK_TEST_DB_PATH override defaults correctly."""
    custom_db = tmp_path / "custom" / "soralink.db"
    monkeypatch.setenv("SORALINK_DB_PATH", str(custom_db))
    monkeypatch.delenv("SORALINK_TEST_DB_PATH", raising=False)
    importlib.reload(config)

    assert get_db_path() == custom_db
    assert config.get_config("development").DATABASE_PATH == custom_db
    # TestConfig falls back to SORALINK_DB_PATH if SORALINK_TEST_DB_PATH is unset
    assert config.get_config("test").DATABASE_PATH == custom_db

    # Explicit SORALINK_TEST_DB_PATH takes precedence for test configuration
    custom_test_db = tmp_path / "custom" / "test.db"
    monkeypatch.setenv("SORALINK_TEST_DB_PATH", str(custom_test_db))
    importlib.reload(config)
    assert config.get_config("test").DATABASE_PATH == custom_test_db


def test_clean_database_initialization(isolated_db_path: Path):
    """DB-01: Verify fresh initialization creates all canonical tables and indexes."""
    assert not isolated_db_path.exists(), "Test database must not exist before initialization"

    # Initialize from schema.sql
    init_db()

    assert isolated_db_path.is_file(), "Database file must exist after init_db()"

    connection = get_connection()
    try:
        # Check all 6 canonical tables exist
        cursor = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = {row["name"] for row in cursor.fetchall()}

        expected_tables = {
            "seat_invites",
            "sessions",
            "requests",
            "request_events",
            "voice_previews",
            "active_broadcasts",
        }
        missing_tables = expected_tables - table_names
        assert not missing_tables, f"Missing canonical tables: {missing_tables}"

        # Check key performance and integrity indexes exist
        cursor = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        index_names = {row["name"] for row in cursor.fetchall()}

        expected_indexes = {
            "idx_sessions_expiry",
            "idx_requests_queue",
            "idx_requests_passenger",
            "idx_requests_seat",
            "idx_requests_no_active_duplicate",
            "idx_request_events_history",
            "idx_voice_previews_expiry",
            "idx_broadcasts_active",
        }
        missing_indexes = expected_indexes - index_names
        assert not missing_indexes, f"Missing required indexes: {missing_indexes}"

    finally:
        connection.close()


def test_database_connection_pragmas(db_connection: sqlite3.Connection):
    """Verify SQLite WAL mode, foreign-key enforcement, and busy timeout."""
    # Foreign keys must be active on each connection
    fk_status = db_connection.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk_status == 1, "Foreign keys must be enabled on every connection"

    # Busy timeout must be 20 seconds (20,000 ms)
    busy_timeout = db_connection.execute("PRAGMA busy_timeout").fetchone()[0]
    assert busy_timeout == 20000, "PRAGMA busy_timeout must be set to 20000ms"

    # Journal mode must be WAL
    journal_mode = db_connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal_mode.lower() == "wal", f"Expected WAL journal mode, got {journal_mode}"


def test_demo_database_seeding(initialized_db: Path, db_connection: sqlite3.Connection):
    """Verify demo seat invitation seeding inserts expected seats and is idempotent."""
    cursor = db_connection.execute("SELECT COUNT(*) FROM seat_invites")
    initial_count = cursor.fetchone()[0]
    assert initial_count == 0, "Clean database must start with zero seat invites"

    # Seed demo seats
    count = seed_seat_invites()
    assert count == len(DEMO_INVITES)

    cursor = db_connection.execute("SELECT seat_label, is_active FROM seat_invites ORDER BY seat_label")
    rows = cursor.fetchall()
    seeded_seats = {row["seat_label"]: row["is_active"] for row in rows}

    for seat in DEMO_INVITES:
        assert seat in seeded_seats, f"Demo seat {seat} was not seeded"
        assert seeded_seats[seat] == 1, f"Demo seat {seat} must be active"

    # Re-running seed must be idempotent and not raise IntegrityError
    count_second = seed_seat_invites()
    assert count_second == len(DEMO_INVITES)

    cursor = db_connection.execute("SELECT COUNT(*) FROM seat_invites")
    assert cursor.fetchone()[0] == len(DEMO_INVITES), "Seeding again must not create duplicate seat records"


def test_test_isolation_does_not_touch_production_database(isolated_db_path: Path):
    """Verify that isolated test run does not modify or point to the production database path."""
    current_path = get_db_path()
    assert current_path == isolated_db_path
    assert current_path != database.DEFAULT_DB_PATH
    assert "soralink_test.db" in str(current_path)
