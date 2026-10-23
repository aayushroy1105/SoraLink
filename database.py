
"""SQLite initialization, connection management, and transactions."""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "instance" / "soralink.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def get_db_path() -> Path:
    """Return the configured database path."""
    configured_path = os.environ.get("SORALINK_DB_PATH")
    return Path(configured_path).expanduser() if configured_path else DEFAULT_DB_PATH


def get_connection() -> sqlite3.Connection:
    """Create a configured SQLite connection."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        str(db_path),
        timeout=20.0,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 20000")
    return connection


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """Yield a connection and always close it."""
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


def init_db() -> None:
    """Enable WAL mode and create tables and indexes from schema.sql."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if not SCHEMA_PATH.is_file():
        raise FileNotFoundError(f"Database schema not found: {SCHEMA_PATH}")

    connection = get_connection()
    try:
        # journal_mode cannot be changed inside a transaction.
        connection.execute("PRAGMA journal_mode = WAL")
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        connection.executescript(schema)
        # Ensure backwards-compatible column pa_card_id exists on active_broadcasts
        cursor = connection.execute("PRAGMA table_info(active_broadcasts)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "pa_card_id" not in columns:
            connection.execute("ALTER TABLE active_broadcasts ADD COLUMN pa_card_id TEXT")

        # Ensure backwards-compatible column request_id exists on voice_previews
        cursor = connection.execute("PRAGMA table_info(voice_previews)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "request_id" not in columns:
            connection.execute("ALTER TABLE voice_previews ADD COLUMN request_id TEXT")
    finally:
        connection.close()


@contextmanager
def transaction(
    connection: sqlite3.Connection,
) -> Iterator[sqlite3.Connection]:
    """Run statements atomically, rolling back if an error occurs."""
    connection.execute("BEGIN")
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


def now_ms() -> int:
    """Return the current UTC Unix timestamp in milliseconds."""
    return time.time_ns() // 1_000_000
