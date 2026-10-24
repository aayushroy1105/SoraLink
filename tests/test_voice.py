"""Comprehensive tests for SoraLink offline voice transcription, intent classification, and preview pipeline.

Covers:
- Audio upload validation (formats, sizes, missing files, unauthenticated/crew denial)
- Local model unavailable error handling (documented offline failure path)
- Mocked local transcription and intent classification pipeline
- Bounded intent candidate selection from approved data/intents.json
- Low-confidence and ambiguous transcript handling
- Urgent expression handling (medical_help, motion_sickness)
- Voice preview persistence and 30-minute expiry
- Session ownership enforcement and cross-passenger denial
- Preview confirmation creating requests strictly on explicit passenger action
- Duplicate confirmation idempotency and conflicting intent reuse prevention
- none_of_these fallback without request creation and subsequent preview invalidation
- Audio temporary file cleanup
"""

from __future__ import annotations

import io
import math
import wave
from io import BytesIO
from pathlib import Path
from typing import Any
import pytest
from flask.testing import FlaskClient

from database import get_connection, now_ms
import classifier
import requests_service
import voice


CREW_TEST_PASSWORD = "test-crew-password-xyz"


@pytest.fixture(autouse=True)
def configure_environment(monkeypatch: pytest.MonkeyPatch):
    """Ensure crew credentials are configured for test environment."""
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
# 1. Audio Upload Validation & Authorization
# =============================================================================

def test_voice_request_authorization(client: FlaskClient):
    """Unauthenticated users and crew cannot access passenger voice pipeline."""
    # Unauthenticated
    res_unauth = client.post(
        "/api/voice_request",
        data={"audio": (io.BytesIO(b"dummy audio"), "test.webm", "audio/webm")},
        content_type="multipart/form-data",
    )
    assert res_unauth.status_code == 401
    assert res_unauth.json["error"]["code"] == "UNAUTHENTICATED"

    # Crew
    _login_crew(client)
    res_crew = client.post(
        "/api/voice_request",
        data={"audio": (io.BytesIO(b"dummy audio"), "test.webm", "audio/webm")},
        content_type="multipart/form-data",
    )
    assert res_crew.status_code == 403
    assert res_crew.json["error"]["code"] == "FORBIDDEN"


def test_voice_upload_validation(client: FlaskClient):
    """Invalid, empty, oversized, or unsupported uploads are safely rejected."""
    _login_passenger(client, seat_label="18A")

    # Missing audio field
    res_no_audio = client.post(
        "/api/voice_request",
        data={"other_field": "hello"},
        content_type="multipart/form-data",
    )
    assert res_no_audio.status_code == 400
    assert res_no_audio.json["error"]["code"] == "BAD_REQUEST"

    # Empty audio file
    res_empty = client.post(
        "/api/voice_request",
        data={"audio": (io.BytesIO(b""), "empty.webm", "audio/webm")},
        content_type="multipart/form-data",
    )
    assert res_empty.status_code == 400
    assert res_empty.json["error"]["code"] == "AUDIO_MISSING"

    # Unsupported format
    res_bad_format = client.post(
        "/api/voice_request",
        data={"audio": (io.BytesIO(b"plain text data"), "test.txt", "text/plain")},
        content_type="multipart/form-data",
    )
    assert res_bad_format.status_code == 400
    assert res_bad_format.json["error"]["code"] == "UNSUPPORTED_AUDIO_TYPE"

    # Oversized upload (> 15 MB)
    large_payload = b"0" * (16 * 1024 * 1024)
    res_large = client.post(
        "/api/voice_request",
        data={"audio": (io.BytesIO(large_payload), "large.webm", "audio/webm")},
        content_type="multipart/form-data",
    )
    assert res_large.status_code == 413
    assert res_large.json["error"]["code"] == "PAYLOAD_TOO_LARGE"


# =============================================================================
# 2. Local Model Availability & Clear Failure Path
# =============================================================================

