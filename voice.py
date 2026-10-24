"""Audio intake, local Whisper transcription and the voice-preview payload.

The backend owns everything downstream: this module validates the upload,
transcribes it locally, classifies the text and returns a *preview* dictionary.
It never writes to SQLite, never creates a passenger request and never bypasses
passenger confirmation.

Public interface (used by ``app.py``)::

    init_ai_models() -> dict          # load both models once at startup
    get_ai_readiness() -> dict        # {"voice_model": ..., "classifier": ...}
    process_voice_preview(bytes, mime) -> dict
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from classifier import (
    VoiceProcessingError,
    classify_text,
    get_classifier_readiness,
    init_classifier,
    load_intent_contract,
)

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WHISPER_DIR = PROJECT_ROOT / "models" / "whisper"

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MiB
MAX_AUDIO_SECONDS = 20.0
TARGET_AUDIO_SECONDS = 15.0
SAMPLE_RATE = 16_000

#: Allowlisted MIME types -> safe file extension. The client filename is ignored.
MIME_EXTENSION_MAP: dict[str, str] = {
    "audio/webm;codecs=opus": ".webm",
    "audio/webm": ".webm",
    "audio/mp4": ".mp4",
    "audio/mp4;codecs=mp4a.40.2": ".m4a",
    "audio/mp4;codecs=mp4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/m4a": ".m4a",
    "audio/mp4a-latm": ".m4a",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/ogg;codecs=opus": ".ogg",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, default))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


MAX_CONCURRENT_INFERENCES = _env_int("SORALINK_MAX_CONCURRENT_INFERENCES", 1)
SEMAPHORE_TIMEOUT_SECONDS = _env_float("SORALINK_SEMAPHORE_TIMEOUT", 2.0)

#: One GPU, so one inference at a time by default.
_INFERENCE_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_INFERENCES)


# --------------------------------------------------------------------------- #
# Validation                                                                   #
# --------------------------------------------------------------------------- #
def canonical_mime_type(mime_type: str | None) -> str:
    """Lowercase, drop spaces and extra parameters after the first codec group."""
    if not mime_type:
        return ""
    raw = str(mime_type).split(",")[0].strip().lower().replace(" ", "")
    return raw


def resolve_audio_extension(mime_type: str | None) -> str:
    """Return the safe extension for an allowlisted MIME type or raise."""
    key = canonical_mime_type(mime_type)
    # Exact matching only: an approved container with an unapproved codec
    # (e.g. "audio/webm;codecs=vp9") is rejected rather than silently accepted.
    extension = MIME_EXTENSION_MAP.get(key)
    if extension is None:
        raise VoiceProcessingError(
            "UNSUPPORTED_AUDIO_TYPE",
            "That audio format is not supported. Please record again in this browser.",
            400,
        )
    return extension


def validate_upload(audio_bytes: bytes | bytearray | None, mime_type: str | None) -> str:
    """Validate size/type and return the safe extension. Never trusts filenames."""
    if audio_bytes is None:
        raise VoiceProcessingError(
            "AUDIO_MISSING",
            "No recording was received. Please record your request or tap a request card.",
            400,
        )
    if not isinstance(audio_bytes, (bytes, bytearray)):
        raise VoiceProcessingError(
            "AUDIO_MISSING",
            "No recording was received. Please record your request or tap a request card.",
            400,
        )
    if len(audio_bytes) == 0:
        raise VoiceProcessingError(
            "AUDIO_MISSING",
            "The recording was empty. Please try again or tap a request card.",
            400,
        )
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise VoiceProcessingError(
            "AUDIO_TOO_LARGE",
            "That recording is too large. Please record a shorter request.",
            413,
        )
    return resolve_audio_extension(mime_type)


# --------------------------------------------------------------------------- #
# Whisper singleton                                                            #
# --------------------------------------------------------------------------- #
class _VoiceState:
    model: Any = None
    device: str | None = None
    compute_type: str | None = None
    load_error: str | None = None


_VOICE = _VoiceState()
_VOICE_LOCK = threading.Lock()


def _whisper_dir() -> Path:
    env_dir = os.environ.get("SORALINK_WHISPER_DIR")
    return Path(env_dir) if env_dir else DEFAULT_WHISPER_DIR


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def init_voice_model(force: bool = False) -> bool:
    """Load faster-whisper from ``./models/whisper`` once (CUDA, CPU fallback)."""
    with _VOICE_LOCK:
        if _VOICE.model is not None and not force:
            return True
        _VOICE.model = None
        _VOICE.load_error = None

        model_dir = _whisper_dir()
        if not model_dir.exists():
            _VOICE.load_error = "whisper weights not found"
            return False

        try:
            from faster_whisper import WhisperModel
        except Exception as exc:  # pragma: no cover - dependency missing
            _VOICE.load_error = f"{type(exc).__name__}"
            return False

        attempts: list[tuple[str, str]] = []
        if _cuda_available():
            attempts.append(("cuda", "int8_float16"))
        attempts.append(("cpu", "int8"))

        last_error = "unknown"
        for device, compute_type in attempts:
            try:
                model = WhisperModel(
                    str(model_dir),
                    device=device,
                    compute_type=compute_type,
                    local_files_only=True,
                )
            except Exception as exc:  # CUDA/cuDNN mismatch, corrupted weights, ...
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            _VOICE.model = model
            _VOICE.device = device
            _VOICE.compute_type = compute_type
            return True

        _VOICE.load_error = last_error
        return False


def get_voice_readiness() -> str:
    return "READY" if _VOICE.model is not None else "UNAVAILABLE"


def get_ai_readiness() -> dict[str, str]:
    """Startup/health payload. Deliberately free of paths and tracebacks."""
    return {
        "voice_model": get_voice_readiness(),
        "classifier": get_classifier_readiness(),
    }


def init_ai_models(force: bool = False) -> dict[str, str]:
    """Load Whisper and the SetFit classifier once, then report readiness.

    Raises ``ValueError`` when ``data/intents.json`` violates the frozen
    contract — that is a startup-time programming/merge error, not a passenger
    error, so it must be loud rather than degraded.
    """
    load_intent_contract(refresh=force)
    if force:
        init_voice_model(force=True)
        init_classifier(force=True)
    else:
        init_voice_model()
        init_classifier()
    return get_ai_readiness()


# --------------------------------------------------------------------------- #
# Temp-file + concurrency safety                                               #
# --------------------------------------------------------------------------- #
def _temp_audio_dir() -> Path:
    directory = Path(tempfile.gettempdir()) / "soralink_audio"
    directory.mkdir(parents=True, exist_ok=True)
    try:  # best effort on Windows; POSIX gets 0700
        os.chmod(directory, 0o700)
    except OSError:  # pragma: no cover - platform dependent
        pass
    return directory


def _acquire_inference_slot() -> bool:
    return _INFERENCE_SEMAPHORE.acquire(timeout=SEMAPHORE_TIMEOUT_SECONDS)


def _release_inference_slot() -> None:
    try:
        _INFERENCE_SEMAPHORE.release()
    except ValueError:  # pragma: no cover - defensive
        pass


# --------------------------------------------------------------------------- #
# Transcription                                                               #
# --------------------------------------------------------------------------- #
def _decode_samples(path: Path) -> np.ndarray:
    try:
        from faster_whisper.audio import decode_audio  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - older layouts
        from faster_whisper import decode_audio  # type: ignore[no-redef]

    try:
        samples = decode_audio(str(path), sampling_rate=SAMPLE_RATE)
    except Exception as exc:
        raise VoiceProcessingError(
            "UNSUPPORTED_AUDIO_TYPE",
            "The recording could not be read. Please record again or tap a request card.",
            400,
        ) from exc

    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
    if samples.size == 0:
        raise VoiceProcessingError(
            "SILENCE_OR_NO_SPEECH",
            "No clear speech was detected. Please try again or tap a request card.",
            422,
        )
    return samples


def _transcribe(model: Any, samples: np.ndarray) -> tuple[str, str, float]:
    duration = float(samples.size) / float(SAMPLE_RATE)
    if duration > MAX_AUDIO_SECONDS:
        raise VoiceProcessingError(
            "AUDIO_TOO_LONG",
            f"Recording is {duration:.1f}s; the maximum is {MAX_AUDIO_SECONDS:.0f} seconds.",
            422,
        )
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if duration < 0.25 or peak < 1e-3:
        raise VoiceProcessingError(
            "SILENCE_OR_NO_SPEECH",
            "No clear speech was detected. Please try again or tap a request card.",
            422,
        )

    segments, info = model.transcribe(
        samples,
        vad_filter=True,
        beam_size=1,
        condition_on_previous_text=False,
    )
    parts = [segment.text.strip() for segment in segments if getattr(segment, "text", "").strip()]
    transcript = " ".join(parts).strip()

    info_duration = float(getattr(info, "duration", 0.0) or 0.0)
    if info_duration > MAX_AUDIO_SECONDS:
        raise VoiceProcessingError(
            "AUDIO_TOO_LONG",
            f"Recording is {info_duration:.1f}s; the maximum is {MAX_AUDIO_SECONDS:.0f} seconds.",
            422,
        )

    language = str(getattr(info, "language", "") or "en").split("-")[0].lower()
    if not transcript:
        raise VoiceProcessingError(
            "SILENCE_OR_NO_SPEECH",
            "No clear speech was detected. Please try again or tap a request card.",
            422,
        )
    return transcript, language, max(duration, info_duration)


# --------------------------------------------------------------------------- #
# Public entrypoint                                                            #
# --------------------------------------------------------------------------- #
def process_voice_preview(audio_bytes: bytes, mime_type: str) -> dict[str, Any]:
    """Turn an uploaded recording into a structured preview for the backend.

    Raises :class:`VoiceProcessingError` with a frozen ``code`` and HTTP status on
    every failure path. The temp file is removed in a ``finally`` block whether
    transcription succeeds or fails.
    """
    extension = validate_upload(audio_bytes, mime_type)

    if not _acquire_inference_slot():
        raise VoiceProcessingError(
            "MODEL_BUSY",
            "Voice recognition is currently busy. Please retry or use a request card.",
            503,
        )

    temp_path: Path | None = None
    try:
        if not init_voice_model():
            raise VoiceProcessingError(
                "MODEL_UNAVAILABLE",
                "Voice recognition is not available right now. Please tap a request card.",
                503,
            )

        temp_path = _temp_audio_dir() / f"soralink_audio_{uuid.uuid4().hex}{extension}"
        with open(temp_path, "wb") as handle:
            handle.write(audio_bytes)

        started = time.perf_counter()
        samples = _decode_samples(temp_path)
        transcript, language, duration = _transcribe(_VOICE.model, samples)
        classification = classify_text(transcript)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

        # Structured preview only — persistence and confirmation belong to the backend.
        result: dict[str, Any] = {
            "transcript": classification["transcript"],
            "language": language,
            "suggested_intent": classification["suggested_intent"],
            "attributes": classification["attributes"],
            "candidates": classification["candidates"],
            "outcome": classification["outcome"],
            "requires_choice": classification["requires_choice"],
        }
        # Telemetry for logs only; excluded from the HTTP body by app.py if desired.
        result_meta = {
            "duration_seconds": round(duration, 2),
            "processing_ms": elapsed_ms,
            "device": _VOICE.device,
        }
        _LAST_PREVIEW_META.clear()
        _LAST_PREVIEW_META.update(result_meta)
        return result
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            except OSError:  # pragma: no cover - Windows file lock
                pass
        _release_inference_slot()


#: Last preview diagnostics (timing/device) for scripts; never part of the API body.
_LAST_PREVIEW_META: dict[str, Any] = {}


__all__ = [
    "MAX_AUDIO_BYTES",
    "MAX_AUDIO_SECONDS",
    "MIME_EXTENSION_MAP",
    "VoiceProcessingError",
    "canonical_mime_type",
    "get_ai_readiness",
    "get_voice_readiness",
    "init_ai_models",
    "process_voice_preview",
    "resolve_audio_extension",
    "validate_upload",
]


import json
import sqlite3
import time
import uuid

from database import get_db, transaction

DEFAULT_PREVIEW_TTL_SECONDS = 30 * 60

def now_ms() -> int:
    """Return the current UTC Unix timestamp in milliseconds."""
    return time.time_ns() // 1_000_000


DEFAULT_PREVIEW_TTL_SECONDS = 30 * 60


def _preview_from_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    raw_alts = data.get("alternatives_json", "[]")
    try:
        alternatives = json.loads(raw_alts) if isinstance(raw_alts, str) else raw_alts
    except (json.JSONDecodeError, TypeError):
        alternatives = []

    return {
        "id": data.get("id"),
        "preview_id": data.get("id"),
        "session_id": data.get("session_id"),
        "transcript": data.get("transcript"),
        "intent_id": data.get("intent_id"),
        "confidence": data.get("confidence"),
        "alternatives": alternatives,
        "created_at_ms": data.get("created_at_ms"),
        "expires_at_ms": data.get("expires_at_ms"),
        "consumed_at_ms": data.get("consumed_at_ms"),
        "request_id": data.get("request_id"),
    }


def create_voice_preview(
    session_id: str,
    transcript: str,
    intent_id: str | None,
    confidence: float | None,
    alternatives: list[dict[str, Any]],
    ttl_seconds: int = DEFAULT_PREVIEW_TTL_SECONDS,
    current_time_ms: int | None = None,
) -> dict[str, Any]:
    """Persist an expiring voice preview bound to an authenticated session."""
    preview_id = str(uuid.uuid4())
    timestamp = current_time_ms if current_time_ms is not None else now_ms()
    expires_at = timestamp + ttl_seconds * 1000
    alternatives_json = json.dumps(alternatives)

    with get_db() as connection:
        with transaction(connection):
            connection.execute(
                """
                INSERT INTO voice_previews (
                    id, session_id, transcript, intent_id, confidence,
                    alternatives_json, created_at_ms, expires_at_ms,
                    consumed_at_ms, request_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    preview_id,
                    session_id,
                    transcript,
                    intent_id,
                    confidence,
                    alternatives_json,
                    timestamp,
                    expires_at,
                ),
            )

        row = connection.execute(
            "SELECT * FROM voice_previews WHERE id = ?",
            (preview_id,),
        ).fetchone()

    return _preview_from_row(row)


