"""Regression and acceptance tests for dual-role sessions, request persistence, and crew replies.

Covers:
- Dual-role coexistence in the same client/cookie jar
- Independent role logout (logging out crew preserves passenger and vice versa)
- Passenger request persistence across re-login (same seat, rotated session ID)
- Crew predefined reply delivery via Socket.IO seat room
- Request status and reply persistence across refresh / GET /api/passenger/state
- Passenger follow-up submission across re-login
- Cross-role authorization isolation
"""

from __future__ import annotations

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import socketio

CREW_PASSWORD = "test-crew-password-xyz"


@pytest.fixture(autouse=True)
def configure_crew(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SORALINK_CREW_CODE", CREW_PASSWORD)
    monkeypatch.setenv("SORALINK_CREW_USERNAME", "crew_demo")


# =============================================================================
# 1. Dual-role coexistence in the same cookie jar / browser
# =============================================================================

def test_dual_role_coexistence_in_same_client(client: FlaskClient):
    """Logging into crew in the same client does NOT destroy the passenger session."""
    # 1. Login as passenger
    res_p = client.post("/api/auth/passenger", json={"seat_label": "18A", "demo_code": "0000"})
    assert res_p.status_code == 200
    p_sid = res_p.json["data"]["session_id"]

    # 2. Login as crew in the same client / cookie jar
    res_c = client.post("/api/auth/crew", json={"username": "crew_demo", "password": CREW_PASSWORD})
    assert res_c.status_code == 200
    c_sid = res_c.json["data"]["crew_id"]

    # 3. Passenger state endpoint still returns 200 and belongs to passenger
    res_p_state = client.get("/api/passenger/state")
    assert res_p_state.status_code == 200
    assert res_p_state.json["ok"] is True
    assert res_p_state.json["data"]["seat_label"] == "18A"

    # 4. Crew requests endpoint still returns 200 and belongs to crew
    res_c_reqs = client.get("/api/crew/requests")
    assert res_c_reqs.status_code == 200
    assert res_c_reqs.json["ok"] is True

    # 5. Role inspection with role hints
    res_me_p = client.get("/api/auth/me?role=passenger")
    assert res_me_p.status_code == 200
    assert res_me_p.json["data"]["role"] == "passenger"
    assert res_me_p.json["data"]["seat_label"] == "18A"

    res_me_c = client.get("/api/auth/me?role=crew")
    assert res_me_c.status_code == 200
    assert res_me_c.json["data"]["role"] == "crew"
    assert res_me_c.json["data"]["crew_id"] == c_sid


# =============================================================================
# 2. Independent role logout
# =============================================================================

def test_role_specific_logout_preserves_other_role(client: FlaskClient):
    """Logging out of crew leaves passenger session intact; logging out of passenger leaves crew intact."""
    # Authenticate both roles in same client
    client.post("/api/auth/passenger", json={"seat_label": "18A", "demo_code": "0000"})
    client.post("/api/auth/crew", json={"username": "crew_demo", "password": CREW_PASSWORD})

    # Log out crew specifically
    res_out_c = client.post("/api/auth/logout?role=crew")
    assert res_out_c.status_code == 200

    # Crew session is unauthenticated, crew endpoints rejected
    assert client.get("/api/auth/me?role=crew").status_code == 401
    assert client.get("/api/crew/requests").status_code in (401, 403)

    # Passenger remains authenticated and functional
    res_p = client.get("/api/passenger/state")
    assert res_p.status_code == 200
    assert res_p.json["data"]["seat_label"] == "18A"
    assert client.get("/api/auth/me?role=passenger").status_code == 200

    # Re-login crew, then log out passenger specifically
    client.post("/api/auth/crew", json={"username": "crew_demo", "password": CREW_PASSWORD})
    res_out_p = client.post("/api/auth/logout?role=passenger")
    assert res_out_p.status_code == 200

    # Passenger session is unauthenticated, passenger endpoints rejected
    assert client.get("/api/auth/me?role=passenger").status_code == 401
    assert client.get("/api/passenger/state").status_code in (401, 403)

    # Crew remains authenticated and functional
    assert client.get("/api/crew/requests").status_code == 200
    assert client.get("/api/auth/me?role=crew").status_code == 200


# =============================================================================
# 3. Passenger request persistence across re-login & role switching
# =============================================================================

def test_request_persistence_and_crew_reply_across_relogin(app: Flask):
    """Requests and crew replies persist across passenger re-login (new session ID) and role switching."""
    client_p = app.test_client()
    client_c = app.test_client()

    # 1. Passenger logs in and creates request
    res_p_login1 = client_p.post("/api/auth/passenger", json={"seat_label": "18A", "demo_code": "0000"})
    sid_1 = res_p_login1.json["data"]["session_id"]

    res_create = client_p.post("/api/requests", json={"intent_id": "water_request"})
    assert res_create.status_code == 201
    req_id = res_create.json["data"]["request_id"]

    # 2. Crew logs in and acknowledges with a canned response
    client_c.post("/api/auth/crew", json={"username": "crew_demo", "password": CREW_PASSWORD})
    res_ack = client_c.post(
        f"/api/crew/requests/{req_id}/acknowledge",
        json={"response_id": "crew_on_the_way"},
    )
    assert res_ack.status_code == 200
    assert res_ack.json["data"]["request"]["status"] == "ACKNOWLEDGED"

    # 3. Passenger logs out and logs in again (session rotation, brand new session ID)
    client_p.post("/api/auth/logout?role=passenger")
    res_p_login2 = client_p.post("/api/auth/passenger", json={"seat_label": "18A", "demo_code": "0000"})
    sid_2 = res_p_login2.json["data"]["session_id"]
    assert sid_1 != sid_2

    # 4. Fetch passenger state with the new session
    res_state = client_p.get("/api/passenger/state")
    assert res_state.status_code == 200
    reqs = res_state.json["data"]["requests"]
    assert len(reqs) == 1
    persisted_req = reqs[0]

    # Verify request fields, status, and persisted crew reply
    assert persisted_req["id"] == req_id
    assert persisted_req["seat_label"] == "18A"
    assert persisted_req["status"] == "ACKNOWLEDGED"
    assert persisted_req["crew_reply_id"] == "crew_on_the_way"
    assert persisted_req["crew_reply_text_en"] is not None
    assert persisted_req["crew_reply_text_ja"] is not None

    # 5. Passenger can send follow-up note across re-login
    res_fu = client_p.post(
        f"/api/crew/requests/{req_id}/follow_up",
        json={"message": "With ice please"},
    )
    assert res_fu.status_code == 200

    # 6. Crew completes the request
    res_comp = client_c.post(f"/api/crew/requests/{req_id}/complete")
    assert res_comp.status_code == 200

    # 7. Passenger state reflects COMPLETED status
    res_state_final = client_p.get("/api/passenger/state")
    assert res_state_final.status_code == 200
    assert res_state_final.json["data"]["requests"][0]["status"] == "COMPLETED"


# =============================================================================
# 4. Real-time crew reply delivered to seat room
# =============================================================================

def test_crew_reply_realtime_delivered_to_seat_room(app: Flask):
    """Crew reply is emitted to passenger seat room and received by reconnected passenger."""
    client_p18 = app.test_client()
    client_p12 = app.test_client()
    client_c = app.test_client()

    client_p18.post("/api/auth/passenger", json={"seat_label": "18A", "demo_code": "0000"})
    client_p12.post("/api/auth/passenger", json={"seat_label": "12A", "demo_code": "DEMO-12A"})
    client_c.post("/api/auth/crew", json={"username": "crew_demo", "password": CREW_PASSWORD})

    sock_p18 = socketio.test_client(app, flask_test_client=client_p18)
    sock_p12 = socketio.test_client(app, flask_test_client=client_p12)
    sock_c = socketio.test_client(app, flask_test_client=client_c)

    # 18A creates request
    res_req = client_p18.post("/api/requests", json={"intent_id": "blanket_request"})
    req_id = res_req.json["data"]["request_id"]

    # Clear initial connection events
    sock_p18.get_received()
    sock_p12.get_received()
    sock_c.get_received()

    # Crew acknowledges with reply
    res_ack = client_c.post(
        f"/api/crew/requests/{req_id}/acknowledge",
        json={"response_id": "request_acknowledged"},
    )
    assert res_ack.status_code == 200

    events_18 = sock_p18.get_received()
    events_12 = sock_p12.get_received()

    # 18A received request_updated and crew_reply
    reply_events_18 = [e for e in events_18 if e["name"] == "crew_reply"]
    assert len(reply_events_18) == 1
    assert reply_events_18[0]["args"][0]["request_id"] == req_id
    assert reply_events_18[0]["args"][0]["response_id"] == "request_acknowledged"

    # 12A must NOT receive 18A's reply
    reply_events_12 = [e for e in events_12 if e["name"] == "crew_reply"]
    assert len(reply_events_12) == 0


# =============================================================================
# 5. Real-time delivery to passenger who rotated session
# =============================================================================

def test_realtime_delivery_after_session_rotation(app: Flask):
    """When passenger re-logs in and gets a new session, socket in seat room receives updates."""
    client_p = app.test_client()
    client_c = app.test_client()

    # Initial login & request
    client_p.post("/api/auth/passenger", json={"seat_label": "18A", "demo_code": "0000"})
    res_req = client_p.post("/api/requests", json={"intent_id": "tea_coffee"})
    req_id = res_req.json["data"]["request_id"]

    # Re-login (session rotation)
    client_p.post("/api/auth/passenger", json={"seat_label": "18A", "demo_code": "0000"})

    # Connect socket with new session
    sock_p = socketio.test_client(app, flask_test_client=client_p)
    sock_p.get_received()

    # Crew acknowledges request
    client_c.post("/api/auth/crew", json={"username": "crew_demo", "password": CREW_PASSWORD})
    client_c.post(
        f"/api/crew/requests/{req_id}/acknowledge",
        json={"response_id": "crew_on_the_way"},
    )

    # Verify new socket received both request_updated and crew_reply
    received = sock_p.get_received()
    assert any(e["name"] == "request_updated" and e["args"][0]["request_id"] == req_id for e in received)
    assert any(e["name"] == "crew_reply" and e["args"][0]["request_id"] == req_id for e in received)


# =============================================================================
# 6. Cross-role authorization isolation
# =============================================================================

def test_cross_role_authorization_isolation(client: FlaskClient):
    """Passenger cannot access crew routes and crew cannot access passenger routes."""
    # Passenger only
    client.post("/api/auth/passenger", json={"seat_label": "18A", "demo_code": "0000"})
    res_crew_forbidden = client.get("/api/crew/requests")
    assert res_crew_forbidden.status_code == 403

    # Log out passenger, login crew only
    client.post("/api/auth/logout?role=passenger")
    client.post("/api/auth/crew", json={"username": "crew_demo", "password": CREW_PASSWORD})
    res_pass_forbidden = client.post("/api/requests", json={"intent_id": "water_request"})
    assert res_pass_forbidden.status_code == 403


# =============================================================================
# 7. Role header isolation & Socket.IO dual session room routing
# =============================================================================

def test_role_header_isolation_and_socket_rooms(app: Flask):
    """X-SoraLink-Role header directs /api/auth/me and Socket.IO rooms correctly when both cookies exist."""
    client = app.test_client()

    # Authenticate both in the same cookie jar
    res_p = client.post("/api/auth/passenger", json={"seat_label": "18A", "demo_code": "0000"})
    assert res_p.status_code == 200
    res_c = client.post("/api/auth/crew", json={"username": "crew_demo", "password": CREW_PASSWORD})
    assert res_c.status_code == 200

    # /api/auth/me with X-SoraLink-Role header
    me_p = client.get("/api/auth/me", headers={"X-SoraLink-Role": "passenger"})
    assert me_p.status_code == 200
    assert me_p.json["data"]["role"] == "passenger"
    assert me_p.json["data"]["seat_label"] == "18A"

    me_c = client.get("/api/auth/me", headers={"X-SoraLink-Role": "crew"})
    assert me_c.status_code == 200
    assert me_c.json["data"]["role"] == "crew"

    # Socket connections with query string role
    sock_p = socketio.test_client(app, flask_test_client=client, query_string="role=passenger")
    sock_c = socketio.test_client(app, flask_test_client=client, query_string="role=crew")

    p_events = sock_p.get_received()
    c_events = sock_c.get_received()

    p_conn = next(e for e in p_events if e["name"] == "connection_ready")
    c_conn = next(e for e in c_events if e["name"] == "connection_ready")

    assert p_conn["args"][0]["role"] == "passenger"
    assert p_conn["args"][0]["seat_label"] == "18A"
    assert c_conn["args"][0]["role"] == "crew"

    # Passenger creates request -> crew receives request_created
    p_req = client.post(
        "/api/requests",
        json={"intent_id": "water_request"},
        headers={"X-SoraLink-Role": "passenger"},
    )
    assert p_req.status_code == 201
    req_id = p_req.json["data"]["id"]

    crew_received = sock_c.get_received()
    assert any(e["name"] == "request_created" and e["args"][0]["request"]["request_id"] == req_id for e in crew_received)

    # Crew acknowledges with response_id -> passenger receives crew_reply
    ack = client.post(
        f"/api/crew/requests/{req_id}/acknowledge",
        json={"response_id": "crew_on_the_way"},
        headers={"X-SoraLink-Role": "crew"},
    )
    assert ack.status_code == 200

    pass_received = sock_p.get_received()
    assert any(e["name"] == "crew_reply" and e["args"][0]["request_id"] == req_id for e in pass_received)

    # Logout crew using X-SoraLink-Role leaves passenger authenticated
    logout_c = client.post("/api/auth/logout", headers={"X-SoraLink-Role": "crew"})
    assert logout_c.status_code == 200
    assert client.get("/api/auth/me", headers={"X-SoraLink-Role": "crew"}).status_code == 401
    assert client.get("/api/auth/me", headers={"X-SoraLink-Role": "passenger"}).status_code == 200
