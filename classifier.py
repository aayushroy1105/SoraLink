"""Local intent classification for SoraLink (SetFit + rule-based attributes).

This module is *pure suggestion logic*: text in, structured preview out.  It never
touches SQLite, never creates passenger requests, never invents intent IDs and
never generates crew/safety wording.

Public interface used by ``voice.py`` and the backend:

* :class:`VoiceProcessingError` — the single AI-side exception type.
* ``load_intent_contract()`` — validated ``data/intents.json``.
* ``init_classifier()`` / ``get_classifier_readiness()`` — singleton loading.
* ``classify_text(transcript) -> dict`` — outcome + candidates + attributes.
* ``extract_attributes(intent_id, text) -> dict`` — rule-based attribute extractor.
"""

from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_INTENTS_PATH = PROJECT_ROOT / "data" / "intents.json"
DEFAULT_CLASSIFIER_DIR = PROJECT_ROOT / "models" / "setfit_intent_classifier"

REQUIRED_INTENT_IDS: tuple[str, ...] = (
    "medical_help",
    "accessibility_assist",
    "safety_concern",
    "motion_sickness",
    "water_request",
    "blanket_request",
    "pillow_request",
    "bag_help",
    "headphone_request",
    "meal_inquiry",
    "tea_coffee",
    "lavatory_assist",
    "seat_issue",
    "customs_form",
    "baby_care",
)
URGENT_IDS: frozenset[str] = frozenset(REQUIRED_INTENT_IDS[:4])
VALID_PRIORITIES = frozenset({"URGENT", "ROUTINE"})

#: Thresholds (overridable through the environment / ``.env``).
DEFAULT_SUGGESTED_THRESHOLD = 0.50  # calibrated by scripts/train_classifier.py
DEFAULT_MARGIN_THRESHOLD = 0.05
DEFAULT_UNRELIABLE_THRESHOLD = 0.35
#: An URGENT intent at or above this score is never dropped from the preview.
URGENT_SURFACE_THRESHOLD = 0.25
#: Stricter bar for text whose words the catalog has never seen. Closed-set heads
#: give out-of-domain noise ~0.3 on some intent; only a decisive urgent score is
#: allowed to override the UNRELIABLE verdict (urgent keywords always do).
OOD_URGENT_SCORE_THRESHOLD = 0.50

#: Closed-set models always produce a confident-looking label, even for words
#: they have never seen. If fewer than this fraction of a transcript's content
#: words appear anywhere in the catalog vocabulary, the result is UNRELIABLE
#: rather than a confident guess.
DEFAULT_MIN_VOCAB_COVERAGE = 0.34

#: Function words carry no intent and are ignored by the coverage check.
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "i", "me", "my", "we", "our", "you", "your", "he", "she",
        "it", "its", "they", "them", "is", "am", "are", "was", "were", "be", "been",
        "do", "does", "did", "can", "could", "would", "should", "will", "shall", "may",
        "might", "must", "to", "of", "in", "on", "at", "for", "with", "and", "or",
        "but", "if", "so", "this", "that", "these", "those", "there", "here", "some",
        "any", "have", "has", "had", "get", "got", "give", "please", "thanks", "thank",
        "very", "just", "now", "not", "no", "yes", "ok", "okay", "also", "more", "much",
        "want", "need", "like", "would", "one", "two", "sir", "madam", "excuse",
        "hai", "hoon", "hu", "ho", "ka", "ki", "ke", "ko", "se", "me", "mein", "hai",
        "kya", "koi", "ek", "de", "do", "di", "ji", "mera", "meri", "mujhe", "mujh",
        "thoda", "zara", "karo", "kar", "karne", "mil", "sakta", "sakti",
    }
)

_VOCAB_CACHE: tuple[int, frozenset[str]] | None = None

#: Words that only mean "urgent" together with the absence of routine context.
WEAK_URGENT_CUES = frozenset({"help", "madad", "urgent", "urgently"})

