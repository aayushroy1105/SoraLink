
"""Persistent PA announcement lifecycle."""

from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any

from database import get_db, transaction


DEFAULT_TTL_SECONDS = 120
MAX_TTL_SECONDS = 30 * 60


class BroadcastServiceError(Exception):
    """Base exception for PA broadcast failures."""


class BroadcastNotFoundError(BroadcastServiceError):
    """Raised when an announcement does not exist."""


class InvalidBroadcastError(BroadcastServiceError):
    """Raised when announcement input is invalid."""


class BroadcastAuthorizationError(BroadcastServiceError):
    """Raised when the caller is not authenticated crew."""


def now_ms() -> int:
    """Return the current UTC Unix timestamp in milliseconds."""
    return time.time_ns() // 1_000_000


def _require_crew(session: dict[str, Any]) -> str:
    """Return a crew session ID after checking the authenticated role."""
    if not isinstance(session, dict) or session.get("role") != "crew":
        raise BroadcastAuthorizationError("Crew authorization is required")

    session_id = session.get("id")
    if not isinstance(session_id, str) or not session_id:
        raise BroadcastAuthorizationError("Invalid crew session")

    return session_id


def _validate_text(
    value: Any,
    field_name: str,
    max_length: int,
) -> str:
    if not isinstance(value, str):
        raise InvalidBroadcastError(f"{field_name} must be text")

    value = value.strip()

    if not value:
        raise InvalidBroadcastError(f"{field_name} is required")

    if len(value) > max_length:
        raise InvalidBroadcastError(
            f"{field_name} must be at most {max_length} characters"
        )

    return value


def _broadcast_from_row(
    row: sqlite3.Row | dict[str, Any],
) -> dict[str, Any]:
    return dict(row)


def create_broadcast(
    crew_session: dict[str, Any],
    *,
    title: str,
    body: str,
    category: str = "general",
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    """Persist a crew announcement with a bounded expiration time."""
    crew_id = _require_crew(crew_session)

    title = _validate_text(title, "title", 100)
    body = _validate_text(body, "body", 1000)
    category = _validate_text(category, "category", 40)

    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise InvalidBroadcastError("ttl_seconds must be an integer")

    if not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
        raise InvalidBroadcastError(
            f"ttl_seconds must be between 1 and {MAX_TTL_SECONDS}"
        )

    timestamp = now_ms()
    expires_at = timestamp + ttl_seconds * 1000
    broadcast_id = str(uuid.uuid4())

    with get_db() as connection:
        with transaction(connection):
            # Ensure the crew session still exists and is active.
            active_session = connection.execute(
                """
                SELECT id
                FROM sessions
                WHERE id = ?
                  AND role = 'crew'
                  AND revoked_at_ms IS NULL
                  AND expires_at_ms > ?
                """,
                (crew_id, timestamp),
            ).fetchone()

            if active_session is None:
                raise BroadcastAuthorizationError(
                    "Crew session is no longer active"
                )

            connection.execute(
                """
                INSERT INTO active_broadcasts (
                    id, title, body, category,
                    created_by_session_id, created_at_ms,
                    expires_at_ms, ended_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    broadcast_id,
                    title,
                    body,
                    category,
                    crew_id,
                    timestamp,
                    expires_at,
                ),
            )

        row = connection.execute(
            "SELECT * FROM active_broadcasts WHERE id = ?",
            (broadcast_id,),
        ).fetchone()

    return _broadcast_from_row(row)


def list_active_broadcasts() -> list[dict[str, Any]]:
    """Return announcements that are active at the current time."""
    timestamp = now_ms()

    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT id, title, body, category,
                   created_at_ms, expires_at_ms
            FROM active_broadcasts
            WHERE ended_at_ms IS NULL
              AND expires_at_ms > ?
            ORDER BY created_at_ms DESC, id DESC
            """,
            (timestamp,),
        ).fetchall()

    return [_broadcast_from_row(row) for row in rows]


def get_active_broadcast(
    broadcast_id: str,
) -> dict[str, Any] | None:
    """Return one active announcement, or None if inactive or missing."""
    timestamp = now_ms()

    with get_db() as connection:
        row = connection.execute(
            """
            SELECT id, title, body, category,
                   created_at_ms, expires_at_ms
            FROM active_broadcasts
            WHERE id = ?
              AND ended_at_ms IS NULL
              AND expires_at_ms > ?
            """,
            (broadcast_id, timestamp),
        ).fetchone()

    return _broadcast_from_row(row) if row is not None else None


def end_broadcast(
    crew_session: dict[str, Any],
    broadcast_id: str,
) -> dict[str, Any]:
    """End an active announcement and return its updated record."""
    crew_id = _require_crew(crew_session)
    timestamp = now_ms()

    with get_db() as connection:
        with transaction(connection):
            active_session = connection.execute(
                """
                SELECT id
                FROM sessions
                WHERE id = ?
                  AND role = 'crew'
                  AND revoked_at_ms IS NULL
                  AND expires_at_ms > ?
                """,
                (crew_id, timestamp),
            ).fetchone()

            if active_session is None:
                raise BroadcastAuthorizationError(
                    "Crew session is no longer active"
                )

            row = connection.execute(
                """
                SELECT *
                FROM active_broadcasts
                WHERE id = ?
                  AND ended_at_ms IS NULL
                  AND expires_at_ms > ?
                """,
                (broadcast_id, timestamp),
            ).fetchone()

            if row is None:
                raise BroadcastNotFoundError(
                    "Announcement is not active or does not exist"
                )

            connection.execute(
                """
                UPDATE active_broadcasts
                SET ended_at_ms = ?
                WHERE id = ?
                  AND ended_at_ms IS NULL
                """,
                (timestamp, broadcast_id),
            )

        updated = connection.execute(
            "SELECT * FROM active_broadcasts WHERE id = ?",
            (broadcast_id,),
        ).fetchone()

    return _broadcast_from_row(updated)


# Convenient aliases for route handlers.
get_active_broadcasts = list_active_broadcasts
broadcast_announcement = create_broadcast
end_announcement = end_broadcast
