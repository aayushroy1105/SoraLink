"""Tests for the SoraLink AI/audio layer (classifier.py + voice.py).

No GPU, model weights or network access are required: the heavy models are
replaced with deterministic fakes, while real WAV bytes exercise the actual
validation, decoding, cleanup and concurrency code paths.
"""

from __future__ import annotations

import json
import math
import sys
import types
import wave
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import classifier  # noqa: E402
import voice  # noqa: E402
from classifier import (  # noqa: E402
    REQUIRED_INTENT_IDS,
    URGENT_IDS,
    VoiceProcessingError,
)

CLASS_LABELS = list(REQUIRED_INTENT_IDS)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def make_wav(seconds: float = 1.0, freq: float = 440.0, amplitude: int = 8000) -> bytes:
    """Mono 16-bit 16 kHz PCM WAV with a real tone (not silence)."""
    rate = 16000
    frames = int(rate * seconds)
    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        samples = bytearray()
        for index in range(frames):
            value = int(amplitude * math.sin(2 * math.pi * freq * index / rate))
            samples += int(value).to_bytes(2, "little", signed=True)
        handle.writeframes(bytes(samples))
    return buffer.getvalue()


def make_silent_wav(seconds: float = 1.0) -> bytes:
    rate = 16000
    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))
    return buffer.getvalue()


def score_vector(overrides: dict[str, float], base: float = 0.002) -> np.ndarray:
    vector = np.full(len(CLASS_LABELS), base, dtype=np.float32)
    for intent_id, score in overrides.items():
        vector[CLASS_LABELS.index(intent_id)] = score
    return vector


def install_fake_classifier(monkeypatch, overrides: dict[str, float]) -> None:
    vector = score_vector(overrides)

    class FakeSetFit:
        labels = CLASS_LABELS

        def predict_proba(self, texts):
            return np.tile(vector, (len(texts), 1))

    monkeypatch.setattr(classifier._STATE, "model", FakeSetFit())
    monkeypatch.setattr(classifier._STATE, "labels", list(CLASS_LABELS))


def assert_error(exc_info, code: str, http_status: int) -> None:
    assert exc_info.value.code == code
    assert exc_info.value.http_status == http_status
    assert isinstance(exc_info.value.message, str) and exc_info.value.message


def temp_audio_files() -> set[Path]:
    return set(voice._temp_audio_dir().glob("soralink_audio_*"))


@pytest.fixture
def fake_classifier(monkeypatch):
    def install(overrides: dict[str, float]) -> None:
        install_fake_classifier(monkeypatch, overrides)

    monkeypatch.setattr(classifier._STATE, "model", None)
    monkeypatch.setattr(classifier._STATE, "labels", [])
    return install


@pytest.fixture
def fake_whisper(monkeypatch):
    """Replace the Whisper singleton; never touches ./models or the GPU."""
    original_model = voice._VOICE.model
    original_device = voice._VOICE.device

    def install(text: str = "Could I have warm water please", language: str = "en",
                duration: float = 1.2, raises: Exception | None = None):
        class FakeWhisper:
            def __init__(self) -> None:
                self.kwargs: dict | None = None

            def transcribe(self, samples, **kwargs):
                self.kwargs = kwargs
                if raises is not None:
                    raise raises
                info = types.SimpleNamespace(duration=duration, language=language)
                segments = [types.SimpleNamespace(text=text)] if text else []
                return iter(segments), info

        instance = FakeWhisper()
        voice._VOICE.model = instance
        voice._VOICE.device = "cpu"
        monkeypatch.setattr(voice, "init_voice_model", lambda force=False: True)
        return instance

    yield install

    voice._VOICE.model = original_model
    voice._VOICE.device = original_device


