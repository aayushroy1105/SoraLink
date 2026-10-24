"""Comprehensive tests for Socket.IO reconnection, room authorization, and state resynchronization.

Covers:
- Socket.IO connection authentication with valid, missing, expired, and revoked session cookies.
- Server-controlled role-specific room assignment (crew:dashboard, passenger:<session_id>, passengers:all).
- Reconnection after missed request_created events (crew queue state resynchronization).
- Reconnection after missed request_updated and crew_reply events (passenger state recovery).
- Reconnection after missed PA broadcast created and ended events.
- Refresh-based passenger and crew state recovery via REST endpoints.
- Cross-seat isolation (zero event or data leakage between seats).
- state_resync_required event triggers and exact payload contract compliance.
- Idempotent request operations preventing duplicate socket emissions.
- Disconnection mid-lifecycle preserving SQLite transaction durability.
- Content catalog and passenger replies endpoints.
"""

from __future__ import annotations

import json
from typing import Any
import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import socketio
from database import get_connection, now_ms
import requests_service


CREW_TEST_PASSWORD = "test-crew-password-xyz"


@pytest.fixture(autouse=True)
def configure_environment(monkeypatch: pytest.MonkeyPatch):
    """Ensure crew code is configured for crew authentication during tests."""
    monkeypatch.setenv("SORALINK_CREW_CODE", CREW_TEST_PASSWORD)
    monkeypatch.setenv("SORALINK_CREW_USERNAME", "crew_demo")


def _login_passenger(client: FlaskClient, seat_label: str = "18A", demo_code: str = "0000") -> dict[str, Any]:
    """Helper to authenticate passenger and return login payload dict."""
    res = client.post(
        "/api/auth/passenger",
        json={"seat_label": seat_label, "demo_code": demo_code},
    )
    assert res.status_code == 200, f"Passenger login failed: {res.json}"
    return res.json["data"]


def _login_crew(client: FlaskClient) -> dict[str, Any]:
    """Helper to authenticate crew and return login payload dict."""
    res = client.post(
        "/api/auth/crew",
        json={"username": "crew_demo", "password": CREW_TEST_PASSWORD},
    )
    assert res.status_code == 200, f"Crew login failed: {res.json}"
    return res.json["data"]


# ============================================================================
# 1. Socket.IO Connection Authentication and Validation
# ============================================================================

def test_socket_connection_with_valid_passenger_cookie(app: Flask, client: FlaskClient):
    """Valid passenger session cookie connects and receives connection_ready with seat info."""
    data = _login_passenger(client, seat_label="18A")
    session_id = data["session_id"]

    socket = socketio.test_client(app, flask_test_client=client)
    assert socket.is_connected()

    received = socket.get_received()
    assert len(received) >= 1
    ready_event = next(e for e in received if e["name"] == "connection_ready")
    args = ready_event["args"][0]
    assert args["role"] == "passenger"
    assert args["session_id"] == session_id
    assert args["seat_label"] == "18A"
    assert "server_time" in args
    assert isinstance(args["server_time"], int)

    socket.disconnect()


def test_socket_connection_with_valid_crew_cookie(app: Flask, client: FlaskClient):
    """Valid crew session cookie connects and receives connection_ready with crew info."""
    data = _login_crew(client)
    session_id = data["session_id"]

    socket = socketio.test_client(app, flask_test_client=client)
    assert socket.is_connected()

    received = socket.get_received()
    ready_event = next(e for e in received if e["name"] == "connection_ready")
    args = ready_event["args"][0]
    assert args["role"] == "crew"
    assert args["session_id"] == session_id
    assert "crew_id" in args
    assert "server_time" in args

    socket.disconnect()


def test_socket_connection_missing_cookie_rejected(app: Flask, client: FlaskClient):
    """Socket.IO connection without session cookie is rejected."""
    socket = socketio.test_client(app, flask_test_client=client)
    assert not socket.is_connected()


def test_socket_connection_expired_cookie_rejected(app: Flask, client: FlaskClient):
    """Socket.IO connection with an expired session cookie is rejected."""
    _login_passenger(client, seat_label="18A")

    # Manually expire the session in SQLite
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE sessions SET created_at_ms = ?, expires_at_ms = ?",
            (now_ms() - 20000, now_ms() - 10000),
        )
        conn.commit()
    finally:
        conn.close()

    socket = socketio.test_client(app, flask_test_client=client)
    assert not socket.is_connected()