#: Nouns that mark a request as routine. Used only to qualify weak urgent cues,
#: so "help me with my bag" stays routine while "help me please" surfaces help.
ROUTINE_CONTEXT_WORDS = frozenset(
    {
        "bag", "bags", "baggage", "luggage", "suitcase", "backpack", "trolley",
        "blanket", "blankets", "kambal", "pillow", "takiya", "takya", "cushion",
        "water", "paani", "pani", "drink", "juice", "coffee", "tea",
        "meal", "food", "khana", "khaana", "snack", "sandwich", "noodles",
        "seat", "seatbelt", "belt", "tray", "armrest", "recline",
        "screen", "tv", "headphone", "headphones", "entertainment", "movie", "wifi",
        "pen", "tissue", "form", "card", "magazine", "charging", "cable",
        "washroom", "toilet", "bathroom", "restroom", "lavatory", "loo",
        "temperature", "ac", "vent", "airflow", "hot", "cold",
        "translate", "translator", "hindi", "punjabi", "japanese", "language",
        "baby", "infant", "toddler", "bassinet", "diaper", "nappy", "formula",
        "bottle", "changing", "sterilise", "sterilize",
        "customs", "immigration", "declaration", "arrival", "landing", "transit",
        "headphone", "earphone", "earphones", "remote", "volume",
    }
)

#: Rule-based attribute vocabulary. Validated against ``allowed_attributes`` at
#: contract-load time, so the catalog stays the single source of truth.
ATTRIBUTE_CUES: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {
    "water_request": {
        "temperature": {
            "COLD": ("cold", "ice", "iced", "chilled", "thanda", "thandi", "ठंडा", "ਠੰਡਾ"),
            "ROOM": ("room temperature", "room temp", "normal", "regular", "plain"),
            "WARM": ("warm", "hot", "garam", "lukewarm", "गरम", "ਗਰਮ"),
        }
    },
    "meal_inquiry": {
        "dietary": {
            "VEG": ("veg", "vegetarian", "vegan", "jain", "shakahari", "शाकाहारी", "ਸ਼ਾਕਾਹਾਰੀ"),
            "NON_VEG": (
                "non veg", "non-veg", "nonveg", "chicken", "mutton", "fish",
                "egg", "meat", "मटन", "ਚਿਕਨ",
            ),
            "SNACK": (
                "snack", "snacks", "sandwich", "noodles", "chips", "biscuit",
                "cookie", "namkeen", "स्नैक",
            ),
        }
    },
}

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u2028\u2029]")
_REPEATED_PUNCT_RE = re.compile(r"([!?.,;:])\1+")
_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[\w\u0900-\u097F\u0A00-\u0A7F']+", re.UNICODE)


# --------------------------------------------------------------------------- #
# Errors                                                                       #
# --------------------------------------------------------------------------- #
class VoiceProcessingError(Exception):
    """Passenger-safe, machine-readable failure for the AI/voice layer.

    ``code`` is one of the frozen Part 9.4 values; ``http_status`` is what the
    backend should return. Messages never contain paths or tracebacks.
    """

    def __init__(self, code: str, message: str, http_status: int) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.http_status = int(http_status)

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message}}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"VoiceProcessingError(code={self.code!r}, http_status={self.http_status})"


# --------------------------------------------------------------------------- #
# Intent contract                                                              #
# --------------------------------------------------------------------------- #
_CONTRACT_CACHE: dict[str, Any] | None = None
_CONTRACT_LOCK = threading.Lock()


def _intents_path(path: str | os.PathLike[str] | None = None) -> Path:
    if path is not None:
        return Path(path)
    env_path = os.environ.get("SORALINK_INTENTS_PATH")
    return Path(env_path) if env_path else DEFAULT_INTENTS_PATH


