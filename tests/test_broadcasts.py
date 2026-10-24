"""Comprehensive tests for SoraLink PA broadcast persistence, authorization, and realtime events.

Covers:
- Authenticated crew broadcast creation
- Server-side validation of PA card ID against approved catalog
- Rejection of client-supplied announcement text and spoofed metadata
- Unauthenticated and passenger authorization enforcement
- Durability across database connection close and reopen
- Active broadcast retrieval and late-join/reconnect recovery
- Expiration exclusion based on authoritative integer *_ms convention
- Idempotent broadcast termination
- Socket.IO emissions occurring strictly after database commit
- No Socket.IO emissions on persistence failure
- Crew broadcast queue listing
"""

from __future__ import annotations

import sqlite3
from typing import Any
import pytest
from flask.testing import FlaskClient

from database import get_connection, now_ms
import broadcast_service


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
# 1. Crew Broadcast Creation & Catalog Validation
# =============================================================================

def test_valid_crew_broadcast_creation(client: FlaskClient):
    """Crew can create a broadcast referencing an approved PA card."""
    _login_crew(client)

    res = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "boarding_update"},
    )
    assert res.status_code == 201, f"Creation failed: {res.json}"
    data = res.json["data"]

    assert data["pa_card_id"] == "boarding_update"
    assert data["broadcast_id"]
    assert data["title"] == "Boarding update"
    assert "Boarding is in progress" in data["body"]
    assert data["category"] == "boarding"
    assert data["active_status"] is True
    assert isinstance(data["created_at_ms"], int)
    assert isinstance(data["expires_at_ms"], int)
    # Default TTL for boarding_update is 120s
    assert data["expires_at_ms"] - data["created_at_ms"] == 120 * 1000

    # Custom duration test within bounds
    res_custom = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "turbulence", "duration_seconds": 300},
    )
    assert res_custom.status_code == 201
    custom_data = res_custom.json["data"]
    assert custom_data["expires_at_ms"] - custom_data["created_at_ms"] == 300 * 1000


def test_invalid_or_unknown_pa_card_rejected(client: FlaskClient):
    """Unknown, missing, or malformed PA card IDs must be rejected."""
    _login_crew(client)

    # Missing pa_card_id
    res_empty = client.post("/api/crew/pa/broadcast", json={})
    assert res_empty.status_code == 400
    assert res_empty.json["ok"] is False
    assert res_empty.json["error"]["code"] == "INVALID_CARD"

    # Non-string pa_card_id
    res_type = client.post("/api/crew/pa/broadcast", json={"pa_card_id": 123})
    assert res_type.status_code == 400
    assert res_type.json["error"]["code"] == "INVALID_CARD"

    # Unknown pa_card_id
    res_unknown = client.post("/api/crew/pa/broadcast", json={"pa_card_id": "unapproved_emergency_alert"})
    assert res_unknown.status_code == 400
    assert res_unknown.json["error"]["code"] == "INVALID_BROADCAST"
    assert "Unknown PA card ID" in res_unknown.json["error"]["message"]

    # Invalid duration bounds (negative or exceeding max 30 min)
    res_duration_low = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "turbulence", "duration_seconds": 0},
    )
    assert res_duration_low.status_code == 400

    res_duration_high = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "turbulence", "duration_seconds": 999999},
    )
    assert res_duration_high.status_code == 400


# =============================================================================
# 2. Text Rejection & Spoofing Prevention
# =============================================================================

def test_rejection_of_client_supplied_text_and_spoofed_metadata(client: FlaskClient):
    """The backend rejects client attempts to supply custom text or spoof metadata."""
    _login_crew(client)

    # Rejection of client-supplied announcement body/text
    res_custom_body = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "boarding_update", "body": "Malicious arbitrary announcement"},
    )
    assert res_custom_body.status_code == 400
    assert res_custom_body.json["error"]["code"] == "INVALID_BROADCAST"
    assert "Client-supplied announcement text is not permitted" in res_custom_body.json["error"]["message"]

    res_custom_title = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "boarding_update", "title": "Fake Title"},
    )
    assert res_custom_title.status_code == 400
    assert res_custom_title.json["error"]["code"] == "INVALID_BROADCAST"

    # Rejection of spoofed metadata
    res_spoof_creator = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "boarding_update", "created_by": "hacked_admin"},
    )
    assert res_spoof_creator.status_code == 400
    assert res_spoof_creator.json["error"]["code"] == "INVALID_METADATA"

    res_spoof_time = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "boarding_update", "created_at": 1000},
    )
    assert res_spoof_time.status_code == 400
    assert res_spoof_time.json["error"]["code"] == "INVALID_METADATA"

    res_spoof_status = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "boarding_update", "active_status": False},
    )
    assert res_spoof_status.status_code == 400
    assert res_spoof_status.json["error"]["code"] == "INVALID_METADATA"