def test_socket_connection_revoked_cookie_rejected(app: Flask, client: FlaskClient):
    """Socket.IO connection with a revoked (logged out) session cookie is rejected."""
    _login_passenger(client, seat_label="18A")

    # Log out to revoke session
    res_logout = client.post("/api/auth/logout")
    assert res_logout.status_code == 200

    socket = socketio.test_client(app, flask_test_client=client)
    assert not socket.is_connected()


def test_socket_connection_forged_cookie_rejected(app: Flask, client: FlaskClient):
    """Socket.IO connection with a forged session cookie is rejected."""
    client.set_cookie("soralink_session", "forged-token-value-12345")
    socket = socketio.test_client(app, flask_test_client=client)
    assert not socket.is_connected()


# ============================================================================
# 2. Server-Controlled Room Authorization and Cross-Seat Isolation
# ============================================================================

def test_room_assignment_and_cross_seat_isolation(app: Flask):
    """Passenger and crew clients are joined only to authorized rooms; no cross-seat leakage."""
    client_a = app.test_client()
    client_b = app.test_client()
    client_crew = app.test_client()

    pass_a = _login_passenger(client_a, seat_label="18A", demo_code="0000")
    pass_b = _login_passenger(client_b, seat_label="14B", demo_code="DEMO-14B")
    _login_crew(client_crew)

    sock_a = socketio.test_client(app, flask_test_client=client_a)
    sock_b = socketio.test_client(app, flask_test_client=client_b)
    sock_crew = socketio.test_client(app, flask_test_client=client_crew)

    assert sock_a.is_connected()
    assert sock_b.is_connected()
    assert sock_crew.is_connected()

    # Clear initial connection_ready events
    sock_a.get_received()
    sock_b.get_received()
    sock_crew.get_received()

    # Passenger A creates a request
    res_create = client_a.post("/api/requests", json={"intent_id": "water_request"})
    assert res_create.status_code == 201
    req_id = res_create.json["data"]["request_id"]

    # Crew receives request_created
    crew_events = sock_crew.get_received()
    assert any(e["name"] == "request_created" and e["args"][0]["request"]["request_id"] == req_id for e in crew_events)

    # Passenger A receives request_updated
    a_events = sock_a.get_received()
    assert any(e["name"] == "request_updated" and e["args"][0]["request_id"] == req_id for e in a_events)

    # CRITICAL: Passenger B must receive NOTHING
    b_events = sock_b.get_received()
    assert len(b_events) == 0, f"Passenger B leaked events: {b_events}"

    # Crew acknowledges Passenger A's request with a canned response
    res_ack = client_crew.post(
        f"/api/crew/requests/{req_id}/acknowledge",
        json={"response_id": "request_acknowledged"},
    )
    assert res_ack.status_code == 200

    # Passenger A receives updated status and crew_reply
    a_ack_events = sock_a.get_received()
    assert any(e["name"] == "request_updated" and e["args"][0]["status"] == "ACKNOWLEDGED" for e in a_ack_events)
    assert any(e["name"] == "crew_reply" and e["args"][0]["request_id"] == req_id for e in a_ack_events)

    # Crew receives request_updated
    crew_ack_events = sock_crew.get_received()
    assert any(e["name"] == "request_updated" and e["args"][0]["request_id"] == req_id for e in crew_ack_events)

    # CRITICAL: Passenger B must still receive NOTHING
    assert len(sock_b.get_received()) == 0

    sock_a.disconnect()
    sock_b.disconnect()
    sock_crew.disconnect()


# ============================================================================
# 3. State Resynchronization: Missed Request Events
# ============================================================================

def test_crew_reconnect_recovers_missed_request_created(app: Flask):
    """Crew client disconnects, passenger creates request, crew reconnects and recovers full state."""
    client_crew = app.test_client()
    client_pass = app.test_client()

    _login_crew(client_crew)
    _login_passenger(client_pass, seat_label="18A")

    sock_crew = socketio.test_client(app, flask_test_client=client_crew)
    assert sock_crew.is_connected()
    sock_crew.get_received()

    # Simulate network drop / Wi-Fi interruption on crew side
    sock_crew.disconnect()
    assert not sock_crew.is_connected()

    # Passenger creates an urgent request while crew socket is offline
    res_req = client_pass.post("/api/requests", json={"intent_id": "medical_help"})
    assert res_req.status_code == 201
    urgent_req_id = res_req.json["data"]["request_id"]

    # Passenger also creates a routine request
    res_req2 = client_pass.post("/api/requests", json={"intent_id": "water_request"})
    assert res_req2.status_code == 201
    routine_req_id = res_req2.json["data"]["request_id"]

    # Crew reconnects
    sock_crew_reconnected = socketio.test_client(app, flask_test_client=client_crew)
    assert sock_crew_reconnected.is_connected()

    # Authoritative state recovery: crew calls GET /api/crew/requests
    res_queue = client_crew.get("/api/crew/requests")
    assert res_queue.status_code == 200
    requests_list = res_queue.json["data"]["requests"]

    # Both requests were recovered from SQLite
    req_ids = [r["id"] for r in requests_list]
    assert urgent_req_id in req_ids
    assert routine_req_id in req_ids

    # Urgency ordering verified: urgent medical_help appears before routine water_request
    urgent_idx = req_ids.index(urgent_req_id)
    routine_idx = req_ids.index(routine_req_id)
    assert urgent_idx < routine_idx

    sock_crew_reconnected.disconnect()