# --------------------------------------------------------------------------- #
# Contract                                                                     #
# --------------------------------------------------------------------------- #
def test_contract_contains_all_15_frozen_intents():
    contract = classifier.load_intent_contract(refresh=True)
    ids = [entry["intent_id"] for entry in contract["intents"]]
    assert len(ids) == 15
    assert set(ids) == set(REQUIRED_INTENT_IDS)
    assert len(ids) == len(set(ids))

    for entry in contract["intents"]:
        assert entry["priority"] in {"URGENT", "ROUTINE"}
        assert set(entry["labels"]) == {"en", "ja", "hi", "pa"}
        assert len(entry["training_examples"]) >= 20
        if entry["priority"] == "URGENT":
            assert entry["urgent_keywords"], entry["intent_id"]
        else:
            assert entry["urgent_keywords"] == []

    by_id = {entry["intent_id"]: entry for entry in contract["intents"]}
    assert set(by_id) & set(URGENT_IDS) == set(URGENT_IDS)
    assert by_id["water_request"]["allowed_attributes"] == {
        "temperature": ["COLD", "ROOM", "WARM"]
    }
    assert by_id["meal_inquiry"]["allowed_attributes"] == {
        "dietary": ["VEG", "NON_VEG", "SNACK"]
    }


def test_contract_rejects_missing_intent(tmp_path):
    contract = json.loads((PROJECT_ROOT / "data" / "intents.json").read_text(encoding="utf-8"))
    contract["intents"] = [i for i in contract["intents"] if i["intent_id"] != "customs_form"]
    broken = tmp_path / "intents.json"
    broken.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(ValueError, match="customs_form"):
        classifier.load_intent_contract(broken)


def test_contract_rejects_duplicate_and_bad_priority(tmp_path):
    contract = json.loads((PROJECT_ROOT / "data" / "intents.json").read_text(encoding="utf-8"))

    duplicate = json.loads(json.dumps(contract))
    duplicate["intents"].append(duplicate["intents"][0])
    dup_path = tmp_path / "duplicate.json"
    dup_path.write_text(json.dumps(duplicate), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        classifier.load_intent_contract(dup_path)

    bad_priority = json.loads(json.dumps(contract))
    bad_priority["intents"][0]["priority"] = "HIGH"
    bad_path = tmp_path / "priority.json"
    bad_path.write_text(json.dumps(bad_priority), encoding="utf-8")
    with pytest.raises(ValueError, match="priority"):
        classifier.load_intent_contract(bad_path)


def test_probability_columns_follow_head_class_order():
    class FakeHead:
        classes_ = np.array(["bag_help", "water_request"])

    model = types.SimpleNamespace(labels=["water_request", "bag_help"], model_head=FakeHead())
    assert classifier.probability_labels(model) == ["bag_help", "water_request"]

    # A differentiable head has no classes_; model.labels is then authoritative.
    plain = types.SimpleNamespace(labels=["water_request"], model_head=None)
    assert classifier.probability_labels(plain) == ["water_request"]


def test_normalization_preserves_scripts_and_tidies_punctuation():
    assert classifier.normalize_text("  Could   I have water!!!  ") == "Could I have water!"
    assert classifier.normalize_text("hello???") == "hello?"
    assert classifier.normalize_text("tabiyat\u200b kharab\x00 hai") == "tabiyat kharab hai"
    assert classifier.normalize_text("मुझे पानी चाहिए") == "मुझे पानी चाहिए"
    assert classifier.normalize_text("ਮੈਨੂੰ ਪਾਣੀ ਚਾਹੀਦਾ ਹੈ") == "ਮੈਨੂੰ ਪਾਣੀ ਚਾਹੀਦਾ ਹੈ"
    assert classifier.normalize_text(None) == ""


# --------------------------------------------------------------------------- #
# MIME / upload validation                                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "mime,expected",
    [
        ("audio/webm;codecs=opus", ".webm"),
        ("audio/webm", ".webm"),
        ("audio/mp4", ".mp4"),
        ("audio/x-m4a", ".m4a"),
        ("audio/mp4a-latm", ".m4a"),
        ("audio/wav", ".wav"),
        ("audio/x-wav", ".wav"),
        ("audio/wave", ".wav"),
        ("audio/ogg", ".ogg"),
        ("audio/ogg;codecs=opus", ".ogg"),
        ("audio/mpeg", ".mp3"),
        ("audio/mp3", ".mp3"),
        (" AUDIO/WEBM;Codecs=Opus ", ".webm"),
    ],
)
def test_mime_allowlist(mime, expected):
    assert voice.resolve_audio_extension(mime) == expected


