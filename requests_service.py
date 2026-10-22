
"""Request validation, persistence, queue ordering, and lifecycle."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from database import get_db, transaction


BASE_DIR = Path(__file__).resolve().parent
INTENTS_PATH = BASE_DIR / "data" / "intents.json"

VALID_STATUSES = {"PENDING", "ACKNOWLEDGED", "COMPLETED"}


class RequestServiceError(Exception):
    """Base exception for request-service failures."""


class InvalidIntentError(RequestServiceError):
    """The supplied intent ID is not in the canonical catalog."""


class RequestNotFoundError(RequestServiceError):
    """The requested record does not exist or is not accessible."""


class InvalidTransitionError(RequestServiceError):
    """The requested lifecycle transition is not allowed."""


class DuplicateActiveRequestError(RequestServiceError):
    """An active request for this seat and intent already exists."""


def now_ms() -> int:
    """Return UTC Unix time in milliseconds."""
    return time.time_ns() // 1_000_000


def load_intent_catalog() -> dict[str, dict[str, Any]]:
    """Load and validate the canonical intent catalog."""
    if not INTENTS_PATH.is_file():
        raise RuntimeError(f"Intent catalog not found: {INTENTS_PATH}")

    try:
        payload = json.loads(INTENTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Unable to read the intent catalog") from exc

    intents = payload.get("intents")
    if not isinstance(intents, list):
        raise RuntimeError("Intent catalog must contain an intents list")

    catalog: dict[str, dict[str, Any]] = {}

    for item in intents:
        if not isinstance(item, dict):
            raise RuntimeError("Each intent must be a JSON object")

        intent_id = item.get("id")
        priority = item.get("priority")

        if not isinstance(intent_id, str) or not intent_id:
            raise RuntimeError("Every intent must have a non-empty ID")

        if priority not in {"urgent", "routine"}:
            raise RuntimeError(f"Invalid priority for intent: {intent_id}")

        if intent_id in catalog:
            raise RuntimeError(f"Duplicate intent ID: {intent_id}")

        catalog[intent_id] = item

    return catalog


def validate_intent(intent_id: str) -> dict[str, Any]:
    """Return a canonical intent or reject an unknown ID."""
    if not isinstance(intent_id, str) or not intent_id:
        raise InvalidIntentError("A valid intent ID is required")

    intent = load_intent_catalog().get(intent_id)
    if intent is None:
        raise InvalidIntentError("Unknown intent ID")

    return intent


def _require_passenger(session: dict[str, Any]) -> tuple[str, str]:
    """Return passenger session ID and seat after checking authorization."""
    if session.get("role") != "passenger":
        raise PermissionError("Only passengers can submit this request")

    session_id = session.get("id")
    seat_label = session.get("seat_label")

    if not isinstance(session_id, str) or not session_id:
        raise PermissionError("Invalid passenger session")

    if not isinstance(seat_label, str) or not seat_label:
        raise PermissionError("Passenger session has no assigned seat")

    return session_id, seat_label


def _require_crew(session: dict[str, Any]) -> str:
    """Return the crew session ID after checking authorization."""
    if session.get("role") != "crew":
        raise PermissionError("Crew authorization is required")

    session_id = session.get("id")
    if not isinstance(session_id, str) or not session_id:
        raise PermissionError("Invalid crew session")

    return session_id


def _request_from_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    """Convert a SQLite row to a plain dictionary."""
    return dict(row)


def create_request(
    passenger_session: dict[str, Any],
    intent_id: str,
) -> dict[str, Any]:
    """Create a visual/typed passenger request.

    Seat and role come from the authenticated session, not the request body.
    Priority is loaded from the canonical intent catalog.
    """
    session_id, seat_label = _require_passenger(passenger_session)
    intent = validate_intent(intent_id)
    priority = intent["priority"]
    timestamp = now_ms()
    request_id = str(uuid.uuid4())

    with get_db() as connection:
        try:
            with transaction(connection):
                # Confirm the session is still active in the database.
                active_session = connection.execute(
                    """
                    SELECT id
                    FROM sessions
                    WHERE id = ?
                      AND role = 'passenger'
                      AND seat_label = ?
                      AND revoked_at_ms IS NULL
                      AND expires_at_ms > ?
                    """,
                    (session_id, seat_label, timestamp),
                ).fetchone()

                if active_session is None:
                    raise PermissionError("Passenger session is no longer active")

                existing = connection.execute(
                    """
                    SELECT *
                    FROM requests
                    WHERE seat_label = ?
                      AND intent_id = ?
                      AND status IN ('PENDING', 'ACKNOWLEDGED')
                    """,
                    (seat_label, intent_id),
                ).fetchone()

                if existing is not None:
                    raise DuplicateActiveRequestError(
                        "An active request for this item already exists"
                    )

                connection.execute(
                    """
                    INSERT INTO requests (
                        id, session_id, seat_label, intent_id, priority,
                        status, created_at_ms, updated_at_ms,
                        acknowledged_at_ms, completed_at_ms, acknowledged_by
                    )
                    VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?, NULL, NULL, NULL)
                    """,
                    (
                        request_id,
                        session_id,
                        seat_label,
                        intent_id,
                        priority,
                        timestamp,
                        timestamp,
                    ),
                )

                connection.execute(
                    """
                    INSERT INTO request_events (
                        request_id, actor_session_id, event_type,
                        details_json, created_at_ms
                    )
                    VALUES (?, ?, 'CREATED', ?, ?)
                    """,
                    (
                        request_id,
                        session_id,
                        json.dumps({"intent_id": intent_id}),
                        timestamp,
                    ),
                )

        except sqlite3.IntegrityError as exc:
            # The unique partial index also protects against concurrent inserts.
            if "idx_requests_no_active_duplicate" in str(exc) or (
                "UNIQUE constraint failed: requests.seat_label, requests.intent_id"
                in str(exc)
            ):
                raise DuplicateActiveRequestError(
                    "An active request for this item already exists"
                ) from exc
            raise

        row = connection.execute(
            "SELECT * FROM requests WHERE id = ?",
            (request_id,),
        ).fetchone()

    return _request_from_row(row)


def list_crew_requests(
    crew_session: dict[str, Any],
    *,
    include_completed: bool = False,
) -> list[dict[str, Any]]:
    """Return requests in urgent-first, FIFO-within-priority order."""
    _require_crew(crew_session)

    if include_completed:
        status_filter = ""
        params: tuple[Any, ...] = ()
    else:
        status_filter = "WHERE status IN ('PENDING', 'ACKNOWLEDGED')"
        params = ()

    with get_db() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM requests
            {status_filter}
            ORDER BY
                CASE priority WHEN 'urgent' THEN 0 ELSE 1 END,
                created_at_ms ASC,
                id ASC
            """,
            params,
        ).fetchall()

    return [_request_from_row(row) for row in rows]


