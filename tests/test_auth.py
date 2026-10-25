"""Contract-compliant authentication tests for SoraLink backend.

Covers AUTH-01 through AUTH-05, session inspection, role isolation,
malformed payloads, session expiry, revocation, seat immutability,
and Socket.IO session validation.
"""

from __future__ import annotations

import sqlite3
from typing import Any
import pytest
from flask.testing import FlaskClient

from database import get_connection, now_ms


CREW_TEST_PASSWORD = "test-crew-password-xyz"


@pytest.fixture(autouse=True)
def configure_crew_code(monkeypatch: pytest.MonkeyPatch):
    """Ensure crew code is configured for test execution."""
    monkeypatch.setenv("SORALINK_CREW_CODE", CREW_TEST_PASSWORD)
    monkeypatch.setenv("SORALINK_CREW_USERNAME", "crew_demo")


# =============================================================================
# AUTH-01: Valid passenger login
# =============================================================================

def test_auth_01_valid_passenger_login(client: FlaskClient):
    """AUTH-01: Valid passenger credentials establish session, set cookie, return role & seat."""
    res = client.post(
        "/api/auth/passenger",
        json={"seat_label": "18A", "demo_code": "0000"},
    )
    assert res.status_code == 200
    assert res.json["ok"] is True

    data = res.json["data"]
    assert data["role"] == "passenger"
    assert data["seat_label"] == "18A"
    assert "session_id" in data
    assert isinstance(data["session_id"], str) and len(data["session_id"]) > 0

    # Ensure no secrets or tokens are leaked in the JSON envelope
    assert "token" not in data
    assert "token_hash" not in data
    assert "invite_code" not in data
    assert "demo_code" not in data

    # Verify HTTP-only session cookie is set
    set_cookie = res.headers.get("Set-Cookie", "")
    assert "soralink_session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()

    # Verify session inspection endpoint works with the established cookie
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json["ok"] is True
    me_data = me_res.json["data"]
    assert me_data["role"] == "passenger"
    assert me_data["seat_label"] == "18A"
    assert me_data["session_id"] == data["session_id"]


# =============================================================================
# AUTH-02: Invalid passenger credentials
# =============================================================================

def test_auth_02_invalid_passenger_credentials(client: FlaskClient):
    """AUTH-02: Invalid passenger credentials are rejected with standard error envelope."""
    # Wrong demo code
    res = client.post(
        "/api/auth/passenger",
        json={"seat_label": "18A", "demo_code": "wrong_code"},
    )
    assert res.status_code == 401
    assert res.json["ok"] is False
    assert res.json["error"]["code"] == "INVALID_CREDENTIALS"
    assert "soralink_session=" not in res.headers.get("Set-Cookie", "")

    # Unknown seat
    res_unknown = client.post(
        "/api/auth/passenger",
        json={"seat_label": "99Z", "demo_code": "0000"},
    )
    assert res_unknown.status_code == 401
    assert res_unknown.json["ok"] is False
    assert res_unknown.json["error"]["code"] == "INVALID_CREDENTIALS"

    # Inactive invitation
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE seat_invites SET is_active = 0 WHERE seat_label = '18A'"
        )
    finally:
        conn.close()

    res_inactive = client.post(
        "/api/auth/passenger",
        json={"seat_label": "18A", "demo_code": "0000"},
    )
    assert res_inactive.status_code == 401
    assert res_inactive.json["ok"] is False
    assert res_inactive.json["error"]["code"] == "INVALID_CREDENTIALS"


# =============================================================================
# AUTH-03: Valid crew login
# =============================================================================

def test_auth_03_valid_crew_login(client: FlaskClient):
    """AUTH-03: Valid crew credentials establish crew session and return crew role/identity."""
    res = client.post(
        "/api/auth/crew",
        json={"username": "crew_demo", "password": CREW_TEST_PASSWORD},
    )
    assert res.status_code == 200
    assert res.json["ok"] is True

    data = res.json["data"]
    assert data["role"] == "crew"
    assert "crew_id" in data
    assert isinstance(data["crew_id"], str) and len(data["crew_id"]) > 0
    # Crew sessions must not be assigned a passenger seat
    assert data.get("seat_label") is None

    # No secrets or token hashes in response
    assert "token" not in data
    assert "token_hash" not in data
    assert "password" not in data

    # Session cookie set with proper attributes
    set_cookie = res.headers.get("Set-Cookie", "")
    assert "soralink_session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()

    # Verify session inspection reflects crew role
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json["ok"] is True
    assert me_res.json["data"]["role"] == "crew"
    assert me_res.json["data"]["crew_id"] == data["crew_id"]
    assert me_res.json["data"].get("seat_label") is None