def _validate_contract(contract: Any, source: Path) -> dict[str, Any]:
    if not isinstance(contract, dict) or not isinstance(contract.get("intents"), list):
        raise ValueError(f"{source}: expected an object with an 'intents' list")

    intents: list[dict[str, Any]] = contract["intents"]
    seen: set[str] = set()
    for entry in intents:
        if not isinstance(entry, dict):
            raise ValueError(f"{source}: every intent must be an object")
        intent_id = entry.get("intent_id")
        if not isinstance(intent_id, str) or not intent_id:
            raise ValueError(f"{source}: intent with missing/invalid 'intent_id'")
        if intent_id in seen:
            raise ValueError(f"{source}: duplicate intent_id '{intent_id}'")
        seen.add(intent_id)

    missing = [i for i in REQUIRED_INTENT_IDS if i not in seen]
    unknown = sorted(seen - set(REQUIRED_INTENT_IDS))
    if missing:
        raise ValueError(f"{source}: missing required intent_id(s): {', '.join(missing)}")
    if unknown:
        raise ValueError(f"{source}: unknown intent_id(s) outside the frozen set: {', '.join(unknown)}")

    for entry in intents:
        intent_id = entry["intent_id"]
        priority = entry.get("priority")
        if priority not in VALID_PRIORITIES:
            raise ValueError(f"{source}: intent '{intent_id}' has invalid priority {priority!r}")
        expected_priority = "URGENT" if intent_id in URGENT_IDS else "ROUTINE"
        if priority != expected_priority:
            raise ValueError(
                f"{source}: intent '{intent_id}' must have priority {expected_priority!r}, "
                f"got {priority!r}"
            )

        labels = entry.get("labels")
        if not isinstance(labels, dict) or not all(
            isinstance(labels.get(loc), str) and labels[loc].strip()
            for loc in ("en", "ja", "hi", "pa")
        ):
            raise ValueError(f"{source}: intent '{intent_id}' is missing en/ja/hi/pa labels")

        attributes = entry.get("allowed_attributes")
        if not isinstance(attributes, dict):
            raise ValueError(f"{source}: intent '{intent_id}' has invalid allowed_attributes")
        for key, values in attributes.items():
            if not isinstance(key, str) or not isinstance(values, list) or not values:
                raise ValueError(f"{source}: intent '{intent_id}' attribute '{key}' must be a non-empty list")
            if not all(isinstance(v, str) and v.isupper() for v in values):
                raise ValueError(
                    f"{source}: intent '{intent_id}' attribute '{key}' values must be uppercase strings"
                )

        examples = entry.get("training_examples")
        if not isinstance(examples, list) or len(examples) < 10:
            raise ValueError(
                f"{source}: intent '{intent_id}' needs at least 10 training_examples (got "
                f"{len(examples) if isinstance(examples, list) else 'none'})"
            )
        if not isinstance(entry.get("urgent_keywords", []), list):
            raise ValueError(f"{source}: intent '{intent_id}' urgent_keywords must be a list")

    return contract


def load_intent_contract(path: str | os.PathLike[str] | None = None, *, refresh: bool = False) -> dict[str, Any]:
    """Load and validate the frozen intent catalog. Raises ValueError if invalid."""
    global _CONTRACT_CACHE
    source = _intents_path(path)
    with _CONTRACT_LOCK:
        if _CONTRACT_CACHE is not None and not refresh and path is None:
            return _CONTRACT_CACHE
        if not source.exists():
            raise ValueError(f"intent catalog not found: {source}")
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}: invalid JSON ({exc})") from exc
        contract = _validate_contract(raw, source)
        # Fail fast if the attribute rules drift away from the catalog.
        for intent_id, spec in ATTRIBUTE_CUES.items():
            declared = contract_intent(contract, intent_id)["allowed_attributes"]
            for attr, value_cues in spec.items():
                if attr not in declared:
                    raise ValueError(f"{source}: extractor uses undeclared attribute '{attr}' for {intent_id}")
                illegal = set(value_cues) - set(declared[attr])
                if illegal:
                    raise ValueError(
                        f"{source}: extractor uses undeclared values {sorted(illegal)} "
                        f"for {intent_id}.{attr}"
                    )
        if path is None:
            _CONTRACT_CACHE = contract
        return contract


