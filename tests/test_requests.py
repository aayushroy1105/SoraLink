"""Comprehensive tests for SoraLink request lifecycle, persistence, and realtime events.

Covers:
- Authenticated passenger request creation
- Canonical intent validation and server priority derivation
- Identity and seat spoofing prevention
- Cross-passenger isolation
- Crew queue ordering (Urgent before Routine, FIFO within priority)
- Valid and invalid state transitions (PENDING -> ACKNOWLEDGED -> COMPLETED)
- Idempotency and active-request deduplication
- Conflicting reuse of client idempotency keys
- Durable persistence across fresh database connections
- Socket.IO notifications emitted only after commit and not on failure
"""

from __future__ import annotations

import json
from typing import Any
import pytest
from flask.testing import FlaskClient

from database import get_connection, now_ms
import requests_service


CREW_TEST_PASSWORD = "test-crew-password-xyz"


@pytest.fixture(autouse=True)
def configure_environment(monkeypatch: pytest.MonkeyPatch):
    """Ensure crew code is configured for crew authentication during tests."""
    monkeypatch.setenv("SORALINK_CREW_CODE", CREW_TEST_PASSWORD)
    monkeypatch.setenv("SORALINK_CREW_USERNAME", "crew_demo")


def _login_passenger(client: FlaskClient, seat_label: str = "18A", demo_code: str = "0000") -> str:
    """Helper to authenticate passenger and return session_id."""
    res = client.post(
        "/api/auth/passenger",
        json={"seat_label": seat_label, "demo_code": demo_code},
    )
    assert res.status_code == 200, f"Passenger login failed: {res.json}"
    return res.json["data"]["session_id"]


def _login_crew(client: FlaskClient) -> str:
    """Helper to authenticate crew and return crew_id."""
    res = client.post(
        "/api/auth/crew",
        json={"username": "crew_demo", "password": CREW_TEST_PASSWORD},
    )
    assert res.status_code == 200, f"Crew login failed: {res.json}"
    return res.json["data"]["crew_id"]


# =============================================================================
# 1. Request Creation and Intent Validation
# =============================================================================

def test_valid_passenger_request_creation(client: FlaskClient):
    """Valid passenger request creates durable record, derives seat & priority, returns envelope."""
    _login_passenger(client, "18A", "0000")

    res = client.post(
        "/api/requests",
        json={"intent_id": "water_request"},
    )
    assert res.status_code == 201
    assert res.json["ok"] is True

    data = res.json["data"]
    request_id = data["request_id"]
    assert request_id and isinstance(request_id, str)
    assert data["seat_label"] == "18A"
    assert data["intent_id"] == "water_request"
    assert data["status"] == "PENDING"
    assert data["priority"] == "ROUTINE"
    assert isinstance(data["created_at"], int)

    # Verify durability in SQLite
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        assert row is not None
        assert row["seat_label"] == "18A"
        assert row["intent_id"] == "water_request"
        assert row["status"] == "PENDING"
        assert row["priority"] == "routine"

        # Verify audit event in request_events
        ev = conn.execute(
            "SELECT * FROM request_events WHERE request_id = ? AND event_type = 'CREATED'",
            (request_id,),
        ).fetchone()
        assert ev is not None
    finally:
        conn.close()


def test_urgent_request_priority_derivation(client: FlaskClient):
    """Urgent intent derives URGENT priority from canonical catalog."""
    _login_passenger(client, "18A", "0000")

    res = client.post(
        "/api/requests",
        json={"intent_id": "medical_help"},
    )
    assert res.status_code == 201
    assert res.json["ok"] is True
    assert res.json["data"]["priority"] == "URGENT"

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT priority FROM requests WHERE id = ?",
            (res.json["data"]["request_id"],),
        ).fetchone()
        assert row["priority"] == "urgent"
    finally:
        conn.close()