# =============================================================================
# 3. Authorization and Role Isolation
# =============================================================================

def test_unauthenticated_and_passenger_attempts_rejected(client: FlaskClient):
    """Unauthenticated users and passengers cannot create, end, or view crew broadcast routes."""
    # Unauthenticated access
    res_unauth_create = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "boarding_update"},
    )
    assert res_unauth_create.status_code == 401
    assert res_unauth_create.json["error"]["code"] == "UNAUTHENTICATED"

    res_unauth_end = client.post(
        "/api/crew/pa/end",
        json={"broadcast_id": "any-id"},
    )
    assert res_unauth_end.status_code == 401

    res_unauth_list = client.get("/api/crew/broadcasts")
    assert res_unauth_list.status_code == 401

    res_unauth_cards = client.get("/api/crew/pa/cards")
    assert res_unauth_cards.status_code == 401

    # Passenger authenticated attempts
    _login_passenger(client, seat_label="18A")

    res_pass_create = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "boarding_update"},
    )
    assert res_pass_create.status_code == 403
    assert res_pass_create.json["error"]["code"] == "FORBIDDEN"

    res_pass_end = client.post(
        "/api/crew/pa/end",
        json={"broadcast_id": "any-id"},
    )
    assert res_pass_end.status_code == 403

    res_pass_list = client.get("/api/crew/broadcasts")
    assert res_pass_list.status_code == 403

    res_pass_cards = client.get("/api/crew/pa/cards")
    assert res_pass_cards.status_code == 403


# =============================================================================
# 4. Persistence and Recovery
# =============================================================================

def test_persistence_across_connection_reopen(client: FlaskClient):
    """Broadcast state persists durably in SQLite across independent connections."""
    _login_crew(client)

    res = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "meal_service"},
    )
    assert res.status_code == 201
    broadcast_id = res.json["data"]["broadcast_id"]

    # Open a completely fresh SQLite connection to verify storage
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM active_broadcasts WHERE id = ?",
            (broadcast_id,),
        ).fetchone()
        assert row is not None, "Broadcast was not found in SQLite"
        assert row["pa_card_id"] == "meal_service"
        assert row["title"] == "Meal service"
        assert "Meal and beverage service is in progress" in row["body"]
        assert row["category"] == "service"
        assert row["ended_at_ms"] is None
        assert row["expires_at_ms"] > row["created_at_ms"]
    finally:
        conn.close()


def test_active_broadcast_retrieval_and_passenger_recovery(client: FlaskClient):
    """Active broadcasts are retrievable by passengers and survive reconnect/refresh."""
    # Crew creates announcement
    _login_crew(client)
    res_create = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "turbulence"},
    )
    assert res_create.status_code == 201
    b_id = res_create.json["data"]["broadcast_id"]

    # Passenger logs in (simulating client refresh or reconnect)
    _login_passenger(client, seat_label="14B", demo_code="DEMO-14B")

    # Verify retrieval on GET /api/passenger/state
    res_state = client.get("/api/passenger/state")
    assert res_state.status_code == 200
    active = res_state.json["data"]["active_broadcasts"]
    assert len(active) >= 1
    found = next((b for b in active if b["broadcast_id"] == b_id or b["id"] == b_id), None)
    assert found is not None
    assert found["pa_card_id"] == "turbulence"
    assert found["title"] == "Turbulence reminder"
    assert found["active_status"] is True

    # Verify retrieval on GET /api/passenger/broadcasts and GET /api/pa/active
    res_broadcasts = client.get("/api/passenger/broadcasts")
    assert res_broadcasts.status_code == 200
    b_list = res_broadcasts.json["data"]["broadcasts"]
    assert any(b["id"] == b_id for b in b_list)

    res_active = client.get("/api/pa/active")
    assert res_active.status_code == 200
    assert any(b["id"] == b_id for b in res_active.json["data"]["broadcasts"])


