"""Passenger and crew authentication and authorization.

Passenger access is granted through seeded seat invitation codes.
Crew access is granted through a server-configured crew access code or credentials.

Clients receive an HTTP-only cookie containing an opaque session token.
Only its SHA-256 hash is stored in the sessions table.
Roles and seat labels are read from the database, never trusted from client-supplied fields.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from typing import Any

from database import get_db, transaction


DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60


class AuthenticationError(Exception):
    """Raised when authentication credentials are invalid."""


class AuthorizationError(Exception):
    """Raised when a session lacks permission for an action."""


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _session_ttl_ms() -> int:
    raw = os.environ.get("SORALINK_SESSION_TTL_SECONDS", "")
    try:
        seconds = int(raw) if raw else DEFAULT_SESSION_TTL_SECONDS
    except ValueError:
        seconds = DEFAULT_SESSION_TTL_SECONDS

    # Prevent accidental zero-length or excessively long sessions.
    seconds = max(60, min(seconds, 7 * 24 * 60 * 60))
    return seconds * 1000


def _new_session(
    *,
    role: str,
    seat_label: str | None = None,
) -> dict[str, Any]:
    """Create a session and return its one-time raw token and session metadata."""
    if role not in {"passenger", "crew"}:
        raise ValueError("Unsupported session role")

    now = _now_ms()
    expires_at = now + _session_ttl_ms()
    token = secrets.token_urlsafe(32)
    token_hash = _hash_secret(token)
    session_id = secrets.token_urlsafe(18)

    with get_db() as connection:
        with transaction(connection):
            connection.execute(
                """
                INSERT INTO sessions (
                    id, role, seat_label, token_hash,
                    created_at_ms, expires_at_ms, revoked_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    session_id,
                    role,
                    seat_label,
                    token_hash,
                    now,
                    expires_at,
                ),
            )

    return {
        "token": token,
        "session": {
            "id": session_id,
            "role": role,
            "seat_label": seat_label,
            "created_at_ms": now,
            "expires_at_ms": expires_at,
        },
    }


def authenticate_passenger(
    seat_label: str,
    demo_code: str | None = None,
) -> dict[str, Any]:
    """Verify a passenger seat invitation and create a session.

    Accepts (seat_label, demo_code) as required by the contract.
    Also supports legacy single-argument call authenticate_passenger(invite_code).
    """
    if demo_code is None:
        # Legacy invite_code lookup
        if not isinstance(seat_label, str) or not seat_label.strip():
            raise AuthenticationError("A seat invitation code is required")
        code_hash = _hash_secret(seat_label.strip())
        with get_db() as connection:
            row = connection.execute(
                """
                SELECT seat_label, is_active
                FROM seat_invites
                WHERE invite_code_hash = ?
                """,
                (code_hash,),
            ).fetchone()
    else:
        if not isinstance(seat_label, str) or not seat_label.strip():
            raise AuthenticationError("A seat label is required")
        if not isinstance(demo_code, str) or not demo_code.strip():
            raise AuthenticationError("A demo code is required")

        norm_seat = seat_label.strip().upper()
        code_hash = _hash_secret(demo_code.strip())

        with get_db() as connection:
            row = connection.execute(
                """
                SELECT seat_label, is_active
                FROM seat_invites
                WHERE seat_label = ? AND invite_code_hash = ?
                """,
                (norm_seat, code_hash),
            ).fetchone()

    if row is None or not row["is_active"]:
        raise AuthenticationError("Invalid or inactive seat invitation")

    return _new_session(
        role="passenger",
        seat_label=row["seat_label"],
    )


def authenticate_crew(
    username_or_code: str,
    password: str | None = None,
) -> dict[str, Any]:
    """Verify crew credentials against the configured crew code.

    Accepts (username, password) as documented in the contract.
    Also supports legacy single-argument call authenticate_crew(crew_code).
    """
    configured_code = os.environ.get("SORALINK_CREW_CODE") or os.environ.get("SORALINK_CREW_PASSWORD")

    if not configured_code:
        raise AuthenticationError(
            "Crew authentication is not configured on this server"
        )

    if password is None:
        # Legacy single-argument call where the first parameter is the crew access code
        crew_code = username_or_code
        if not isinstance(crew_code, str) or not hmac.compare_digest(
            crew_code.encode("utf-8"),
            configured_code.encode("utf-8"),
        ):
            raise AuthenticationError("Invalid crew access code")
    else:
        username = username_or_code
        expected_user = os.environ.get("SORALINK_CREW_USERNAME", "crew_demo")

        if not isinstance(username, str) or username.strip() != expected_user:
            raise AuthenticationError("Invalid crew credentials")

        if not isinstance(password, str) or not hmac.compare_digest(
            password.encode("utf-8"),
            configured_code.encode("utf-8"),
        ):
            raise AuthenticationError("Invalid crew credentials")

    return _new_session(role="crew")


def get_session_by_token(token: str) -> dict[str, Any] | None:
    """Resolve an opaque session token to an active session, or return None."""
    if not isinstance(token, str) or not token:
        return None

    token_hash = _hash_secret(token)
    now = _now_ms()

    with get_db() as connection:
        row = connection.execute(
            """
            SELECT id, role, seat_label, created_at_ms, expires_at_ms
            FROM sessions
            WHERE token_hash = ?
              AND revoked_at_ms IS NULL
              AND expires_at_ms > ?
            """,
            (token_hash, now),
        ).fetchone()

    return dict(row) if row is not None else None


def get_current_session_from_cookie(cookie_value: str | None) -> dict[str, Any]:
    """Return the authenticated session from a cookie value or raise AuthenticationError."""
    if not cookie_value or not isinstance(cookie_value, str):
        raise AuthenticationError("Missing session cookie")

    session = get_session_by_token(cookie_value.strip())
    if session is None:
        raise AuthenticationError("Missing, invalid, expired, or revoked session")

    return session


def get_bearer_token(authorization_header: str | None) -> str | None:
    """Extract a Bearer token from an Authorization header if present."""
    if not authorization_header:
        return None

    parts = authorization_header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1].strip()
    return token or None


def get_current_session(authorization_header_or_cookie: str | None) -> dict[str, Any]:
    """Return the authenticated session or raise AuthenticationError."""
    if not authorization_header_or_cookie:
        raise AuthenticationError("Missing, invalid, expired, or revoked session")

    token = get_bearer_token(authorization_header_or_cookie) or authorization_header_or_cookie.strip()
    session = get_session_by_token(token)

    if session is None:
        raise AuthenticationError("Missing, invalid, expired, or revoked session")

    return session


def require_role(
    session: dict[str, Any],
    expected_role: str,
) -> dict[str, Any]:
    """Ensure a resolved session has the required server-side role."""
    if session.get("role") != expected_role:
        raise AuthorizationError("You are not authorized to perform this action")
    return session


def revoke_session(session_id: str) -> bool:
    """Revoke a session. Returns True if an active session was revoked."""
    now = _now_ms()

    with get_db() as connection:
        with transaction(connection):
            cursor = connection.execute(
                """
                UPDATE sessions
                SET revoked_at_ms = ?
                WHERE id = ?
                  AND revoked_at_ms IS NULL
                """,
                (now, session_id),
            )

    return cursor.rowcount > 0


def revoke_current_session(cookie_or_header: str | None) -> bool:
    """Revoke the session associated with a valid token."""
    session = get_current_session(cookie_or_header)
    return revoke_session(session["id"])