def test_missing_and_invalid_intent_rejected(client: FlaskClient):
    """Missing or invalid intent IDs and malformed payloads are rejected with 400."""
    _login_passenger(client, "18A", "0000")

    # Missing intent_id
    res1 = client.post("/api/requests", json={})
    assert res1.status_code == 400
    assert res1.json["ok"] is False
    assert res1.json["error"]["code"] == "INVALID_INTENT"

    # Invalid intent_id not in canonical catalog
    res2 = client.post("/api/requests", json={"intent_id": "invented_unknown_drink"})
    assert res2.status_code == 400
    assert res2.json["ok"] is False
    assert res2.json["error"]["code"] == "INVALID_INTENT"

    # Non-string intent_id
    res3 = client.post("/api/requests", json={"intent_id": 12345})
    assert res3.status_code == 400
    assert res3.json["ok"] is False

    # Non-JSON body
    res4 = client.post("/api/requests", data="plain text", content_type="text/plain")
    assert res4.status_code == 400
    assert res4.json["ok"] is False
    assert res4.json["error"]["code"] == "BAD_REQUEST"

    # Confirm no requests were created
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        assert count == 0
    finally:
        conn.close()


# =============================================================================
# 2. Authorization and Spoofing Prevention
# =============================================================================

def test_unauthenticated_request_endpoints(client: FlaskClient):
    """Unauthenticated access to request endpoints returns 401 UNAUTHENTICATED."""
    res1 = client.post("/api/requests", json={"intent_id": "water_request"})
    assert res1.status_code == 401
    assert res1.json["error"]["code"] == "UNAUTHENTICATED"

    res2 = client.get("/api/passenger/state")
    assert res2.status_code == 401
    assert res2.json["error"]["code"] == "UNAUTHENTICATED"

    res3 = client.get("/api/crew/requests")
    assert res3.status_code == 401
    assert res3.json["error"]["code"] == "UNAUTHENTICATED"

    res4 = client.post("/api/crew/requests/any-id/acknowledge")
    assert res4.status_code == 401
    assert res4.json["error"]["code"] == "UNAUTHENTICATED"

    res5 = client.post("/api/crew/requests/any-id/complete")
    assert res5.status_code == 401
    assert res5.json["error"]["code"] == "UNAUTHENTICATED"


def test_passenger_identity_and_seat_spoofing_prevented(client: FlaskClient):
    """Client cannot override seat, role, priority, or status in request body."""
    _login_passenger(client, "18A", "0000")

    # Attacker attempts to forge seat 32D, priority URGENT, and status COMPLETED
    res = client.post(
        "/api/requests",
        json={
            "intent_id": "water_request",
            "seat_label": "32D",
            "priority": "URGENT",
            "status": "COMPLETED",
        },
    )
    assert res.status_code == 201
    data = res.json["data"]

    # Seat must come from authenticated session (18A)
    assert data["seat_label"] == "18A"
    assert data["priority"] == "ROUTINE"
    assert data["status"] == "PENDING"

    # Verify database state matches
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM requests WHERE id = ?", (data["request_id"],)).fetchone()
        assert row["seat_label"] == "18A"
        assert row["priority"] == "routine"
        assert row["status"] == "PENDING"
    finally:
        conn.close()


def test_cross_passenger_isolation(app: Any):
    """Passenger cannot inspect or mutate another passenger's requests."""
    client_a = app.test_client()
    client_b = app.test_client()

    # Passenger A (18A) creates a request
    _login_passenger(client_a, "18A", "0000")
    res_a = client_a.post("/api/requests", json={"intent_id": "water_request"})
    req_a_id = res_a.json["data"]["request_id"]

    # Passenger B (12A) creates a request
    _login_passenger(client_b, "12A", "DEMO-12A")
    res_b = client_b.post("/api/requests", json={"intent_id": "blanket_request"})
    req_b_id = res_b.json["data"]["request_id"]

    # State inspection for Passenger A
    state_a = client_a.get("/api/passenger/state").json["data"]
    req_ids_a = [r["id"] for r in state_a["requests"]]
    assert req_a_id in req_ids_a
    assert req_b_id not in req_ids_a

    # State inspection for Passenger B
    state_b = client_b.get("/api/passenger/state").json["data"]
    req_ids_b = [r["id"] for r in state_b["requests"]]
    assert req_b_id in req_ids_b
    assert req_a_id not in req_ids_b

    # Passenger B attempts to follow up on Passenger A's request
    cross_res = client_b.post(
        f"/api/crew/requests/{req_a_id}/follow_up",
        json={"message": "Cross-passenger tamper attempt"},
    )
    assert cross_res.status_code == 404
    assert cross_res.json["ok"] is False