def test_auth_03_invalid_crew_credentials(client: FlaskClient, monkeypatch: pytest.MonkeyPatch):
    """AUTH-03 negative cases: wrong password, wrong username, unconfigured server."""
    # Wrong password
    res = client.post(
        "/api/auth/crew",
        json={"username": "crew_demo", "password": "wrong-password"},
    )
    assert res.status_code == 401
    assert res.json["ok"] is False
    assert res.json["error"]["code"] == "INVALID_CREDENTIALS"

    # Wrong username
    res_user = client.post(
        "/api/auth/crew",
        json={"username": "wrong_user", "password": CREW_TEST_PASSWORD},
    )
    assert res_user.status_code == 401
    assert res_user.json["ok"] is False
    assert res_user.json["error"]["code"] == "INVALID_CREDENTIALS"

    # When crew authentication is not configured in server environment
    monkeypatch.delenv("SORALINK_CREW_CODE", raising=False)
    monkeypatch.delenv("SORALINK_CREW_PASSWORD", raising=False)
    res_unconfigured = client.post(
        "/api/auth/crew",
        json={"username": "crew_demo", "password": CREW_TEST_PASSWORD},
    )
    assert res_unconfigured.status_code == 401
    assert res_unconfigured.json["ok"] is False
    assert res_unconfigured.json["error"]["code"] == "INVALID_CREDENTIALS"


# =============================================================================
# AUTH-04: Role isolation
# =============================================================================

def test_auth_04_passenger_cannot_access_crew_endpoints(client: FlaskClient):
    """AUTH-04: Passenger session cannot access crew-only endpoints."""
    # Authenticate as passenger
    res = client.post(
        "/api/auth/passenger",
        json={"seat_label": "18A", "demo_code": "0000"},
    )
    assert res.status_code == 200

    # Attempt to access crew-only endpoints
    res_queue = client.get("/api/crew/requests")
    assert res_queue.status_code == 403
    assert res_queue.json["ok"] is False
    assert res_queue.json["error"]["code"] == "FORBIDDEN"

    res_pa = client.get("/api/crew/pa/cards")
    assert res_pa.status_code == 403
    assert res_pa.json["ok"] is False
    assert res_pa.json["error"]["code"] == "FORBIDDEN"

    res_broadcast = client.post(
        "/api/crew/pa/broadcast",
        json={"title": "Test", "body": "Test Announcement"},
    )
    assert res_broadcast.status_code == 403
    assert res_broadcast.json["ok"] is False
    assert res_broadcast.json["error"]["code"] == "FORBIDDEN"


def test_auth_04_crew_cannot_access_passenger_endpoints(client: FlaskClient):
    """AUTH-04: Crew session cannot access passenger-only endpoints."""
    # Authenticate as crew
    res = client.post(
        "/api/auth/crew",
        json={"username": "crew_demo", "password": CREW_TEST_PASSWORD},
    )
    assert res.status_code == 200

    # Attempt to access passenger-only endpoints
    res_state = client.get("/api/passenger/state")
    assert res_state.status_code == 403
    assert res_state.json["ok"] is False
    assert res_state.json["error"]["code"] == "FORBIDDEN"

    res_request = client.post(
        "/api/requests",
        json={"intent_id": "water_request"},
    )
    assert res_request.status_code == 403
    assert res_request.json["ok"] is False
    assert res_request.json["error"]["code"] == "FORBIDDEN"


# =============================================================================
# AUTH-05: Logout and session revocation
# =============================================================================

def test_auth_05_logout_invalidates_session_and_clears_cookie(client: FlaskClient):
    """AUTH-05: Logout invalidates the server session, clears cookie, and prevents access."""
    # Authenticate passenger
    login_res = client.post(
        "/api/auth/passenger",
        json={"seat_label": "18A", "demo_code": "0000"},
    )
    session_id = login_res.json["data"]["session_id"]

    # Verify session is currently active
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200

    # Log out
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.json["ok"] is True
    assert logout_res.json["data"]["logged_out"] is True

    # Check that Set-Cookie instructs browser to clear the cookie
    set_cookie = logout_res.headers.get("Set-Cookie", "")
    assert "soralink_session=" in set_cookie
    # Usually Max-Age=0 or Expires in past
    assert "max-age=0" in set_cookie.lower() or "expires=" in set_cookie.lower()

    # Subsequent access with client (where cookie is cleared) is rejected
    after_res = client.get("/api/auth/me")
    assert after_res.status_code == 401
    assert after_res.json["ok"] is False
    assert after_res.json["error"]["code"] == "UNAUTHENTICATED"

    # Verify directly in SQLite that revoked_at_ms was recorded
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT revoked_at_ms FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        assert row is not None
        assert row["revoked_at_ms"] is not None
    finally:
        conn.close()


# =============================================================================
# Edge cases: Missing cookie, expired session, malformed payloads
# =============================================================================

def test_missing_cookie_returns_unauthenticated(client: FlaskClient):
    """Protected endpoints reject requests without a session cookie."""
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.json["ok"] is False
    assert res.json["error"]["code"] == "UNAUTHENTICATED"

    res_logout = client.post("/api/auth/logout")
    assert res_logout.status_code == 401
    assert res_logout.json["ok"] is False
    assert res_logout.json["error"]["code"] == "UNAUTHENTICATED"