def test_passenger_reconnect_recovers_missed_acknowledgement_and_completion(app: Flask):
    """Passenger disconnects, crew acknowledges and completes request, passenger reconnects and recovers state."""
    client_pass = app.test_client()
    client_crew = app.test_client()

    _login_passenger(client_pass, seat_label="18A")
    _login_crew(client_crew)

    sock_pass = socketio.test_client(app, flask_test_client=client_pass)
    assert sock_pass.is_connected()

    res_create = client_pass.post("/api/requests", json={"intent_id": "blanket_request"})
    assert res_create.status_code == 201
    req_id = res_create.json["data"]["request_id"]

    # Passenger Wi-Fi drops / client disconnects
    sock_pass.disconnect()
    assert not sock_pass.is_connected()

    # Crew acknowledges while passenger is offline
    res_ack = client_crew.post(
        f"/api/crew/requests/{req_id}/acknowledge",
        json={"response_id": "request_acknowledged"},
    )
    assert res_ack.status_code == 200

    # Crew completes the request while passenger is offline
    res_comp = client_crew.post(f"/api/crew/requests/{req_id}/complete")
    assert res_comp.status_code == 200

    # Passenger reconnects
    sock_pass_reconnected = socketio.test_client(app, flask_test_client=client_pass)
    assert sock_pass_reconnected.is_connected()

    # Passenger performs state resync via REST
    res_state = client_pass.get("/api/passenger/state")
    assert res_state.status_code == 200
    passenger_requests = res_state.json["data"]["requests"]

    req_record = next(r for r in passenger_requests if r["id"] == req_id)
    assert req_record["status"] == "COMPLETED"
    assert req_record["acknowledged_at_ms"] is not None
    assert req_record["completed_at_ms"] is not None

    # Passenger also checks replies endpoint
    res_replies = client_pass.get("/api/passenger/replies")
    assert res_replies.status_code == 200
    replies_data = res_replies.json["data"]
    assert "requests" in replies_data
    assert "crew_responses" in replies_data

    sock_pass_reconnected.disconnect()


# ============================================================================
# 4. State Resynchronization: Missed PA Broadcast Events
# ============================================================================

def test_passenger_reconnect_recovers_missed_broadcast_create_and_end(app: Flask):
    """Passenger disconnects, crew creates and ends broadcasts, passenger reconnects and retrieves current state."""
    client_pass = app.test_client()
    client_crew = app.test_client()

    _login_passenger(client_pass, seat_label="18A")
    _login_crew(client_crew)

    sock_pass = socketio.test_client(app, flask_test_client=client_pass)
    assert sock_pass.is_connected()

    # Passenger drops connection
    sock_pass.disconnect()
    assert not sock_pass.is_connected()

    # Crew creates broadcast 1 (turbulence) while passenger is disconnected
    res_b1 = client_crew.post("/api/crew/pa/broadcast", json={"pa_card_id": "turbulence"})
    assert res_b1.status_code == 201
    b1_id = res_b1.json["data"]["broadcast_id"]

    # Passenger reconnects
    sock_pass_rec1 = socketio.test_client(app, flask_test_client=client_pass)
    assert sock_pass_rec1.is_connected()

    # Authoritative active broadcast retrieval
    res_active1 = client_pass.get("/api/pa/active")
    assert res_active1.status_code == 200
    active_ids = [b["id"] for b in res_active1.json["data"]["broadcasts"]]
    assert b1_id in active_ids

    # Passenger drops connection again
    sock_pass_rec1.disconnect()

    # Crew ends broadcast 1 while passenger is disconnected
    res_end = client_crew.post("/api/crew/pa/end", json={"broadcast_id": b1_id})
    assert res_end.status_code == 200

    # Passenger reconnects second time
    sock_pass_rec2 = socketio.test_client(app, flask_test_client=client_pass)
    assert sock_pass_rec2.is_connected()

    # Authoritative active broadcast retrieval confirms broadcast 1 is gone
    res_active2 = client_pass.get("/api/pa/active")
    assert res_active2.status_code == 200
    active_ids2 = [b["id"] for b in res_active2.json["data"]["broadcasts"]]
    assert b1_id not in active_ids2

    sock_pass_rec2.disconnect()