def test_crew_only_action_authorization(app: Any):
    """Passenger cannot access crew routes; crew cannot access passenger submission routes."""
    client_passenger = app.test_client()
    client_crew = app.test_client()

    _login_passenger(client_passenger, "18A", "0000")
    _login_crew(client_crew)

    # Passenger tries crew actions
    res1 = client_passenger.get("/api/crew/requests")
    assert res1.status_code == 403
    assert res1.json["error"]["code"] == "FORBIDDEN"

    res2 = client_passenger.post("/api/crew/requests/fake-id/acknowledge")
    assert res2.status_code == 403
    assert res2.json["error"]["code"] == "FORBIDDEN"

    res3 = client_passenger.post("/api/crew/requests/fake-id/complete")
    assert res3.status_code == 403
    assert res3.json["error"]["code"] == "FORBIDDEN"

    # Crew tries passenger actions
    res4 = client_crew.post("/api/requests", json={"intent_id": "water_request"})
    assert res4.status_code == 403
    assert res4.json["error"]["code"] == "FORBIDDEN"

    res5 = client_crew.get("/api/passenger/state")
    assert res5.status_code == 403
    assert res5.json["error"]["code"] == "FORBIDDEN"


# =============================================================================
# 3. Request Lifecycle and State Transitions
# =============================================================================

def test_valid_request_lifecycle_transitions(app: Any):
    """Valid lifecycle: PENDING -> ACKNOWLEDGED -> COMPLETED."""
    passenger = app.test_client()
    crew = app.test_client()

    _login_passenger(passenger, "18A", "0000")
    _login_crew(crew)

    # 1. Create request -> PENDING
    create_res = passenger.post("/api/requests", json={"intent_id": "water_request"})
    assert create_res.status_code == 201
    request_id = create_res.json["data"]["request_id"]
    assert create_res.json["data"]["status"] == "PENDING"

    # 2. Acknowledge -> ACKNOWLEDGED
    ack_res = crew.post(
        f"/api/crew/requests/{request_id}/acknowledge",
        json={"response_id": "request_acknowledged"},
    )
    assert ack_res.status_code == 200
    assert ack_res.json["data"]["request"]["status"] == "ACKNOWLEDGED"
    assert ack_res.json["data"]["request"]["acknowledged_at_ms"] is not None

    # 3. Complete -> COMPLETED
    comp_res = crew.post(f"/api/crew/requests/{request_id}/complete")
    assert comp_res.status_code == 200
    assert comp_res.json["data"]["request"]["status"] == "COMPLETED"
    assert comp_res.json["data"]["request"]["completed_at_ms"] is not None

    # Check event history in request_events
    events = requests_service.get_request_events(request_id)
    event_types = [e["event_type"] for e in events]
    assert event_types == ["CREATED", "ACKNOWLEDGED", "COMPLETED"]


def test_invalid_lifecycle_transitions_rejected(app: Any):
    """Direct PENDING -> COMPLETED or backwards COMPLETED -> ACKNOWLEDGED are rejected."""
    passenger = app.test_client()
    crew = app.test_client()

    _login_passenger(passenger, "18A", "0000")
    _login_crew(crew)

    # 1. Create request -> PENDING
    create_res = passenger.post("/api/requests", json={"intent_id": "water_request"})
    request_id = create_res.json["data"]["request_id"]

    # Attempt to complete directly from PENDING without acknowledging
    bad_comp = crew.post(f"/api/crew/requests/{request_id}/complete")
    assert bad_comp.status_code == 409
    assert bad_comp.json["ok"] is False
    assert bad_comp.json["error"]["code"] == "INVALID_TRANSITION"

    # Verify status remains PENDING in database
    conn = get_connection()
    try:
        row = conn.execute("SELECT status FROM requests WHERE id = ?", (request_id,)).fetchone()
        assert row["status"] == "PENDING"
    finally:
        conn.close()

    # Legitimate acknowledge, then complete
    crew.post(f"/api/crew/requests/{request_id}/acknowledge")
    crew.post(f"/api/crew/requests/{request_id}/complete")

    # Attempt to acknowledge already COMPLETED request
    bad_ack = crew.post(f"/api/crew/requests/{request_id}/acknowledge")
    assert bad_ack.status_code == 409
    assert bad_ack.json["ok"] is False
    assert bad_ack.json["error"]["code"] == "INVALID_TRANSITION"


