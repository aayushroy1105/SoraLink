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
CREW_RESPONSES_PATH = BASE_DIR / "data" / "crew_responses.json"

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


class IdempotencyConflictError(RequestServiceError):
    """The idempotency key was previously used for a different request."""


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

        # Support the AI branch's frozen catalog schema and the
        # backend's existing normalized schema.
        intent_id = item.get("id") or item.get("intent_id")
        priority = item.get("priority")

        if not isinstance(intent_id, str) or not intent_id:
            raise RuntimeError("Every intent must have a non-empty ID")

        if isinstance(priority, str):
            priority = priority.lower()

        if priority not in {"urgent", "routine"}:
            raise RuntimeError(f"Invalid priority for intent: {intent_id}")

        if intent_id in catalog:
            raise RuntimeError(f"Duplicate intent ID: {intent_id}")

        normalized = {
            **item,
            "id": intent_id,
            "priority": priority,
            "label": item.get("label")
            or item.get("labels", {}).get("en", intent_id),
        }
        catalog[intent_id] = normalized

    return catalog



def load_crew_responses() -> dict[str, dict[str, Any]]:
    """Load the canonical crew responses dictionary."""
    if not CREW_RESPONSES_PATH.is_file():
        return {}
    try:
        data = json.loads(CREW_RESPONSES_PATH.read_text(encoding="utf-8"))
        return data.get("responses", {})
    except (OSError, json.JSONDecodeError):
        return {}


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
    """Convert a SQLite row to a plain dictionary matching contract conventions."""
    item = dict(row)
    item["request_id"] = item.get("id")
    item["created_at"] = item.get("created_at_ms")
    item["updated_at"] = item.get("updated_at_ms")
    item["acknowledged_at"] = item.get("acknowledged_at_ms")
    item["completed_at"] = item.get("completed_at_ms")

    # Priority in uppercase for API response envelope
    if "priority" in item and isinstance(item["priority"], str):
        item["priority"] = item["priority"].upper()

    intent_id = item.get("intent_id")
    if intent_id:
        try:
            catalog = load_intent_catalog()
            intent = catalog.get(intent_id)
            if intent:
                item["label"] = intent.get("label")
                item["labels"] = {
                    "en": intent.get("label", ""),
                }
        except Exception:
            pass

    # Attach any stored crew reply fields so GET /api/passenger/state returns
    # them after a page reload or session rotation (not just via Socket.IO).
    ack_json = item.pop("ack_details_json", None)
    if ack_json:
        try:
            ack_details = json.loads(ack_json) if isinstance(ack_json, str) else ack_json
            item["crew_reply_id"] = ack_details.get("response_id")
            labels = ack_details.get("labels", {})
            item["crew_reply_text_en"] = labels.get("en")
            item["crew_reply_text_ja"] = labels.get("ja")
            item["crew_reply"] = {
                "response_id": ack_details.get("response_id"),
                "labels": labels,
            }
        except Exception:
            pass

    for field in ("crew_reply_id", "crew_reply_text_en", "crew_reply_text_ja"):
        if field not in item:
            item[field] = None
    if "crew_reply" not in item:
        item["crew_reply"] = None

    return item