def get_voice_preview(preview_id: str) -> dict[str, Any] | None:
    """Retrieve a voice preview by ID."""
    with get_db() as connection:
        row = connection.execute(
            "SELECT * FROM voice_previews WHERE id = ?",
            (preview_id,),
        ).fetchone()

    return _preview_from_row(row) if row is not None else None


def consume_voice_preview(
    preview_id: str,
    request_id: str,
    current_time_ms: int | None = None,
) -> None:
    """Mark a preview as consumed by a created request."""
    timestamp = current_time_ms if current_time_ms is not None else now_ms()
    with get_db() as connection:
        with transaction(connection):
            connection.execute(
                """
                UPDATE voice_previews
                SET consumed_at_ms = ?, request_id = ?
                WHERE id = ?
                """,
                (timestamp, request_id, preview_id),
            )


def reject_voice_preview(
    preview_id: str,
    current_time_ms: int | None = None,
) -> None:
    """Mark a preview as rejected via none_of_these."""
    timestamp = current_time_ms if current_time_ms is not None else now_ms()
    with get_db() as connection:
        with transaction(connection):
            connection.execute(
                """
                UPDATE voice_previews
                SET consumed_at_ms = ?, request_id = 'REJECTED'
                WHERE id = ?
                """,
                (timestamp, preview_id),
            )