# ============================================================================
# 5. Full Browser Refresh State Recovery
# ============================================================================

def test_browser_refresh_passenger_and_crew_state_recovery(app: Flask):
    """Browser refresh recovers authoritative identity, seat ownership, and operational state."""
    client_pass = app.test_client()
    client_crew = app.test_client()

    p_data = _login_passenger(client_pass, seat_label="18A")
    c_data = _login_crew(client_crew)

    # Passenger submits request
    res_req = client_pass.post("/api/requests", json={"intent_id": "water_request"})
    assert res_req.status_code == 201
    req_id = res_req.json["data"]["request_id"]

    # Crew creates broadcast
    res_pa = client_crew.post("/api/crew/pa/broadcast", json={"pa_card_id": "meal_service"})
    assert res_pa.status_code == 201
    pa_id = res_pa.json["data"]["broadcast_id"]

    # --- SIMULATE PASSENGER BROWSER REFRESH (HTTP session cookie preserved) ---
    res_p_me = client_pass.get("/api/auth/me")
    assert res_p_me.status_code == 200
    assert res_p_me.json["data"]["seat_label"] == "18A"
    assert res_p_me.json["data"]["session_id"] == p_data["session_id"]
    assert res_p_me.json["data"]["role"] == "passenger"

    res_p_state = client_pass.get("/api/passenger/state")
    assert res_p_state.status_code == 200
    assert any(r["id"] == req_id for r in res_p_state.json["data"]["requests"])
    assert any(b["id"] == pa_id for b in res_p_state.json["data"]["active_broadcasts"])

    # --- SIMULATE CREW BROWSER REFRESH ---
    res_c_me = client_crew.get("/api/auth/me")
    assert res_c_me.status_code == 200
    assert res_c_me.json["data"]["role"] == "crew"
    assert res_c_me.json["data"]["session_id"] == c_data["session_id"]

    res_c_reqs = client_crew.get("/api/crew/requests")
    assert res_c_reqs.status_code == 200
    assert any(r["id"] == req_id for r in res_c_reqs.json["data"]["requests"])

    res_c_bcasts = client_crew.get("/api/crew/broadcasts")
    assert res_c_bcasts.status_code == 200
    assert any(b["id"] == pa_id for b in res_c_bcasts.json["data"]["broadcasts"])


# ============================================================================
# 6. state_resync_required Event and request_resync Handler
# ============================================================================

def test_state_resync_required_on_explicit_reconnect_flag(app: Flask, client: FlaskClient):
    """When a client connects with reconnect=1 query param, state_resync_required is emitted."""
    _login_passenger(client, seat_label="18A")

    # Connect with reconnect query param
    socket = socketio.test_client(app, flask_test_client=client, query_string="reconnect=1")
    assert socket.is_connected()

    received = socket.get_received()
    event_names = [e["name"] for e in received]
    assert "connection_ready" in event_names
    assert "state_resync_required" in event_names

    resync_event = next(e for e in received if e["name"] == "state_resync_required")
    assert resync_event["args"][0] == {"reason": "reconnect_or_state_mismatch"}

    socket.disconnect()


def test_request_resync_socket_event_triggers_state_resync_required(app: Flask, client: FlaskClient):
    """Authenticated client can emit request_resync to receive state_resync_required."""
    _login_passenger(client, seat_label="18A")

    socket = socketio.test_client(app, flask_test_client=client)
    assert socket.is_connected()
    socket.get_received()  # Clear initial events

    # Emit client request_resync
    socket.emit("request_resync", {})

    received = socket.get_received()
    assert len(received) >= 1
    resync_event = next(e for e in received if e["name"] == "state_resync_required")
    assert resync_event["args"][0] == {"reason": "reconnect_or_state_mismatch"}

    socket.disconnect()


# ============================================================================
# 7. Idempotency and Deduplication in Reconnection Scenarios
# ============================================================================