def list_passenger_requests(
    passenger_session: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return requests belonging only to the authenticated passenger session."""
    session_id, seat_label = _require_passenger(passenger_session)

    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM requests
            WHERE session_id = ? AND seat_label = ?
            ORDER BY created_at_ms DESC, id DESC
            """,
            (session_id, seat_label),
        ).fetchall()

    return [_request_from_row(row) for row in rows]


def _get_request(connection: sqlite3.Connection, request_id: str):
    row = connection.execute(
        "SELECT * FROM requests WHERE id = ?",
        (request_id,),
    ).fetchone()

    if row is None:
        raise RequestNotFoundError("Request not found")

    return row


def acknowledge_request(
    crew_session: dict[str, Any],
    request_id: str,
) -> dict[str, Any]:
    """Move a pending request to acknowledged."""
    crew_id = _require_crew(crew_session)
    timestamp = now_ms()

    with get_db() as connection:
        with transaction(connection):
            request = _get_request(connection, request_id)

            if request["status"] != "PENDING":
                raise InvalidTransitionError(
                    "Only pending requests can be acknowledged"
                )

            connection.execute(
                """
                UPDATE requests
                SET status = 'ACKNOWLEDGED',
                    updated_at_ms = ?,
                    acknowledged_at_ms = ?,
                    acknowledged_by = ?
                WHERE id = ? AND status = 'PENDING'
                """,
                (timestamp, timestamp, crew_id, request_id),
            )

            connection.execute(
                """
                INSERT INTO request_events (
                    request_id, actor_session_id, event_type,
                    details_json, created_at_ms
                )
                VALUES (?, ?, 'ACKNOWLEDGED', '{}', ?)
                """,
                (request_id, crew_id, timestamp),
            )

        row = connection.execute(
            "SELECT * FROM requests WHERE id = ?",
            (request_id,),
        ).fetchone()

    return _request_from_row(row)


def complete_request(
    crew_session: dict[str, Any],
    request_id: str,
) -> dict[str, Any]:
    """Move an acknowledged request to completed."""
    crew_id = _require_crew(crew_session)
    timestamp = now_ms()

    with get_db() as connection:
        with transaction(connection):
            request = _get_request(connection, request_id)

            if request["status"] != "ACKNOWLEDGED":
                raise InvalidTransitionError(
                    "Only acknowledged requests can be completed"
                )

            connection.execute(
                """
                UPDATE requests
                SET status = 'COMPLETED',
                    updated_at_ms = ?,
                    completed_at_ms = ?
                WHERE id = ? AND status = 'ACKNOWLEDGED'
                """,
                (timestamp, timestamp, request_id),
            )

            connection.execute(
                """
                INSERT INTO request_events (
                    request_id, actor_session_id, event_type,
                    details_json, created_at_ms
                )
                VALUES (?, ?, 'COMPLETED', '{}', ?)
                """,
                (request_id, crew_id, timestamp),
            )

        row = connection.execute(
            "SELECT * FROM requests WHERE id = ?",
            (request_id,),
        ).fetchone()

    return _request_from_row(row)


def request_follow_up(
    passenger_session: dict[str, Any],
    request_id: str,
    message: str = "",
) -> dict[str, Any]:
    """Record a passenger follow-up for their own active request."""
    session_id, seat_label = _require_passenger(passenger_session)

    if not isinstance(message, str):
        raise ValueError("Follow-up message must be text")

    # Avoid storing unbounded client-provided text.
    message = message.strip()[:300]
    timestamp = now_ms()

    with get_db() as connection:
        with transaction(connection):
            request = connection.execute(
                """
                SELECT *
                FROM requests
                WHERE id = ? AND session_id = ? AND seat_label = ?
                """,
                (request_id, session_id, seat_label),
            ).fetchone()

            if request is None:
                raise RequestNotFoundError("Request not found")

            if request["status"] == "COMPLETED":
                raise InvalidTransitionError(
                    "A completed request cannot receive a follow-up"
                )

            connection.execute(
                """
                INSERT INTO request_events (
                    request_id, actor_session_id, event_type,
                    details_json, created_at_ms
                )
                VALUES (?, ?, 'FOLLOW_UP_REQUESTED', ?, ?)
                """,
                (
                    request_id,
                    session_id,
                    json.dumps({"message": message}),
                    timestamp,
                ),
            )

        row = connection.execute(
            "SELECT * FROM requests WHERE id = ?",
            (request_id,),
        ).fetchone()

    return _request_from_row(row)


# Short aliases for callers that use the API contract's terminology.
get_crew_requests = list_crew_requests
get_passenger_requests = list_passenger_requests