def create_request(
    passenger_session: dict[str, Any],
    intent_id: str,
    client_request_id: str | None = None,
) -> dict[str, Any]:
    """Create a visual/typed passenger request with deduplication and idempotency.

    Seat and role come from the authenticated session, not the request body.
    Priority is loaded from the canonical intent catalog.
    Returns request dictionary with 'was_created': True if newly inserted, False if deduplicated/idempotent.
    """
    session_id, seat_label = _require_passenger(passenger_session)
    intent = validate_intent(intent_id)
    priority = intent["priority"]  # 'urgent' or 'routine' for DB CHECK constraint
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

                # 1. Idempotency key validation if client_request_id was provided
                if client_request_id:
                    existing_events = connection.execute(
                        """
                        SELECT re.request_id, re.details_json, r.*
                        FROM request_events re
                        JOIN requests r ON re.request_id = r.id
                        WHERE re.actor_session_id = ?
                          AND re.event_type = 'CREATED'
                        """,
                        (session_id,),
                    ).fetchall()

                    for ev in existing_events:
                        try:
                            details = json.loads(ev["details_json"])
                        except (TypeError, json.JSONDecodeError):
                            details = {}
                        if details.get("client_request_id") == client_request_id:
                            if ev["intent_id"] == intent_id:
                                # Idempotent replay of original request
                                result = _request_from_row(ev)
                                result["was_created"] = False
                                return result
                            else:
                                # Conflicting reuse of idempotency key for different request
                                raise IdempotencyConflictError(
                                    "Idempotency key has already been used for a different request"
                                )

                # 2. Active-request deduplication: check for active request for same seat & intent
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
                    # Contract requirement: return existing active request
                    result = _request_from_row(existing)
                    result["was_created"] = False
                    return result

                # 3. Create new request
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

                event_details: dict[str, Any] = {"intent_id": intent_id}
                if client_request_id:
                    event_details["client_request_id"] = client_request_id

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
                        json.dumps(event_details),
                        timestamp,
                    ),
                )

        except sqlite3.IntegrityError as exc:
            # Handle concurrent race condition caught by idx_requests_no_active_duplicate
            if "idx_requests_no_active_duplicate" in str(exc) or (
                "UNIQUE constraint failed: requests.seat_label, requests.intent_id"
                in str(exc)
            ):
                with get_db() as conn:
                    row = conn.execute(
                        """
                        SELECT * FROM requests
                        WHERE seat_label = ? AND intent_id = ?
                          AND status IN ('PENDING', 'ACKNOWLEDGED')
                        """,
                        (seat_label, intent_id),
                    ).fetchone()
                    if row is not None:
                        result = _request_from_row(row)
                        result["was_created"] = False
                        return result
            raise

        row = connection.execute(
            "SELECT * FROM requests WHERE id = ?",
            (request_id,),
        ).fetchone()

    result = _request_from_row(row)
    result["was_created"] = True
    return result


def list_crew_requests(
    crew_session: dict[str, Any],
    *,
    include_completed: bool = False,
) -> list[dict[str, Any]]:
    """Return requests in urgent-first, FIFO-within-priority order."""
    _require_crew(crew_session)

    if include_completed:
        status_filter = ""
    else:
        status_filter = "WHERE r.status IN ('PENDING', 'ACKNOWLEDGED')"

    with get_db() as connection:
        rows = connection.execute(
            f"""
            SELECT r.*,
                   (
                       SELECT details_json
                       FROM request_events
                       WHERE request_id = r.id AND event_type = 'ACKNOWLEDGED'
                       ORDER BY id DESC
                       LIMIT 1
                   ) AS ack_details_json
            FROM requests r
            {status_filter}
            ORDER BY
                CASE r.priority WHEN 'urgent' THEN 0 ELSE 1 END,
                r.created_at_ms ASC,
                r.id ASC
            """
        ).fetchall()

    return [_request_from_row(row) for row in rows]


def list_passenger_requests(
    passenger_session: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return all requests for the authenticated passenger's seat.

    Queries by ``seat_label`` only (not ``session_id``) so that requests
    created during a previous session are visible after a re-login.  This
    also means a passenger whose session was rotated by a page reload still
    sees the full request history for their seat.
    """
    _session_id, seat_label = _require_passenger(passenger_session)

    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT r.*,
                   (
                       SELECT details_json
                       FROM request_events
                       WHERE request_id = r.id AND event_type = 'ACKNOWLEDGED'
                       ORDER BY id DESC
                       LIMIT 1
                   ) AS ack_details_json
            FROM requests r
            WHERE r.seat_label = ?
            ORDER BY r.created_at_ms DESC, r.id DESC
            """,
            (seat_label,),
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
    response_id: str | None = None,
) -> dict[str, Any]:
    """Move a pending request to acknowledged. Repeated calls are handled idempotently."""
    crew_id = _require_crew(crew_session)
    timestamp = now_ms()

    with get_db() as connection:
        with transaction(connection):
            request = _get_request(connection, request_id)

            if request["status"] == "ACKNOWLEDGED":
                row = connection.execute(
                    """
                    SELECT r.*,
                           (
                               SELECT details_json
                               FROM request_events
                               WHERE request_id = r.id AND event_type = 'ACKNOWLEDGED'
                               ORDER BY id DESC
                               LIMIT 1
                           ) AS ack_details_json
                    FROM requests r
                    WHERE r.id = ?
                    """,
                    (request_id,),
                ).fetchone()
                result = _request_from_row(row)
                result["was_updated"] = False
                return result

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

            details: dict[str, Any] = {}
            if response_id:
                crew_responses = load_crew_responses()
                resp_info = crew_responses.get(response_id)
                details["response_id"] = response_id
                if resp_info:
                    details["labels"] = resp_info.get("messages", {})

            connection.execute(
                """
                INSERT INTO request_events (
                    request_id, actor_session_id, event_type,
                    details_json, created_at_ms
                )
                VALUES (?, ?, 'ACKNOWLEDGED', ?, ?)
                """,
                (request_id, crew_id, json.dumps(details), timestamp),
            )

        row = connection.execute(
            """
            SELECT r.*,
                   (
                       SELECT details_json
                       FROM request_events
                       WHERE request_id = r.id AND event_type = 'ACKNOWLEDGED'
                       ORDER BY id DESC
                       LIMIT 1
                   ) AS ack_details_json
            FROM requests r
            WHERE r.id = ?
            """,
            (request_id,),
        ).fetchone()

    result = _request_from_row(row)
    result["was_updated"] = True
    return result