def test_idempotent_crew_actions(app: Any):
    """Repeated acknowledge or complete calls on the same request succeed idempotently."""
    passenger = app.test_client()
    crew = app.test_client()

    _login_passenger(passenger, "18A", "0000")
    _login_crew(crew)

    create_res = passenger.post("/api/requests", json={"intent_id": "water_request"})
    request_id = create_res.json["data"]["request_id"]

    # First acknowledge -> 200
    ack1 = crew.post(f"/api/crew/requests/{request_id}/acknowledge")
    assert ack1.status_code == 200
    assert ack1.json["data"]["request"]["status"] == "ACKNOWLEDGED"

    # Repeated acknowledge -> 200 idempotent
    ack2 = crew.post(f"/api/crew/requests/{request_id}/acknowledge")
    assert ack2.status_code == 200
    assert ack2.json["data"]["request"]["status"] == "ACKNOWLEDGED"

    # First complete -> 200
    comp1 = crew.post(f"/api/crew/requests/{request_id}/complete")
    assert comp1.status_code == 200
    assert comp1.json["data"]["request"]["status"] == "COMPLETED"

    # Repeated complete -> 200 idempotent
    comp2 = crew.post(f"/api/crew/requests/{request_id}/complete")
    assert comp2.status_code == 200
    assert comp2.json["data"]["request"]["status"] == "COMPLETED"


# =============================================================================
# 4. Deduplication and Idempotency
# =============================================================================

def test_active_request_deduplication(app: Any):
    """Duplicate submission for the same seat and intent returns the existing active request."""
    passenger = app.test_client()
    crew = app.test_client()

    _login_passenger(passenger, "18A", "0000")
    _login_crew(crew)

    # 1. First submission creates request R1
    res1 = passenger.post("/api/requests", json={"intent_id": "water_request"})
    assert res1.status_code == 201
    r1_id = res1.json["data"]["request_id"]

    # 2. Duplicate submission while R1 is PENDING returns R1 with 200 OK
    res2 = passenger.post("/api/requests", json={"intent_id": "water_request"})
    assert res2.status_code == 200
    assert res2.json["data"]["request_id"] == r1_id

    # Verify crew queue has only 1 item
    queue1 = crew.get("/api/crew/requests").json["data"]["requests"]
    assert len(queue1) == 1
    assert queue1[0]["id"] == r1_id

    # 3. Move R1 to ACKNOWLEDGED
    crew.post(f"/api/crew/requests/{r1_id}/acknowledge")

    # Duplicate submission while R1 is ACKNOWLEDGED still returns R1
    res3 = passenger.post("/api/requests", json={"intent_id": "water_request"})
    assert res3.status_code == 200
    assert res3.json["data"]["request_id"] == r1_id

    # 4. Complete R1
    crew.post(f"/api/crew/requests/{r1_id}/complete")

    # 5. After completion, a new request for the same intent can be created
    res4 = passenger.post("/api/requests", json={"intent_id": "water_request"})
    assert res4.status_code == 201
    r2_id = res4.json["data"]["request_id"]
    assert r2_id != r1_id

    # Database now contains two requests (one COMPLETED, one PENDING)
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, status FROM requests ORDER BY created_at_ms").fetchall()
        assert len(rows) == 2
        assert rows[0]["id"] == r1_id and rows[0]["status"] == "COMPLETED"
        assert rows[1]["id"] == r2_id and rows[1]["status"] == "PENDING"
    finally:
        conn.close()


def test_idempotency_key_replay_and_conflict(client: FlaskClient):
    """Same client_request_id returns original request; conflicting intent returns 409."""
    _login_passenger(client, "18A", "0000")

    key = "idem-key-unique-12345"

    # 1. First submission with client_request_id
    res1 = client.post(
        "/api/requests",
        json={"intent_id": "water_request", "client_request_id": key},
    )
    assert res1.status_code == 201
    orig_id = res1.json["data"]["request_id"]

    # 2. Retrying identical request with same key returns original request
    res2 = client.post(
        "/api/requests",
        json={"intent_id": "water_request", "client_request_id": key},
    )
    assert res2.status_code == 200
    assert res2.json["data"]["request_id"] == orig_id

    # 3. Conflicting reuse of same key for a different intent is rejected
    res3 = client.post(
        "/api/requests",
        json={"intent_id": "blanket_request", "client_request_id": key},
    )
    assert res3.status_code == 409
    assert res3.json["ok"] is False
    assert res3.json["error"]["code"] == "IDEMPOTENCY_CONFLICT"


# =============================================================================
# 5. Crew Queue Priority and FIFO Ordering
# =============================================================================

