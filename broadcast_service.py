"""Persistent PA announcement lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import time
from typing import Any
import uuid

from database import get_db, transaction


BASE_DIR = Path(__file__).resolve().parent
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


_PA_CARDS_CACHE: dict[str, dict[str, Any]] | None = None


def load_pa_cards(reload: bool = False) -> dict[str, dict[str, Any]]:
    """Load and return the fixed, approved PA card catalog from data/pa_cards.json."""
    global _PA_CARDS_CACHE
    if _PA_CARDS_CACHE is not None and not reload:
        return _PA_CARDS_CACHE

    cards_path = BASE_DIR / "data" / "pa_cards.json"
    if not cards_path.is_file():
        raise FileNotFoundError(f"PA card catalog not found at {cards_path}")

    try:
        data = json.loads(cards_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BroadcastServiceError(f"Failed to read PA card catalog: {exc}") from exc

    cards_list = data.get("cards", [])
    cards_map: dict[str, dict[str, Any]] = {}
    for card in cards_list:
        card_id = card.get("id")
        if card_id:
            cards_map[card_id] = card

    _PA_CARDS_CACHE = cards_map
    return cards_map


def _require_crew(session: dict[str, Any]) -> str:
    """Return a crew session ID after checking the authenticated role."""
    if not isinstance(session, dict) or session.get("role") != "crew":
        raise BroadcastAuthorizationError("Crew authorization is required")

    session_id = session.get("id")
    if not isinstance(session_id, str) or not session_id:
        raise BroadcastAuthorizationError("Invalid crew session")

    return session_id


def _broadcast_from_row(
    row: sqlite3.Row | dict[str, Any],
    current_time_ms: int | None = None,
) -> dict[str, Any]:
    """Serialize a database row into standard API and Socket.IO broadcast contract shapes."""
    data = dict(row)
    current_time = current_time_ms if current_time_ms is not None else now_ms()

    broadcast_id = data.get("id", "")
    ended_at = data.get("ended_at_ms")
    expires_at = data.get("expires_at_ms", 0)
    created_at = data.get("created_at_ms", 0)
    pa_card_id = data.get("pa_card_id") or ""
    title = data.get("title", "")
    body = data.get("body", "")
    category = data.get("category", "general")
    created_by = data.get("created_by_session_id", "")

    is_active = (ended_at is None) and (expires_at > current_time)

    # Provide all canonical keys expected across API_CONTRACT, DATABASE_CONTRACT, and SOCKET_EVENTS
    return {
        "id": broadcast_id,
        "broadcast_id": broadcast_id,
        "pa_card_id": pa_card_id,
        "title": title,
        "body": body,
        "category": category,
        "created_by": created_by,
        "created_by_session_id": created_by,
        "created_at": created_at,
        "created_at_ms": created_at,
        "expires_at": expires_at,
        "expires_at_ms": expires_at,
        "ended_at": ended_at,
        "ended_at_ms": ended_at,
        "active_status": is_active,
        "is_active": is_active,
        "labels": {
            "en": body,
        },
    }


def create_broadcast(
    crew_session: dict[str, Any],
    *,
    pa_card_id: str,
    duration_seconds: int | None = None,
    current_time_ms: int | None = None,
) -> dict[str, Any]:
    """Persist a crew announcement with an approved PA card and bounded expiration."""
    crew_id = _require_crew(crew_session)

    if not pa_card_id or not isinstance(pa_card_id, str):
        raise InvalidBroadcastError("pa_card_id is required")

    pa_card_id = pa_card_id.strip()
    cards = load_pa_cards()
    card = cards.get(pa_card_id)
    if card is None:
        raise InvalidBroadcastError(f"Unknown PA card ID: {pa_card_id}")

    # Resolve reviewed content and bounds from trusted catalog
    title = card.get("title", "Announcement")
    body = card.get("body", "")
    category = card.get("category", "general")

    if duration_seconds is None:
        ttl = int(card.get("default_ttl_seconds", DEFAULT_TTL_SECONDS))
    else:
        if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int):
            raise InvalidBroadcastError("duration_seconds must be an integer")
        ttl = duration_seconds

    if not 1 <= ttl <= MAX_TTL_SECONDS:
        raise InvalidBroadcastError(
            f"duration_seconds must be between 1 and {MAX_TTL_SECONDS}"
        )

    timestamp = current_time_ms if current_time_ms is not None else now_ms()
    expires_at = timestamp + ttl * 1000
    broadcast_id = str(uuid.uuid4())

    with get_db() as connection:
        with transaction(connection):
            # Ensure the crew session still exists, is not revoked, and is active.
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
                raise BroadcastAuthorizationError("Crew session is no longer active")

            connection.execute(
                """
                INSERT INTO active_broadcasts (
                    id, pa_card_id, title, body, category,
                    created_by_session_id, created_at_ms,
                    expires_at_ms, ended_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    broadcast_id,
                    pa_card_id,
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

    return _broadcast_from_row(row, current_time_ms=timestamp)


def list_active_broadcasts(current_time_ms: int | None = None) -> list[dict[str, Any]]:
    """Return announcements that are active at the specified (or current) time."""
    timestamp = current_time_ms if current_time_ms is not None else now_ms()

    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM active_broadcasts
            WHERE ended_at_ms IS NULL
              AND expires_at_ms > ?
            ORDER BY created_at_ms DESC, id DESC
            """,
            (timestamp,),
        ).fetchall()

    return [_broadcast_from_row(row, current_time_ms=timestamp) for row in rows]


def list_crew_broadcasts(
    crew_session: dict[str, Any],
    include_inactive: bool = False,
    current_time_ms: int | None = None,
) -> list[dict[str, Any]]:
    """List broadcasts for crew review, optionally including inactive/ended broadcasts."""
    _require_crew(crew_session)
    timestamp = current_time_ms if current_time_ms is not None else now_ms()

    with get_db() as connection:
        if include_inactive:
            rows = connection.execute(
                """
                SELECT *
                FROM active_broadcasts
                ORDER BY created_at_ms DESC, id DESC
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT *
                FROM active_broadcasts
                WHERE ended_at_ms IS NULL
                  AND expires_at_ms > ?
                ORDER BY created_at_ms DESC, id DESC
                """,
                (timestamp,),
            ).fetchall()

    return [_broadcast_from_row(row, current_time_ms=timestamp) for row in rows]


def get_active_broadcast(
    broadcast_id: str,
    current_time_ms: int | None = None,
) -> dict[str, Any] | None:
    """Return one active announcement, or None if inactive, expired, or missing."""
    timestamp = current_time_ms if current_time_ms is not None else now_ms()

    with get_db() as connection:
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

    return _broadcast_from_row(row, current_time_ms=timestamp) if row is not None else None


def end_broadcast(
    crew_session: dict[str, Any],
    broadcast_id: str,
    current_time_ms: int | None = None,
) -> dict[str, Any]:
    """End an announcement idempotently and return its updated record."""
    crew_id = _require_crew(crew_session)
    timestamp = current_time_ms if current_time_ms is not None else now_ms()

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
                raise BroadcastAuthorizationError("Crew session is no longer active")

            row = connection.execute(
                "SELECT * FROM active_broadcasts WHERE id = ?",
                (broadcast_id,),
            ).fetchone()

            if row is None:
                raise BroadcastNotFoundError("Announcement does not exist")

            if row["ended_at_ms"] is None:
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

    return _broadcast_from_row(updated, current_time_ms=timestamp)


# Convenient aliases for route handlers
get_active_broadcasts = list_active_broadcasts
broadcast_announcement = create_broadcast
end_announcement = end_broadcast