def contract_intent(contract: dict[str, Any], intent_id: str) -> dict[str, Any]:
    for entry in contract["intents"]:
        if entry["intent_id"] == intent_id:
            return entry
    raise KeyError(intent_id)


def urgent_keyword_map(contract: dict[str, Any]) -> dict[str, list[str]]:
    """``{intent_id: [keyword, ...]}`` for the four urgent intents only."""
    return {
        entry["intent_id"]: [str(k).strip().lower() for k in entry.get("urgent_keywords", []) if str(k).strip()]
        for entry in contract["intents"]
        if entry["priority"] == "URGENT"
    }


# --------------------------------------------------------------------------- #
# Text helpers                                                                 #
# --------------------------------------------------------------------------- #
def normalize_text(text: str | None) -> str:
    """Trim control characters/extra whitespace/repeated punctuation.

    Unicode is NFC-normalised so Devanagari and Gurmukhi stay intact; no
    transliteration, lowercasing or stop-word removal happens here.
    """
    if text is None:
        return ""
    value = unicodedata.normalize("NFC", str(text))
    value = _CONTROL_CHARS_RE.sub(" ", value)
    value = _REPEATED_PUNCT_RE.sub(r"\1", value)
    value = _WHITESPACE_RE.sub(" ", value)
    return value.strip()


def _tokens(text: str) -> set[str]:
    return {tok.casefold() for tok in _TOKEN_RE.findall(text)}


def _phrase_present(text_lower: str, phrase: str) -> bool:
    """Whole-word/phrase match that also tolerates apostrophes and punctuation."""
    if " " in phrase or "'" in phrase:
        pattern = re.escape(phrase).replace(r"\ ", r"[\s,.;!?]+")
        return re.search(rf"(?<!\w){pattern}(?!\w)", text_lower) is not None
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text_lower) is not None


def request_vocabulary(contract: dict[str, Any]) -> frozenset[str]:
    """Every content token the catalog knows: training text, keywords, labels, IDs."""
    global _VOCAB_CACHE
    key = id(contract)
    if _VOCAB_CACHE is not None and _VOCAB_CACHE[0] == key:
        return _VOCAB_CACHE[1]
    vocabulary: set[str] = set()
    for entry in contract["intents"]:
        chunks: list[str] = [entry["intent_id"].replace("_", " ")]
        chunks.extend(entry.get("training_examples", []))
        chunks.extend(entry.get("urgent_keywords", []))
        chunks.extend((entry.get("labels") or {}).values())
        for chunk in chunks:
            vocabulary.update(_TOKEN_RE.findall(str(chunk).casefold()))
    frozen = frozenset(vocabulary)
    _VOCAB_CACHE = (key, frozen)
    return frozen


def vocabulary_coverage(text: str, contract: dict[str, Any] | None = None) -> float:
    """Fraction of content tokens that appear in the catalog vocabulary."""
    contract = contract or load_intent_contract()
    tokens = [t for t in _TOKEN_RE.findall(normalize_text(text).casefold()) if len(t) > 1]
    content = [t for t in tokens if t not in _STOPWORDS]
    if not content:
        return 1.0  # nothing to judge; let the model decision stand
    vocabulary = request_vocabulary(contract)
    return sum(1 for token in content if token in vocabulary) / len(content)


def min_vocab_coverage() -> float:
    return _env_float("SORALINK_MIN_VOCAB_COVERAGE", DEFAULT_MIN_VOCAB_COVERAGE)