def test_crew_queue_priority_and_fifo_ordering(app: Any):
    """Urgent requests sort before routine requests; FIFO within each priority."""
    crew = app.test_client()
    _login_crew(crew)

    p1 = app.test_client()
    p2 = app.test_client()
    p3 = app.test_client()
    p4 = app.test_client()

    _login_passenger(p1, "18A", "0000")
    _login_passenger(p2, "12A", "DEMO-12A")
    _login_passenger(p3, "12B", "DEMO-12B")
    _login_passenger(p4, "12C", "DEMO-12C")

    # Submit 4 requests in interleaved order:
    # 1. Routine 1 (18A, pillow)
    res_r1 = p1.post("/api/requests", json={"intent_id": "pillow_request"})
    # 2. Urgent 1 (12A, safety_concern)
    res_u1 = p2.post("/api/requests", json={"intent_id": "safety_concern"})
    # 3. Routine 2 (12B, blanket)
    res_r2 = p3.post("/api/requests", json={"intent_id": "blanket_request"})
    # 4. Urgent 2 (12C, medical_help)
    res_u2 = p4.post("/api/requests", json={"intent_id": "medical_help"})

    u1_id = res_u1.json["data"]["request_id"]
    u2_id = res_u2.json["data"]["request_id"]
    r1_id = res_r1.json["data"]["request_id"]
    r2_id = res_r2.json["data"]["request_id"]

    # Fetch crew queue
    queue = crew.get("/api/crew/requests").json["data"]["requests"]
    queue_ids = [r["id"] for r in queue]

    # Expected order: U1, U2, R1, R2
    assert queue_ids == [u1_id, u2_id, r1_id, r2_id], (
        f"Queue did not match expected urgent-first FIFO order: {queue_ids}"
    )


# =============================================================================
# 6. Persistence Across Reconnect and Socket.IO Realtime Delivery
# =============================================================================

def test_persistence_across_connection_reopen(client: FlaskClient):
    """Requests survive database connection closing and are recoverable via passenger state."""
    _login_passenger(client, "18A", "0000")
    create_res = client.post("/api/requests", json={"intent_id": "water_request"})
    request_id = create_res.json["data"]["request_id"]

    # Verify a brand new connection to SQLite reads the committed data
    new_conn = get_connection()
    try:
        row = new_conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        assert row is not None
        assert row["id"] == request_id
    finally:
        new_conn.close()

    # Passenger state retrieval recovers state after browser reload/reconnect
    state = client.get("/api/passenger/state").json["data"]
    assert any(r["id"] == request_id for r in state["requests"])


def test_socketio_request_notifications(app: Any):
    """Socket.IO emits request_created to crew and request_updated to passenger post-commit."""
    from app import socketio

    crew_client = app.test_client()
    pass_client = app.test_client()

    _login_crew(crew_client)
    pass_session_id = _login_passenger(pass_client, "18A", "0000")

    # Connect Socket.IO clients with their authenticated session cookies
    crew_socket = socketio.test_client(app, flask_test_client=crew_client)
    pass_socket = socketio.test_client(app, flask_test_client=pass_client)

    assert crew_socket.is_connected()
    assert pass_socket.is_connected()

    # Flush connection ready events
    crew_socket.get_received()
    pass_socket.get_received()

    # Passenger creates request via REST
    res = pass_client.post("/api/requests", json={"intent_id": "water_request"})
    assert res.status_code == 201
    created_id = res.json["data"]["request_id"]

    # Verify crew dashboard received 'request_created'
    crew_events = crew_socket.get_received()
    created_ev = next((e for e in crew_events if e["name"] == "request_created"), None)
    assert created_ev is not None
    assert created_ev["args"][0]["request"]["request_id"] == created_id

    # Verify passenger received 'request_updated'
    pass_events = pass_socket.get_received()
    pass_updated_ev = next((e for e in pass_events if e["name"] == "request_updated"), None)
    assert pass_updated_ev is not None
    assert pass_updated_ev["args"][0]["request_id"] == created_id

    # A failed request (e.g. invalid intent) must NOT emit Socket.IO events
    pass_client.post("/api/requests", json={"intent_id": "non_existent"})
    assert len(crew_socket.get_received()) == 0
    assert len(pass_socket.get_received()) == 0

    crew_socket.disconnect()
    pass_socket.disconnect()