def test_invalid_or_forged_cookie_rejected(client: FlaskClient):
    """A tampered or non-existent session token cookie is rejected."""
    client.set_cookie("soralink_session", "completely-forged-token-value")
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.json["ok"] is False
    assert res.json["error"]["code"] == "UNAUTHENTICATED"


def test_expired_session_rejected(client: FlaskClient):
    """An expired server session is rejected on protected access."""
    login_res = client.post(
        "/api/auth/passenger",
        json={"seat_label": "18A", "demo_code": "0000"},
    )
    session_id = login_res.json["data"]["session_id"]

    # Manually expire the session in SQLite by shifting both created_at_ms and expires_at_ms into the past
    past_now = now_ms() - 100_000
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE sessions SET created_at_ms = ?, expires_at_ms = ? WHERE id = ?",
            (past_now - 50_000, past_now, session_id),
        )
    finally:
        conn.close()

    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.json["ok"] is False
    assert res.json["error"]["code"] == "UNAUTHENTICATED"


def test_malformed_login_payloads(client: FlaskClient):
    """Malformed or non-JSON payloads are rejected with 400 BAD_REQUEST."""
    # Passenger malformed payloads
    res1 = client.post(
        "/api/auth/passenger",
        data="not a json string",
        content_type="text/plain",
    )
    assert res1.status_code == 400
    assert res1.json["ok"] is False
    assert res1.json["error"]["code"] == "BAD_REQUEST"

    res2 = client.post("/api/auth/passenger", json={})
    assert res2.status_code == 400
    assert res2.json["ok"] is False
    assert res2.json["error"]["code"] == "BAD_REQUEST"

    res3 = client.post("/api/auth/passenger", json={"seat_label": "18A"})
    assert res3.status_code == 400
    assert res3.json["ok"] is False

    res4 = client.post("/api/auth/passenger", json={"demo_code": "0000"})
    assert res4.status_code == 400
    assert res4.json["ok"] is False

    # Crew malformed payloads
    res5 = client.post("/api/auth/crew", json={})
    assert res5.status_code == 400
    assert res5.json["ok"] is False
    assert res5.json["error"]["code"] == "BAD_REQUEST"

    res6 = client.post(
        "/api/auth/crew",
        data="raw-data",
        content_type="text/plain",
    )
    assert res6.status_code == 400
    assert res6.json["ok"] is False


def test_passenger_seat_cannot_be_spoofed_in_request_body(client: FlaskClient):
    """Passenger cannot change seat identity by supplying a different seat_label in request body."""
    # Authenticate as seat 18A
    client.post(
        "/api/auth/passenger",
        json={"seat_label": "18A", "demo_code": "0000"},
    )

    # Attempt to submit a request claiming to be seat 32D
    res = client.post(
        "/api/requests",
        json={"intent_id": "water_request", "seat_label": "32D"},
    )
    assert res.status_code == 201
    created_request = res.json["data"]["request"]

    # Seat must be derived from session (18A), not from body (32D)
    assert created_request["seat_label"] == "18A"

    # Verify in SQLite database directly
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT seat_label FROM requests WHERE id = ?",
            (created_request["id"],),
        ).fetchone()
        assert row is not None
        assert row["seat_label"] == "18A"
    finally:
        conn.close()


def test_socketio_session_cookie_authentication(app: Any, client: FlaskClient):
    """Socket.IO authentication uses the same server-validated session cookie."""
    from app import socketio

    # 1. Unauthenticated Socket.IO connection is rejected
    unauth_socket = socketio.test_client(app, flask_test_client=client)
    assert not unauth_socket.is_connected()

    # 2. Authenticate as passenger via REST to obtain cookie
    login_res = client.post(
        "/api/auth/passenger",
        json={"seat_label": "18A", "demo_code": "0000"},
    )
    assert login_res.status_code == 200
    session_id = login_res.json["data"]["session_id"]

    # Connect with the client that now holds the session cookie
    pass_socket = socketio.test_client(app, flask_test_client=client)
    assert pass_socket.is_connected()

    received = pass_socket.get_received()
    assert any(
        event["name"] == "connection_ready"
        and event["args"][0].get("role") == "passenger"
        and event["args"][0].get("session_id") == session_id
        for event in received
    )
    pass_socket.disconnect()

    # 3. Log out and ensure Socket.IO connection is subsequently rejected
    client.post("/api/auth/logout")
    post_logout_socket = socketio.test_client(app, flask_test_client=client)
    assert not post_logout_socket.is_connected()


def test_html_page_routes(client: FlaskClient):
    """HTML frontend routes serve their corresponding templates."""
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert b"<!doctype html>" in res_root.data.lower()

    res_login = client.get("/login")
    assert res_login.status_code == 200
    assert b"<!doctype html>" in res_login.data.lower()

    res_pass = client.get("/passenger")
    assert res_pass.status_code == 200
    assert b"<!doctype html>" in res_pass.data.lower()

    res_crew = client.get("/crew")
    assert res_crew.status_code == 200
    assert b"<!doctype html>" in res_crew.data.lower()