def test_expired_broadcast_exclusion(client: FlaskClient, monkeypatch: pytest.MonkeyPatch):
    """Announcements past their expiry timestamp are excluded from active state."""
    _login_crew(client)

    # Simulated start time
    base_time = 1_700_000_000_000
    monkeypatch.setattr(broadcast_service, "now_ms", lambda: base_time)

    res_create = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "cabin_crew_assistance", "duration_seconds": 60},
    )
    assert res_create.status_code == 201
    b_id = res_create.json["data"]["broadcast_id"]

    # 30 seconds later: broadcast is still active
    monkeypatch.setattr(broadcast_service, "now_ms", lambda: base_time + 30_000)
    active_midway = broadcast_service.list_active_broadcasts()
    assert any(b["id"] == b_id for b in active_midway)

    # 70 seconds later: broadcast has expired
    monkeypatch.setattr(broadcast_service, "now_ms", lambda: base_time + 70_000)
    active_after = broadcast_service.list_active_broadcasts()
    assert not any(b["id"] == b_id for b in active_after)

    _login_passenger(client, seat_label="18A")
    res_state = client.get("/api/passenger/state")
    assert res_state.status_code == 200
    passenger_active = res_state.json["data"]["active_broadcasts"]
    assert not any(b["id"] == b_id for b in passenger_active)


# =============================================================================
# 5. Broadcast Termination & Idempotency
# =============================================================================

def test_crew_end_broadcast_and_idempotency(client: FlaskClient):
    """Crew can end an active broadcast; repeat termination calls succeed idempotently."""
    _login_crew(client)

    res_create = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "lavatory_queue"},
    )
    assert res_create.status_code == 201
    b_id = res_create.json["data"]["broadcast_id"]

    # End the broadcast
    res_end = client.post(
        "/api/crew/pa/end",
        json={"broadcast_id": b_id},
    )
    assert res_end.status_code == 200
    assert res_end.json["data"]["broadcast_id"] == b_id
    assert res_end.json["data"]["ended_at"] is not None

    # Idempotent repeat call: ending again succeeds without error
    res_end_repeat = client.post(
        "/api/crew/pa/end",
        json={"broadcast_id": b_id},
    )
    assert res_end_repeat.status_code == 200
    assert res_end_repeat.json["data"]["broadcast_id"] == b_id

    # Alternate route: PATCH /api/crew/pa/broadcast/<id>
    res_patch = client.patch(f"/api/crew/pa/broadcast/{b_id}")
    assert res_patch.status_code == 200

    # Verify excluded from passenger active list
    _login_passenger(client, seat_label="18A")
    res_state = client.get("/api/passenger/state")
    assert not any(b["id"] == b_id for b in res_state.json["data"]["active_broadcasts"])

    # Non-existent broadcast termination returns 404
    _login_crew(client)
    res_not_found = client.post(
        "/api/crew/pa/end",
        json={"broadcast_id": "non-existent-uuid-999"},
    )
    assert res_not_found.status_code == 404
    assert res_not_found.json["error"]["code"] == "NOT_FOUND"


def test_crew_list_broadcasts(client: FlaskClient):
    """Crew can list active broadcasts and full history via query parameter."""
    _login_crew(client)

    res1 = client.post("/api/crew/pa/broadcast", json={"pa_card_id": "boarding_update"})
    res2 = client.post("/api/crew/pa/broadcast", json={"pa_card_id": "arrival_preparation"})
    b1_id = res1.json["data"]["broadcast_id"]
    b2_id = res2.json["data"]["broadcast_id"]

    # End broadcast 1
    client.post("/api/crew/pa/end", json={"broadcast_id": b1_id})

    # Default list returns only active
    res_active = client.get("/api/crew/broadcasts")
    assert res_active.status_code == 200
    active_ids = [b["id"] for b in res_active.json["data"]["broadcasts"]]
    assert b2_id in active_ids
    assert b1_id not in active_ids

    # Query with include_inactive=true returns both
    res_all = client.get("/api/crew/broadcasts?include_inactive=true")
    assert res_all.status_code == 200
    all_ids = [b["id"] for b in res_all.json["data"]["broadcasts"]]
    assert b1_id in all_ids
    assert b2_id in all_ids