def complete_request(
    crew_session: dict[str, Any],
    request_id: str,
) -> dict[str, Any]:
    """Move an acknowledged request to completed. Repeated calls are handled idempotently."""
    crew_id = _require_crew(crew_session)
    timestamp = now_ms()

    with get_db() as connection:
        with transaction(connection):
            request = _get_request(connection, request_id)

            if request["status"] == "COMPLETED":
                result = _request_from_row(request)
                result["was_updated"] = False
                return result

            if request["status"] == "PENDING":
                raise InvalidTransitionError(
                    "A request must be acknowledged before completion"
                )

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
            """
            SELECT r.*,
                   (
                       SELECT details_json
                       FROM request_events
                       WHERE request_id = r.id AND event_type = 'ACKNOWLEDGED'
                       ORDER BY id DESC
                       LIMIT 1
                   ) AS ack_details_json
            FROM requests r
            WHERE r.id = ?
            """,
            (request_id,),
        ).fetchone()

    result = _request_from_row(row)
    result["was_updated"] = True
    return result


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
            # Look up request by ID and seat_label — we intentionally do NOT
            # filter by session_id here because a passenger may have re-logged
            # in (new session ID) but still owns requests for their seat.
            request = connection.execute(
                """
                SELECT *
                FROM requests
                WHERE id = ? AND seat_label = ?
                """,
                (request_id, seat_label),
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
            """
            SELECT r.*,
                   (
                       SELECT details_json
                       FROM request_events
                       WHERE request_id = r.id AND event_type = 'ACKNOWLEDGED'
                       ORDER BY id DESC
                       LIMIT 1
                   ) AS ack_details_json
            FROM requests r
            WHERE r.id = ?
            """,
            (request_id,),
        ).fetchone()

    return _request_from_row(row)


def get_request_events(request_id: str) -> list[dict[str, Any]]:
    """Return all audit events for a request in chronological order."""
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM request_events
            WHERE request_id = ?
            ORDER BY created_at_ms ASC, id ASC
            """,
            (request_id,),
        ).fetchall()

    events = []
    for row in rows:
        d = dict(row)
        try:
            d["details"] = json.loads(d["details_json"])
        except Exception:
            d["details"] = {}
        events.append(d)
    return events


def get_request_by_id(request_id: str) -> dict[str, Any] | None:
    """Retrieve a request by its primary key ID, or None if not found."""
    with get_db() as connection:
        row = connection.execute(
            """
            SELECT r.*,
                   (
                       SELECT details_json
                       FROM request_events
                       WHERE request_id = r.id AND event_type = 'ACKNOWLEDGED'
                       ORDER BY id DESC
                       LIMIT 1
                   ) AS ack_details_json
            FROM requests r
            WHERE r.id = ?
            """,
            (request_id,),
        ).fetchone()

    return _request_from_row(row) if row is not None else None


# Short aliases for callers that use the API contract's terminology.
get_crew_requests = list_crew_requests
get_passenger_requests = list_passenger_requests
