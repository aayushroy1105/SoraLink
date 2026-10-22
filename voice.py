
"""Local audio processing and Whisper transcription.

Audio is processed locally. This module transcribes audio only;
classification and passenger confirmation are separate steps.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent

DEFAULT_MODEL_PATH = BASE_DIR / "models" / "whisper"
MAX_AUDIO_BYTES = 15 * 1024 * 1024

ALLOWED_AUDIO_TYPES = {
    "audio/webm",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/ogg",
    "audio/flac",
    "audio/mp3",
}

AUDIO_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
}


class VoiceProcessingError(Exception):
    """Base exception for voice processing failures."""


class InvalidAudioError(VoiceProcessingError):
    """Raised when uploaded audio is invalid or unsupported."""


class TranscriptionUnavailableError(VoiceProcessingError):
    """Raised when the local transcription engine cannot be loaded."""


class TranscriptionFailedError(VoiceProcessingError):
    """Raised when audio transcription fails."""


_model = None
_model_key: tuple[str, str] | None = None


def _get_model_path() -> Path:
    configured = os.environ.get("SORALINK_WHISPER_MODEL_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_MODEL_PATH


def _get_model():
    """Load a local faster-whisper model once; never download a model."""
    global _model, _model_key

    model_path = _get_model_path()
    device = os.environ.get("SORALINK_WHISPER_DEVICE", "cpu").strip()
    compute_type = os.environ.get(
        "SORALINK_WHISPER_COMPUTE_TYPE", "int8"
    ).strip()

    key = (str(model_path.resolve()), f"{device}:{compute_type}")

    if _model is not None and _model_key == key:
        return _model

    if not model_path.exists():
        raise TranscriptionUnavailableError(
            "Local Whisper model not found. Configure "
            "SORALINK_WHISPER_MODEL_PATH before using voice requests."
        )

    try:
        from faster_whisper import WhisperModel

        _model = WhisperModel(
            str(model_path),
            device=device,
            compute_type=compute_type,
            local_files_only=True,
        )
        _model_key = key
        return _model
    except Exception as exc:
        _model = None
        _model_key = None
        raise TranscriptionUnavailableError(
            "The local Whisper model could not be loaded."
        ) from exc


def _normalise_audio_type(content_type: str | None) -> str:
    """Return the base MIME type without parameters."""
    if not content_type:
        raise InvalidAudioError("Audio content type is required")

    return content_type.split(";", 1)[0].strip().lower()


def transcribe_audio(
    audio_bytes: bytes,
    content_type: str,
    *,
    language: str | None = None,
) -> dict[str, Any]:
    """Transcribe uploaded audio using a locally installed Whisper model.

    Args:
        audio_bytes: Raw encoded audio bytes from the client.
        content_type: Browser-reported MIME type.
        language: Optional language code, such as 'en' or 'ja'.

    Returns:
        A dictionary containing transcript, detected language,
        and an optional language probability.

    Raises:
        InvalidAudioError: The upload is invalid or unsupported.
        TranscriptionUnavailableError: The local model is unavailable.
        TranscriptionFailedError: Transcription failed.
    """
    if not isinstance(audio_bytes, bytes) or not audio_bytes:
        raise InvalidAudioError("No audio data was received")

    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise InvalidAudioError("Audio upload exceeds the 15 MB limit")

    mime_type = _normalise_audio_type(content_type)

    if mime_type not in ALLOWED_AUDIO_TYPES:
        raise InvalidAudioError(
            f"Unsupported audio format: {mime_type}"
        )

    if language is not None:
        if not isinstance(language, str) or not language.strip():
            raise InvalidAudioError("Language must be a non-empty language code")
        language = language.strip().lower()

        if len(language) > 12:
            raise InvalidAudioError("Language code is too long")

    model = _get_model()
    extension = AUDIO_EXTENSIONS[mime_type]
    temporary_path: str | None = None

    try:
        # Each request gets a unique temporary file.
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=extension,
            prefix="soralink-audio-",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            temporary_file.write(audio_bytes)

        segments, info = model.transcribe(
            temporary_path,
            language=language,
            beam_size=5,
            vad_filter=True,
        )

        # Segment generation can fail lazily, so iterate inside try/finally.
        parts = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                parts.append(text)

        transcript = " ".join(parts).strip()

        if not transcript:
            raise TranscriptionFailedError(
                "No speech could be recognized in the audio"
            )

        language_probability = getattr(info, "language_probability", None)

        return {
            "transcript": transcript,
            "language": getattr(info, "language", None),
            "language_probability": (
                float(language_probability)
                if language_probability is not None
                else None
            ),
        }

    except VoiceProcessingError:
        raise
    except Exception as exc:
        raise TranscriptionFailedError(
            "Audio transcription failed"
        ) from exc
    finally:
        if temporary_path is not None:
            try:
                Path(temporary_path).unlink(missing_ok=True)
            except OSError:
                # Do not expose a temporary path or audio bytes to clients.
                pass


def reset_model() -> None:
    """Reset the cached model, useful for tests and model replacement."""
    global _model, _model_key
    _model = None
    _model_key = None