@pytest.mark.parametrize(
    "mime",
    ["application/pdf", "video/mp4", "audio/flac", "text/plain", "", None, "audio/webm;codecs=vp9"],
)
def test_mime_rejected(mime):
    with pytest.raises(VoiceProcessingError) as exc:
        voice.resolve_audio_extension(mime)
    assert_error(exc, "UNSUPPORTED_AUDIO_TYPE", 400)


def test_audio_missing():
    for payload in (b"", None):
        with pytest.raises(VoiceProcessingError) as exc:
            voice.validate_upload(payload, "audio/webm")
        assert_error(exc, "AUDIO_MISSING", 400)


def test_audio_too_large():
    payload = b"0" * (voice.MAX_AUDIO_BYTES + 1)
    with pytest.raises(VoiceProcessingError) as exc:
        voice.validate_upload(payload, "audio/webm")
    assert_error(exc, "AUDIO_TOO_LARGE", 413)


def test_error_type_is_shared_with_voice_module():
    assert voice.VoiceProcessingError is classifier.VoiceProcessingError


# --------------------------------------------------------------------------- #
# Model availability / concurrency                                             #
# --------------------------------------------------------------------------- #
def test_model_unavailable_when_weights_missing(monkeypatch):
    before = temp_audio_files()
    monkeypatch.setattr(voice, "init_voice_model", lambda force=False: False)
    with pytest.raises(VoiceProcessingError) as exc:
        voice.process_voice_preview(make_wav(1.0), "audio/wav")
    assert_error(exc, "MODEL_UNAVAILABLE", 503)
    assert temp_audio_files() == before


def test_model_busy_when_semaphore_is_held(monkeypatch):
    monkeypatch.setattr(voice, "SEMAPHORE_TIMEOUT_SECONDS", 0.05)
    assert voice._INFERENCE_SEMAPHORE.acquire(timeout=2.0)
    try:
        with pytest.raises(VoiceProcessingError) as exc:
            voice.process_voice_preview(make_wav(1.0), "audio/wav")
        assert_error(exc, "MODEL_BUSY", 503)
    finally:
        voice._INFERENCE_SEMAPHORE.release()

    # The slot must still be usable afterwards.
    assert voice._INFERENCE_SEMAPHORE.acquire(timeout=1.0)
    voice._INFERENCE_SEMAPHORE.release()


def test_semaphore_released_when_inference_fails(fake_whisper):
    fake_whisper(raises=RuntimeError("decode exploded"))
    with pytest.raises(RuntimeError):
        voice.process_voice_preview(make_wav(1.0), "audio/wav")
    assert voice._INFERENCE_SEMAPHORE.acquire(timeout=1.0)
    voice._INFERENCE_SEMAPHORE.release()


# --------------------------------------------------------------------------- #
# Audio validation inside the pipeline                                         #
# --------------------------------------------------------------------------- #
def test_silent_audio_is_rejected(fake_whisper):
    fake_whisper()
    before = temp_audio_files()
    with pytest.raises(VoiceProcessingError) as exc:
        voice.process_voice_preview(make_silent_wav(1.0), "audio/wav")
    assert_error(exc, "SILENCE_OR_NO_SPEECH", 422)
    assert temp_audio_files() == before


def test_audio_too_long_is_rejected(fake_whisper):
    fake_whisper()
    before = temp_audio_files()
    with pytest.raises(VoiceProcessingError) as exc:
        voice.process_voice_preview(make_wav(21.0), "audio/wav")
    assert_error(exc, "AUDIO_TOO_LONG", 422)
    assert temp_audio_files() == before


def test_empty_transcript_is_silence(fake_whisper):
    fake_whisper(text="")
    with pytest.raises(VoiceProcessingError) as exc:
        voice.process_voice_preview(make_wav(1.0), "audio/wav")
    assert_error(exc, "SILENCE_OR_NO_SPEECH", 422)


def test_temp_file_removed_after_success(fake_whisper, fake_classifier):
    fake_whisper(text="Could I have warm water please")
    fake_classifier({"water_request": 0.88, "meal_inquiry": 0.05})
    before = temp_audio_files()

    result = voice.process_voice_preview(make_wav(1.0), "audio/webm;codecs=opus")

    assert result["outcome"] == "SUGGESTED"
    assert temp_audio_files() == before, "temp audio file was not deleted"