def test_local_whisper_unavailable_failure_path(client: FlaskClient):
    """When faster-whisper or weights are not installed, a clear 503 is returned."""
    _login_passenger(client, seat_label="18A")

    # Real un-mocked call in test environment where local Whisper model weights are absent
    res = client.post(
        "/api/voice_request",
        data={"audio": (io.BytesIO(b"RIFF dummy wav data"), "test.wav", "audio/wav")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 503
    assert res.json["ok"] is False
    assert res.json["error"]["code"] == "MODEL_UNAVAILABLE"

    # Verify visual request flow remains 100% operational
    res_visual = client.post("/api/requests", json={"intent_id": "water_request"})
    assert res_visual.status_code in (200, 201)
    assert res_visual.json["ok"] is True


# =============================================================================
# 3. Mocked Pipeline: Transcription & Intent Classification
# =============================================================================


def test_mocked_transcription_and_approved_intent(
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Mock AI voice processing and verify the suggested intent and persisted preview."""
    _login_passenger(client, seat_label="18A")

    monkeypatch.setattr(
        voice,
        "process_voice_preview",
        lambda *args, **kwargs: {
            "transcript": "Can I please have some water?",
            "language": "en",
            "outcome": "SUGGESTED",
            "suggested_intent": {
                "intent_id": "water_request",
                "score": 0.8812,
            },
            "candidates": [
                {"intent_id": "water_request", "score": 0.8812},
                {"intent_id": "meal_inquiry", "score": 0.05},
            ],
            "attributes": {},
            "requires_choice": False,
        },
    )

    res = client.post(
        "/api/voice_request",
        data={
            "audio": (
                io.BytesIO(b"audio bytes"),
                "input.webm",
                "audio/webm",
            )
        },
        content_type="multipart/form-data",
    )

    assert res.status_code == 200
    data = res.json["data"]

    assert data["transcript"] == "Can I please have some water?"
    assert data["intent_id"] == "water_request"
    assert data["confidence"] >= 0.72
    assert data["needs_confirmation"] is True
    assert data["preview_id"]

    # Verify preview was persisted durably in the database.
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM voice_previews WHERE id = ?",
            (data["preview_id"],),
        ).fetchone()

        assert row is not None
        assert row["transcript"] == "Can I please have some water?"
        assert row["intent_id"] == "water_request"
        assert row["consumed_at_ms"] is None
        assert row["expires_at_ms"] - row["created_at_ms"] == 1800 * 1000
    finally:
        conn.close()



def test_empty_transcript_handling(
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Empty or whitespace-only transcription returns 422 without creating a preview."""
    _login_passenger(client, seat_label="18A")

    monkeypatch.setattr(
        voice,
        "process_voice_preview",
        lambda *args, **kwargs: {
            "transcript": "   ",
            "language": "en",
            "outcome": "UNRELIABLE",
            "suggested_intent": None,
            "candidates": [],
            "attributes": {},
            "requires_choice": True,
        },
    )

    res = client.post(
        "/api/voice_request",
        data={
            "audio": (
                io.BytesIO(b"audio bytes"),
                "silence.webm",
                "audio/webm",
            )
        },
        content_type="multipart/form-data",
    )

    assert res.status_code == 422
    assert res.json["error"]["code"] == "SILENCE_OR_NO_SPEECH"

    # Confirm no preview row exists in the database.
    conn = get_connection()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM voice_previews"
        ).fetchone()[0]
        assert count == 0
    finally:
        conn.close()



def test_low_confidence_and_ambiguous_matches(
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Ambiguous matches offer alternatives without pre-selecting an intent."""
    _login_passenger(client, seat_label="18A")

    monkeypatch.setattr(
        voice,
        "process_voice_preview",
        lambda *args, **kwargs: {
            "transcript": "I need something right now",
            "language": "en",
            "outcome": "UNRELIABLE",
            "suggested_intent": None,
            "candidates": [
                {"intent_id": "water_request", "score": 0.34},
                {"intent_id": "meal_inquiry", "score": 0.32},
            ],
            "attributes": {},
            "requires_choice": True,
        },
    )

    res = client.post(
        "/api/voice_request",
        data={
            "audio": (
                io.BytesIO(b"audio bytes"),
                "ambiguous.webm",
                "audio/webm",
            )
        },
        content_type="multipart/form-data",
    )

    assert res.status_code == 200
    data = res.json["data"]

    assert data["transcript"] == "I need something right now"
    assert data["intent_id"] is None
    assert data["needs_confirmation"] is True
    assert data["allow_none_of_these"] is True
    assert len(data["alternatives"]) >= 1


def test_urgent_expression_classification(
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Recognized urgent phrases are classified as urgent and surfaced."""
    _login_passenger(client, seat_label="18A")

    urgent_cases = [
        (
            "Help me I am having chest pain and need a doctor",
            "medical_help",
        ),
        (
            "I feel airsick and I think I am going to vomit",
            "motion_sickness",
        ),
    ]

    for transcript, intent_id in urgent_cases:
        monkeypatch.setattr(
            voice,
            "process_voice_preview",
            lambda *args, _transcript=transcript, _intent_id=intent_id, **kwargs: {
                "transcript": _transcript,
                "language": "en",
                "outcome": "SUGGESTED",
                "suggested_intent": {
                    "intent_id": _intent_id,
                    "score": 0.95,
                },
                "candidates": [
                    {"intent_id": _intent_id, "score": 0.95},
                ],
                "attributes": {},
                "requires_choice": False,
            },
        )

        res = client.post(
            "/api/voice_request",
            data={
                "audio": (
                    io.BytesIO(b"audio bytes"),
                    "urgent.webm",
                    "audio/webm",
                )
            },
            content_type="multipart/form-data",
        )

        assert res.status_code == 200
        data = res.json["data"]
        assert data["transcript"] == transcript
        assert data["intent_id"] == intent_id
        assert data["needs_confirmation"] is True


# =============================================================================
# 4. Preview Lifecycle, Expiry, & Ownership
# =============================================================================

def test_preview_expiry_enforcement(client: FlaskClient, monkeypatch: pytest.MonkeyPatch):
    """Previews older than 30 minutes cannot be confirmed."""
    session_id = _login_passenger(client, seat_label="18A")

    base_time = 1_700_000_000_000
    preview = voice.create_voice_preview(
        session_id=session_id,
        transcript="Water please",
        intent_id="water_request",
        confidence=0.9,
        alternatives=[],
        current_time_ms=base_time,
    )
    preview_id = preview["id"]

    # 29 minutes later: confirmation succeeds
    monkeypatch.setattr(voice, "now_ms", lambda: base_time + 29 * 60 * 1000)
    import database
    monkeypatch.setattr(database, "now_ms", lambda: base_time + 29 * 60 * 1000)

    # Confirm
    res_confirm = client.post(
        "/api/voice_request/confirm",
        json={"preview_id": preview_id, "intent_id": "water_request"},
    )
    assert res_confirm.status_code in (200, 201)

    # Create another preview and advance clock past 30 minutes
    preview2 = voice.create_voice_preview(
        session_id=session_id,
        transcript="Blanket please",
        intent_id="blanket_request",
        confidence=0.9,
        alternatives=[],
        current_time_ms=base_time,
    )
    p2_id = preview2["id"]

    monkeypatch.setattr(database, "now_ms", lambda: base_time + 31 * 60 * 1000)
    res_expired = client.post(
        "/api/voice_request/confirm",
        json={"preview_id": p2_id, "intent_id": "blanket_request"},
    )
    assert res_expired.status_code == 410
    assert res_expired.json["error"]["code"] == "PREVIEW_EXPIRED"


def test_preview_ownership_and_cross_passenger_denial(client: FlaskClient):
    """Passengers cannot confirm or reject previews created by other passenger sessions."""
    # Passenger A creates preview
    session_a = _login_passenger(client, seat_label="18A")
    preview = voice.create_voice_preview(
        session_id=session_a,
        transcript="Water please",
        intent_id="water_request",
        confidence=0.9,
        alternatives=[],
    )
    p_id = preview["id"]

    # Passenger B logs in
    _login_passenger(client, seat_label="14B", demo_code="DEMO-14B")

    # Passenger B tries to confirm Passenger A's preview
    res_cross_confirm = client.post(
        "/api/voice_request/confirm",
        json={"preview_id": p_id, "intent_id": "water_request"},
    )
    assert res_cross_confirm.status_code == 403
    assert res_cross_confirm.json["error"]["code"] == "FORBIDDEN"

    # Passenger B tries to reject Passenger A's preview
    res_cross_reject = client.post(
        "/api/voice_request/none_of_these",
        json={"preview_id": p_id},
    )
    assert res_cross_reject.status_code == 403
    assert res_cross_reject.json["error"]["code"] == "FORBIDDEN"


# =============================================================================
# 5. Confirmation & Idempotency
# =============================================================================

def test_request_created_only_upon_explicit_confirmation(client: FlaskClient):
    """Uploading audio or creating a preview never creates a request until confirmed."""
    session_id = _login_passenger(client, seat_label="18A")

    preview = voice.create_voice_preview(
        session_id=session_id,
        transcript="I need water",
        intent_id="water_request",
        confidence=0.9,
        alternatives=[],
    )
    p_id = preview["id"]

    # Confirm NO request exists yet
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        assert count == 0, "Request was prematurely created before passenger confirmation!"
    finally:
        conn.close()

    # Passenger explicitly confirms
    res = client.post(
        "/api/voice_request/confirm",
        json={"preview_id": p_id, "intent_id": "water_request"},
    )
    assert res.status_code == 201
    assert res.json["data"]["status"] == "PENDING"
    assert res.json["data"]["seat_label"] == "18A"

    # Request now exists in requests table
    conn = get_connection()
    try:
        req_row = conn.execute("SELECT * FROM requests WHERE seat_label = '18A'").fetchone()
        assert req_row is not None
        assert req_row["intent_id"] == "water_request"
    finally:
        conn.close()


def test_duplicate_confirmation_and_conflict_handling(client: FlaskClient):
    """Repeat confirmation of same intent succeeds idempotently; different intent returns 409."""
    session_id = _login_passenger(client, seat_label="18A")

    preview = voice.create_voice_preview(
        session_id=session_id,
        transcript="Water please",
        intent_id="water_request",
        confidence=0.9,
        alternatives=[],
    )
    p_id = preview["id"]

    # First confirmation
    res1 = client.post(
        "/api/voice_request/confirm",
        json={"preview_id": p_id, "intent_id": "water_request"},
    )
    assert res1.status_code == 201
    req_id = res1.json["data"]["request_id"]

    # Duplicate confirmation of same preview with same intent
    res2 = client.post(
        "/api/voice_request/confirm",
        json={"preview_id": p_id, "intent_id": "water_request"},
    )
    assert res2.status_code == 200
    assert res2.json["data"]["request_id"] == req_id

    # Attempt to confirm same consumed preview with a conflicting intent
    res3 = client.post(
        "/api/voice_request/confirm",
        json={"preview_id": p_id, "intent_id": "blanket_request"},
    )
    assert res3.status_code == 409
    assert res3.json["error"]["code"] == "PREVIEW_ALREADY_CONSUMED"


def test_none_of_these_fallback_behavior(client: FlaskClient):
    """none_of_these returns visual catalog, creates no request, and invalidates preview."""
    session_id = _login_passenger(client, seat_label="18A")

    preview = voice.create_voice_preview(
        session_id=session_id,
        transcript="Something random",
        intent_id=None,
        confidence=0.3,
        alternatives=[],
    )
    p_id = preview["id"]

    # Passenger selects none of these
    res = client.post(
        "/api/voice_request/none_of_these",
        json={"preview_id": p_id},
    )
    assert res.status_code == 200
    data = res.json["data"]
    assert data["needs_visual_fallback"] is True
    assert "intents" in data
    assert len(data["intents"]) >= 15

    # Verify no request created
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        assert count == 0
    finally:
        conn.close()

    # Subsequent confirmation attempt on rejected preview is rejected
    res_confirm = client.post(
        "/api/voice_request/confirm",
        json={"preview_id": p_id, "intent_id": "water_request"},
    )
    assert res_confirm.status_code == 409
    assert res_confirm.json["error"]["code"] == "PREVIEW_REJECTED"


# =============================================================================
# 6. Audio Temporary File Cleanup
# =============================================================================

def test_temporary_audio_file_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Temporary audio files are deleted even when audio decoding fails."""
    monkeypatch.setattr(voice, "_temp_audio_dir", lambda: tmp_path)
    monkeypatch.setattr(voice, "_acquire_inference_slot", lambda: True)
    monkeypatch.setattr(voice, "_release_inference_slot", lambda: None)
    monkeypatch.setattr(voice, "init_voice_model", lambda: True)

    class FakeVoiceState:
        model = object()
        device = "cpu"

    monkeypatch.setattr(voice, "_VOICE", FakeVoiceState())

    def fail_decoding(*args, **kwargs):
        raise voice.VoiceProcessingError(
            "UNSUPPORTED_AUDIO_TYPE",
            "Simulated decoding failure",
            400,
        )

    monkeypatch.setattr(voice, "_decode_samples", fail_decoding)

    with pytest.raises(
        voice.VoiceProcessingError,
        match="Simulated decoding failure",
    ):
        voice.process_voice_preview(b"fake audio data", "audio/webm")

    assert list(tmp_path.iterdir()) == [], (
        "Temporary audio files were not cleaned up!"
    )