def urgent_signals(text: str, contract: dict[str, Any]) -> list[dict[str, str]]:
    """Return urgent intent matches, applying the strong/weak cue rule.

    Each item is ``{"intent_id", "keyword", "strength"}``. Weak cues (``help``,
    ``madad``, ...) are ignored when the transcript also names a routine object,
    so benign "help me with my bag" requests do not raise a medical flag.
    """
    lowered = normalize_text(text).casefold()
    if not lowered:
        return []
    token_set = _tokens(lowered)
    routine_context = bool(token_set & ROUTINE_CONTEXT_WORDS)
    matches: list[dict[str, str]] = []
    for intent_id, keywords in urgent_keyword_map(contract).items():
        for keyword in keywords:
            if not _phrase_present(lowered, keyword):
                continue
            strength = "weak" if keyword in WEAK_URGENT_CUES else "strong"
            if strength == "weak" and routine_context:
                continue
            matches.append({"intent_id": intent_id, "keyword": keyword, "strength": strength})
    return matches


# --------------------------------------------------------------------------- #
# Model singleton                                                              #
# --------------------------------------------------------------------------- #
class _ClassifierState:
    model: Any = None
    labels: list[str] = []
    device: str | None = None
    load_error: str | None = None


_STATE = _ClassifierState()
_STATE_LOCK = threading.Lock()


def _classifier_dir() -> Path:
    env_dir = os.environ.get("SORALINK_CLASSIFIER_DIR")
    return Path(env_dir) if env_dir else DEFAULT_CLASSIFIER_DIR


def _detect_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def probability_labels(model: Any) -> list[str]:
    """Label for each column returned by ``model.predict_proba``.

    SetFit 1.2 keeps ``model.labels`` in the order it was given, but its sklearn
    head returns probability columns in ``classes_`` (alphabetical) order.  Using
    ``model.labels`` for the columns silently mislabels every prediction, so the
    head's class order wins whenever it exists.
    """
    head = getattr(model, "model_head", None)
    classes = getattr(head, "classes_", None)
    if classes is not None and len(classes) > 0:
        return [str(label) for label in classes]
    return [str(label) for label in getattr(model, "labels", []) or []]


def init_classifier(force: bool = False) -> bool:
    """Load the fine-tuned SetFit model once. Returns True when usable."""
    with _STATE_LOCK:
        if _STATE.model is not None and not force:
            return True
        _STATE.model = None
        _STATE.labels = []
        _STATE.load_error = None

        model_dir = _classifier_dir()
        if not model_dir.exists():
            _STATE.load_error = "classifier weights not found"
            return False

        try:
            from setfit import SetFitModel

            model = SetFitModel.from_pretrained(str(model_dir))
            labels = probability_labels(model)
            if sorted(labels) != sorted(REQUIRED_INTENT_IDS):
                raise ValueError(
                    "classifier labels do not match the frozen intent vocabulary "
                    f"({len(labels)} labels)"
                )

            device = _detect_device()
            if device != "cpu" and hasattr(model, "to"):
                try:
                    model.to(device)
                except Exception:
                    device = "cpu"
            elif device != "cpu":
                device = "cpu"

            _STATE.model = model
            _STATE.labels = labels
            _STATE.device = device
            return True
        except Exception as exc:  # pragma: no cover - depends on local weights
            _STATE.model = None
            _STATE.labels = []
            _STATE.load_error = f"{type(exc).__name__}"
            return False


def get_classifier_readiness() -> str:
    return "READY" if _STATE.model is not None else "UNAVAILABLE"


# --------------------------------------------------------------------------- #
# Attributes                                                                   #
# --------------------------------------------------------------------------- #
def _span_matches(text_lower: str, cue: str) -> list[tuple[int, int]]:
    if " " in cue or "-" in cue:
        pattern = re.escape(cue).replace(r"\ ", r"[\s-]+")
        return [(m.start(), m.end()) for m in re.finditer(rf"(?<!\w){pattern}(?!\w)", text_lower)]
    return [
        (m.start(), m.end())
        for m in re.finditer(rf"(?<!\w){re.escape(cue)}(?!\w)", text_lower)
    ]