def test_temp_file_removed_when_inference_raises(fake_whisper):
    fake_whisper(raises=RuntimeError("whisper crashed"))
    before = temp_audio_files()
    with pytest.raises(RuntimeError):
        voice.process_voice_preview(make_wav(1.0), "audio/wav")
    assert temp_audio_files() == before, "temp audio file leaked on exception"


# --------------------------------------------------------------------------- #
# Voice preview payload                                                        #
# --------------------------------------------------------------------------- #
def test_preview_payload_matches_contract(fake_whisper, fake_classifier):
    fake_whisper(text="Could I have warm water, please?", language="en")
    fake_classifier({"water_request": 0.8812, "meal_inquiry": 0.0510})

    result = voice.process_voice_preview(make_wav(1.0), "audio/webm;codecs=opus")

    assert set(result) == {
        "transcript",
        "language",
        "suggested_intent",
        "attributes",
        "candidates",
        "outcome",
        "requires_choice",
    }
    assert result["transcript"] == "Could I have warm water, please?"
    assert result["language"] == "en"
    assert result["outcome"] == "SUGGESTED"
    assert result["requires_choice"] is False
    assert result["suggested_intent"] == {"intent_id": "water_request", "score": 0.8812}
    assert result["attributes"] == {"temperature": "WARM"}
    assert result["candidates"][0] == {"intent_id": "water_request", "score": 0.8812}
    assert len(result["candidates"]) <= 3
    json.dumps(result)  # must be JSON serialisable for the backend


def test_preview_requires_choice_has_no_suggestion(fake_whisper, fake_classifier):
    fake_whisper(text="water or food maybe")
    fake_classifier({"water_request": 0.45, "meal_inquiry": 0.40})

    result = voice.process_voice_preview(make_wav(1.0), "audio/wav")

    assert result["outcome"] == "REQUIRES_CHOICE"
    assert result["requires_choice"] is True
    assert result["suggested_intent"] is None
    assert result["attributes"] == {}
    ids = [c["intent_id"] for c in result["candidates"]]
    assert ids[:2] == ["water_request", "meal_inquiry"]


# --------------------------------------------------------------------------- #
# Classification outcomes                                                      #
# --------------------------------------------------------------------------- #
def test_suggested_outcome(fake_classifier):
    fake_classifier({"blanket_request": 0.91, "seat_issue": 0.03, "pillow_request": 0.02})
    result = classifier.classify_text("Can I get a blanket please")
    assert result["outcome"] == "SUGGESTED"
    assert result["requires_choice"] is False
    assert result["suggested_intent"]["intent_id"] == "blanket_request"
    assert 0.0 <= result["suggested_intent"]["score"] <= 1.0


def test_requires_choice_on_close_margin(fake_classifier):
    fake_classifier({"water_request": 0.48, "meal_inquiry": 0.42})
    result = classifier.classify_text("some water and food please")
    assert result["outcome"] == "REQUIRES_CHOICE"
    assert result["requires_choice"] is True
    assert result["suggested_intent"] is None
    assert len(result["candidates"]) >= 2


def test_unreliable_outcome(fake_classifier):
    fake_classifier({intent_id: 0.06 for intent_id in REQUIRED_INTENT_IDS})
    result = classifier.classify_text("purple elephant dancing on the runway")
    assert result["outcome"] == "UNRELIABLE"
    assert result["requires_choice"] is True
    assert result["suggested_intent"] is None
    assert result["candidates"] == []
    assert result["transcript"] == "purple elephant dancing on the runway"


def test_confident_model_on_gibberish_is_unreliable(fake_classifier):
    # A closed-set head happily labels nonsense; the vocabulary gate must catch it.
    fake_classifier({"headphone_request": 0.97, "seat_issue": 0.01})
    result = classifier.classify_text("zzz qqq blorp flurble")
    assert result["outcome"] == "UNRELIABLE"
    assert result["suggested_intent"] is None
    assert result["candidates"] == []
    assert result["transcript"] == "zzz qqq blorp flurble"