def test_idempotent_visual_request_does_not_duplicate_queue_or_events(app: Flask):
    """Repeated visual request with idempotency key does not emit duplicate request_created notifications."""
    client_pass = app.test_client()
    client_crew = app.test_client()

    _login_passenger(client_pass, seat_label="18A")
    _login_crew(client_crew)

    sock_crew = socketio.test_client(app, flask_test_client=client_crew)
    sock_crew.get_received()

    # First submission
    res1 = client_pass.post(
        "/api/requests",
        json={"intent_id": "water_request", "client_request_id": "idem-key-100"},
    )
    assert res1.status_code == 201

    events1 = sock_crew.get_received()
    assert len([e for e in events1 if e["name"] == "request_created"]) == 1

    # Replay identical submission (e.g. after network retry)
    res2 = client_pass.post(
        "/api/requests",
        json={"intent_id": "water_request", "client_request_id": "idem-key-100"},
    )
    assert res2.status_code == 200
    assert res2.json["data"]["request_id"] == res1.json["data"]["request_id"]

    # No duplicate request_created emitted to crew
    events2 = sock_crew.get_received()
    assert len([e for e in events2 if e["name"] == "request_created"]) == 0

    sock_crew.disconnect()


def test_idempotent_crew_acknowledge_and_complete_do_not_duplicate_events(app: Flask):
    """Repeated acknowledge and complete actions do not re-emit socket events when was_updated is false."""
    client_pass = app.test_client()
    client_crew = app.test_client()

    _login_passenger(client_pass, seat_label="18A")
    _login_crew(client_crew)

    sock_pass = socketio.test_client(app, flask_test_client=client_pass)
    sock_crew = socketio.test_client(app, flask_test_client=client_crew)

    res_create = client_pass.post("/api/requests", json={"intent_id": "blanket_request"})
    req_id = res_create.json["data"]["request_id"]

    sock_pass.get_received()
    sock_crew.get_received()

    # 1. Acknowledge
    res_ack1 = client_crew.post(f"/api/crew/requests/{req_id}/acknowledge")
    assert res_ack1.status_code == 200

    pass_events = sock_pass.get_received()
    crew_events = sock_crew.get_received()
    assert len([e for e in pass_events if e["name"] == "request_updated"]) == 1
    assert len([e for e in crew_events if e["name"] == "request_updated"]) == 1

    # Repeated Acknowledge
    res_ack2 = client_crew.post(f"/api/crew/requests/{req_id}/acknowledge")
    assert res_ack2.status_code == 200

    assert len(sock_pass.get_received()) == 0
    assert len(sock_crew.get_received()) == 0

    # 2. Complete
    res_comp1 = client_crew.post(f"/api/crew/requests/{req_id}/complete")
    assert res_comp1.status_code == 200

    assert len([e for e in sock_pass.get_received() if e["name"] == "request_updated"]) == 1
    assert len([e for e in sock_crew.get_received() if e["name"] == "request_updated"]) == 1

    # Repeated Complete
    res_comp2 = client_crew.post(f"/api/crew/requests/{req_id}/complete")
    assert res_comp2.status_code == 200

    assert len(sock_pass.get_received()) == 0
    assert len(sock_crew.get_received()) == 0

    sock_pass.disconnect()
    sock_crew.disconnect()


# ============================================================================
# 8. Fixed Content Catalog and Replies Endpoints
# ============================================================================

def test_content_catalog_endpoint(client: FlaskClient):
    """GET /api/content/catalog returns reviewed intent catalog and crew responses."""
    res = client.get("/api/content/catalog")
    assert res.status_code == 200
    data = res.json["data"]
    assert "intents" in data
    assert isinstance(data["intents"], list)
    assert len(data["intents"]) > 0

    assert "crew_responses" in data
    assert isinstance(data["crew_responses"], dict)
    assert "request_acknowledged" in data["crew_responses"]


def test_passenger_replies_endpoint(app: Flask, client: FlaskClient):
    """GET /api/passenger/replies requires authentication and returns passenger requests and reviewed responses."""
    # Unauthenticated rejected
    res_unauth = client.get("/api/passenger/replies")
    assert res_unauth.status_code == 401

    # Authenticated passenger
    _login_passenger(client, seat_label="18A")
    client.post("/api/requests", json={"intent_id": "water_request"})

    res = client.get("/api/passenger/replies")
    assert res.status_code == 200
    data = res.json["data"]
    assert "requests" in data
    assert len(data["requests"]) >= 1
    assert "crew_responses" in data
    assert "request_received" in data["crew_responses"]
    assert "messages" in data["crew_responses"]["request_received"]
    assert "en" in data["crew_responses"]["request_received"]["messages"]
    assert "ja" in data["crew_responses"]["request_received"]["messages"]