# =============================================================================
# 6. Socket.IO Integrity & Failure Handling
# =============================================================================

def test_socketio_notifications_emitted_only_after_commit(app, client: FlaskClient, monkeypatch: pytest.MonkeyPatch):
    """Socket.IO notifications are emitted only after the SQLite transaction has committed."""
    _login_crew(client)

    emitted_events: list[dict[str, Any]] = []

    from app import socketio

    original_emit = socketio.emit

    def spy_emit(event: str, *args: Any, **kwargs: Any):
        # Assert database state at the precise moment of emission
        if event == "pa_broadcast_created":
            item = args[0] if args else kwargs.get("data")
            b_id = item["id"]
            conn = get_connection()
            try:
                row = conn.execute(
                    "SELECT id, ended_at_ms FROM active_broadcasts WHERE id = ?",
                    (b_id,),
                ).fetchone()
                assert row is not None, f"Row {b_id} was not in database when {event} was emitted!"
            finally:
                conn.close()

        if event == "pa_broadcast_ended":
            item = args[0] if args else kwargs.get("data")
            b_id = item["id"]
            conn = get_connection()
            try:
                row = conn.execute(
                    "SELECT id, ended_at_ms FROM active_broadcasts WHERE id = ?",
                    (b_id,),
                ).fetchone()
                assert row is not None
                assert row["ended_at_ms"] is not None, f"Broadcast {b_id} ended_at_ms not committed when {event} emitted!"
            finally:
                conn.close()

        emitted_events.append({"event": event, "args": args, "kwargs": kwargs})
        return original_emit(event, *args, **kwargs)

    monkeypatch.setattr(socketio, "emit", spy_emit)

    # Create broadcast
    res_create = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "turbulence"},
    )
    assert res_create.status_code == 201
    b_id = res_create.json["data"]["broadcast_id"]

    created_events = [e["event"] for e in emitted_events]
    assert "pa_broadcast_created" in created_events
    assert "announcement_created" not in created_events

    # End broadcast
    emitted_events.clear()
    res_end = client.post(
        "/api/crew/pa/end",
        json={"broadcast_id": b_id},
    )
    assert res_end.status_code == 200

    ended_events = [e["event"] for e in emitted_events]
    assert "pa_broadcast_ended" in ended_events
    assert "announcement_ended" not in ended_events


def test_no_socketio_notification_on_persistence_failure(app, client: FlaskClient, monkeypatch: pytest.MonkeyPatch):
    """If database persistence fails, no Socket.IO notification is emitted."""
    _login_crew(client)

    from app import socketio

    emitted_events: list[str] = []
    monkeypatch.setattr(
        socketio,
        "emit",
        lambda event, *args, **kwargs: emitted_events.append(event),
    )

    # Force database write failure
    def failing_create(*args, **kwargs):
        raise sqlite3.OperationalError("Simulated disk I/O failure")

    monkeypatch.setattr(broadcast_service, "create_broadcast", failing_create)

    res = client.post(
        "/api/crew/pa/broadcast",
        json={"pa_card_id": "turbulence"},
    )
    assert res.status_code == 500
    assert res.json["ok"] is False

    # Verify no Socket.IO events were emitted
    assert "pa_broadcast_created" not in emitted_events
    assert "announcement_created" not in emitted_events


# =============================================================================
# 7. Approved PA Cards Catalog Endpoints
# =============================================================================

def test_pa_cards_catalog_endpoints(client: FlaskClient):
    """Cards catalog is accessible to crew and passengers."""
    _login_crew(client)
    res_crew = client.get("/api/crew/pa/cards")
    assert res_crew.status_code == 200
    cards_crew = res_crew.json["data"]["cards"]
    assert len(cards_crew) >= 6
    ids = {c["id"] for c in cards_crew}
    assert "boarding_update" in ids
    assert "turbulence" in ids

    # Public content endpoint
    res_content = client.get("/api/content/pa_cards")
    assert res_content.status_code == 200
    cards_content = res_content.json["data"]["cards"]
    assert len(cards_content) >= 6