def test_known_vocabulary_is_not_treated_as_gibberish(fake_classifier):
    fake_classifier({"lavatory_assist": 0.90, "seat_issue": 0.02})
    result = classifier.classify_text("where is the washroom please")
    assert result["outcome"] == "SUGGESTED"
    assert result["suggested_intent"]["intent_id"] == "lavatory_assist"


def test_urgent_keyword_forces_choice_even_with_confident_routine(fake_classifier):
    fake_classifier({"meal_inquiry": 0.80, "medical_help": 0.05})
    result = classifier.classify_text("I need a doctor now")
    assert result["outcome"] == "REQUIRES_CHOICE"
    assert result["requires_choice"] is True
    assert result["suggested_intent"] is None
    assert "medical_help" in [c["intent_id"] for c in result["candidates"]]


def test_urgent_preserved_when_overall_result_would_be_unreliable(fake_classifier):
    fake_classifier({"meal_inquiry": 0.30, "medical_help": 0.28})
    result = classifier.classify_text("something is not right with me")
    assert result["outcome"] == "REQUIRES_CHOICE"
    assert "medical_help" in [c["intent_id"] for c in result["candidates"]]


def test_out_of_vocabulary_moderate_urgent_score_is_not_surfaced(fake_classifier):
    # Closed-set heads score noise around 0.3 on some intent; that alone must not
    # turn gibberish into an urgent request.
    fake_classifier({"accessibility_assist": 0.30, "medical_help": 0.20})
    result = classifier.classify_text("zzz qqq blorp flurble")
    assert result["outcome"] == "UNRELIABLE"
    assert result["candidates"] == []


def test_out_of_vocabulary_decisive_urgent_score_is_preserved(fake_classifier):
    fake_classifier({"medical_help": 0.62, "meal_inquiry": 0.05})
    result = classifier.classify_text("zzz qqq blorp flurble")
    assert result["outcome"] == "REQUIRES_CHOICE"
    assert "medical_help" in [c["intent_id"] for c in result["candidates"]]


def test_weak_help_keyword_respects_routine_context():
    contract = classifier.load_intent_contract()
    assert classifier.urgent_signals("can you help me with my bag", contract) == []
    assert classifier.urgent_signals("please help me", contract)[0]["intent_id"] == "accessibility_assist"
    assert classifier.urgent_signals("there is smoke in the cabin", contract)[0]["intent_id"] == "safety_concern"


def test_empty_classification_text_is_silence():
    with pytest.raises(VoiceProcessingError) as exc:
        classifier.classify_text("   \x00  ")
    assert_error(exc, "SILENCE_OR_NO_SPEECH", 422)


def test_model_unavailable_for_classifier(monkeypatch):
    monkeypatch.setattr(classifier._STATE, "model", None)
    monkeypatch.setattr(classifier, "init_classifier", lambda force=False: False)
    with pytest.raises(VoiceProcessingError) as exc:
        classifier.classify_text("I need a blanket")
    assert_error(exc, "MODEL_UNAVAILABLE", 503)


# --------------------------------------------------------------------------- #
# Attributes                                                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text,expected",
    [
        ("cold water please", {"temperature": "COLD"}),
        ("thanda pani chahiye", {"temperature": "COLD"}),
        ("room temperature water", {"temperature": "ROOM"}),
        ("could I get warm water", {"temperature": "WARM"}),
        ("garam paani please", {"temperature": "WARM"}),
        ("can i have some water", {}),
        ("hot and cold water", {}),
    ],
)
def test_water_temperature_extraction(text, expected):
    assert classifier.extract_attributes("water_request", text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("I want the vegetarian meal", {"dietary": "VEG"}),
        ("non veg meal please", {"dietary": "NON_VEG"}),
        ("chicken please", {"dietary": "NON_VEG"}),
        ("just a snack", {"dietary": "SNACK"}),
        ("veg and non veg both", {}),
    ],
)
def test_meal_dietary_extraction(text, expected):
    assert classifier.extract_attributes("meal_inquiry", text) == expected


@pytest.mark.parametrize(
    "intent_id",
    [i for i in REQUIRED_INTENT_IDS if i not in {"water_request", "meal_inquiry"}],
)
def test_intents_without_attributes_never_return_any(intent_id):
    assert classifier.extract_attributes(intent_id, "cold non veg warm veg snack") == {}