def extract_attributes(
    intent_id: str,
    text: str,
    contract: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Extract only the attributes the frozen catalog allows for ``intent_id``.

    Conservative by design: conflicts (e.g. "cold and hot water") produce no
    attribute instead of guessing, and unlisted intents always return ``{}``.
    """
    contract = contract or load_intent_contract()
    spec = contract_intent(contract, intent_id)
    allowed: dict[str, list[str]] = spec.get("allowed_attributes") or {}
    rules = ATTRIBUTE_CUES.get(intent_id, {})
    if not allowed or not rules:
        return {}

    lowered = normalize_text(text).casefold()
    if not lowered:
        return {}

    extracted: dict[str, str] = {}
    for attribute, values in allowed.items():
        cue_groups = rules.get(attribute)
        if not cue_groups:
            continue

        # Longest cue first so "non veg" wins over "veg".
        candidates: list[tuple[int, int, str]] = []
        for value, cues in cue_groups.items():
            if value not in values:
                continue
            for cue in cues:
                for start, end in _span_matches(lowered, cue.casefold()):
                    candidates.append((start, end, value))
        candidates.sort(key=lambda item: (item[1] - item[0]), reverse=True)

        claimed: list[tuple[int, int]] = []
        matched_values: set[str] = set()
        for start, end, value in candidates:
            if any(start < c_end and end > c_start for c_start, c_end in claimed):
                continue
            claimed.append((start, end))
            matched_values.add(value)

        if len(matched_values) == 1:
            extracted[attribute] = next(iter(matched_values))
    return extracted


# --------------------------------------------------------------------------- #
# Thresholds & classification                                                  #
# --------------------------------------------------------------------------- #
def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if 0.0 <= value <= 1.0 else default


def thresholds() -> dict[str, float]:
    """Current calibrated thresholds (read per call so ``.env``/tests can override)."""
    return {
        "suggested": _env_float("SUGGESTED_THRESHOLD", DEFAULT_SUGGESTED_THRESHOLD),
        "margin": _env_float("MARGIN_THRESHOLD", DEFAULT_MARGIN_THRESHOLD),
        "unreliable": _env_float("UNRELIABLE_THRESHOLD", DEFAULT_UNRELIABLE_THRESHOLD),
    }


def _model_probabilities(text: str) -> dict[str, float]:
    model = _STATE.model
    labels = _STATE.labels
    if model is None or not labels:
        raise VoiceProcessingError(
            "MODEL_UNAVAILABLE",
            "The intent classifier is not available right now. Please choose a request card.",
            503,
        )
    raw = model.predict_proba([text])[0]
    if hasattr(raw, "detach"):
        raw = raw.detach().cpu().numpy()
    values = [float(v) for v in raw]
    if len(values) != len(labels):
        raise VoiceProcessingError(
            "MODEL_UNAVAILABLE",
            "The intent classifier returned an unexpected result. Please choose a request card.",
            503,
        )
    return dict(zip(labels, values))


def _rank(scores: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def _merge_urgent_candidates(
    ranked: list[tuple[str, float]],
    flagged: Iterable[str],
    limit: int = 3,
) -> list[tuple[str, float]]:
    """Top ``limit`` intents, guaranteeing every flagged urgent intent is present."""
    selected = list(ranked[:limit])
    selected_ids = {intent_id for intent_id, _ in selected}
    for intent_id in flagged:
        if intent_id in selected_ids:
            continue
        replacement = next(
            (i for i in ranked if i[0] == intent_id),
            None,
        )
        if replacement is None:
            continue
        if len(selected) >= limit:
            # Drop the weakest non-urgent entry rather than the urgent one.
            for index in range(len(selected) - 1, -1, -1):
                if selected[index][0] not in URGENT_IDS:
                    selected.pop(index)
                    break
        selected.append(replacement)
        selected_ids.add(intent_id)
    selected.sort(key=lambda item: item[1], reverse=True)
    return selected[:limit]


def classify_text(transcript: str) -> dict[str, Any]:
    """Classify a transcript into the frozen vocabulary and pick a preview outcome."""
    text = normalize_text(transcript)
    if not text:
        raise VoiceProcessingError(
            "SILENCE_OR_NO_SPEECH",
            "No clear speech was detected. Please try again or tap a request card.",
            422,
        )

    contract = load_intent_contract()
    if not init_classifier():
        raise VoiceProcessingError(
            "MODEL_UNAVAILABLE",
            "The intent classifier is not available right now. Please choose a request card.",
            503,
        )

    scores = _model_probabilities(text)
    ranked = _rank(scores)
    top1_id, top1_score = ranked[0]
    top2_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = top1_score - top2_score

    signals = urgent_signals(text, contract)
    in_vocabulary = vocabulary_coverage(text, contract) >= min_vocab_coverage()
    # In-vocabulary text only needs a moderate urgent score to be surfaced; text
    # built from unseen words needs a decisive one, so noise is not reported as an
    # urgent need. A matched urgent keyword always wins either way.
    urgent_score_threshold = (
        URGENT_SURFACE_THRESHOLD if in_vocabulary else OOD_URGENT_SCORE_THRESHOLD
    )
    flagged = {signal["intent_id"] for signal in signals}
    flagged.update(
        intent_id
        for intent_id in URGENT_IDS
        if scores.get(intent_id, 0.0) >= urgent_score_threshold
    )
    # Any urgent keyword OR any sufficiently confident URGENT intent forces a
    # choice: an urgent request is never silently turned into a routine suggestion.
    urgent_conflict = bool(flagged)

    limits = thresholds()
    # An out-of-vocabulary transcript is never a confident suggestion, regardless
    # of what a closed-set classifier claims. Urgent signals still win.
    out_of_vocabulary = not urgent_conflict and not in_vocabulary

    if out_of_vocabulary:
        outcome = "UNRELIABLE"
    elif (
        top1_score >= limits["suggested"]
        and margin >= limits["margin"]
        and not urgent_conflict
    ):
        outcome = "SUGGESTED"
    elif top1_score < limits["unreliable"] and not urgent_conflict:
        # Low overall confidence with no urgent signal: ask the passenger to
        # edit the transcript or pick a card instead of guessing.
        outcome = "UNRELIABLE"
    else:
        outcome = "REQUIRES_CHOICE"

    if outcome == "UNRELIABLE":
        return {
            "transcript": text,
            "suggested_intent": None,
            "attributes": {},
            "candidates": [],
            "outcome": "UNRELIABLE",
            "requires_choice": True,
        }

    candidates = _merge_urgent_candidates(ranked, flagged, limit=3)
    candidates_payload = [
        {"intent_id": intent_id, "score": round(float(score), 4)}
        for intent_id, score in candidates
    ]

    if outcome == "SUGGESTED":
        return {
            "transcript": text,
            "suggested_intent": {"intent_id": top1_id, "score": round(float(top1_score), 4)},
            "attributes": extract_attributes(top1_id, text, contract),
            "candidates": candidates_payload,
            "outcome": "SUGGESTED",
            "requires_choice": False,
        }

    return {
        "transcript": text,
        "suggested_intent": None,
        "attributes": {},
        "candidates": candidates_payload,
        "outcome": "REQUIRES_CHOICE",
        "requires_choice": True,
    }


__all__ = [
    "ATTRIBUTE_CUES",
    "REQUIRED_INTENT_IDS",
    "URGENT_IDS",
    "VoiceProcessingError",
    "classify_text",
    "extract_attributes",
    "get_classifier_readiness",
    "init_classifier",
    "load_intent_contract",
    "normalize_text",
    "probability_labels",
    "thresholds",
    "urgent_signals",
    "vocabulary_coverage",
]
