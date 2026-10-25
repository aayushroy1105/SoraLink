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

import logging

import json
import os
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_INTENTS_PATH = PROJECT_ROOT / "data" / "intents.json"
UPDATED_MODEL_DIR = PROJECT_ROOT / "Updated_Model" / "models" / "setfit_intent_classifier"
FALLBACK_MODEL_DIR = PROJECT_ROOT / "models" / "setfit_intent_classifier"
DEFAULT_CLASSIFIER_DIR = UPDATED_MODEL_DIR
logger = logging.getLogger(__name__)

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
DEFAULT_SUGGESTED_THRESHOLD = 0.60  # calibrated by scripts/train_classifier.py
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

#: Whisper -> classifier hand-off. A transcript the ASR itself doubts must never
#: become an auto-accepted suggestion; it is downgraded to REQUIRES_CHOICE.
ASR_MIN_AVG_LOGPROB = -1.0
ASR_MAX_NO_SPEECH_PROB = 0.6

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
        # Devanagari function words (grammar only; content nouns stay content).
        "है", "हैं", "हूँ", "हूं", "हो", "था", "थी", "थे", "में", "को", "से", "ने",
        "का", "की", "के", "और", "कि", "भी", "नहीं", "क्या", "यह", "वह", "ये", "वो",
        "इस", "उस", "एक", "कुछ", "बहुत", "थोड़ा", "थोड़ी", "कृपया", "जी", "लिए",
        "वाला", "वाली", "वाले", "गया", "गई", "हुआ", "हुई", "होने", "कर", "करने",
        "चाहिए", "चाहता", "चाहती", "दीजिए", "कीजिए", "बताइए", "पड़ा", "पड़ी",
        "कौन", "सा", "सी", "दिया", "देना", "भर", "अब", "किसको", "किस", "कहाँ", "कब",
        "कैसे", "क्यों", "सकता", "सकती", "सकते", "मुझे", "मेरा", "मेरी", "मेरे",
        "हमारा", "हमारी", "हमारे", "आप", "आपका", "आपकी", "आपके", "अपना", "अपनी",
        "साथ", "ऊपर", "नीचे", "करना", "किया", "होना", "होगा",
        # Gurmukhi function words.
        "ਹੈ", "ਹਨ", "ਸੀ", "ਵਿੱਚ", "ਨੂੰ", "ਦਾ", "ਦੀ", "ਦੇ", "ਤੋਂ", "ਤੇ", "ਲਈ",
        "ਵਾਲਾ", "ਵਾਲੀ", "ਵਾਲੇ", "ਕਿ", "ਵੀ", "ਨਹੀਂ", "ਕੀ", "ਇਹ", "ਉਹ", "ਇੱਕ",
        "ਕੁਝ", "ਬਹੁਤ", "ਥੋੜ੍ਹਾ", "ਗਿਆ", "ਗਈ", "ਕਰੋ", "ਕਰ", "ਕਰਨ", "ਚਾਹੀਦਾ",
        "ਚਾਹੀਦੀ", "ਦਿਓ", "ਲੱਗ", "ਪਿਆ", "ਪਈ",
        "ਨੇ", "ਕਿਵੇਂ", "ਕਿੱਥੇ", "ਕਦੋਂ", "ਕਿਉਂ", "ਰਿਹਾ", "ਰਹੀ", "ਰਹੇ", "ਸਕਦਾ",
        "ਸਕਦੀ", "ਸਕਦੇ", "ਮੈਨੂੰ", "ਮੇਰਾ", "ਮੇਰੀ", "ਮੇਰੇ", "ਸਾਡਾ", "ਸਾਡੀ", "ਸਾਡੇ",
        "ਤੁਸੀਂ", "ਤੁਹਾਡਾ", "ਤੁਹਾਡੀ", "ਤੁਹਾਡੇ", "ਆਪਣਾ", "ਆਪਣੀ", "ਨਾਲ", "ਵਿਚ",
        "ਉੱਤੇ", "ਕਰਨਾ", "ਕੀਤਾ", "ਹੋਣਾ", "ਹੋਵੇ", "ਜਾਂ", "ਜਾਵੇ", "ਕਿਰਪਾ", "ਕਰਕੇ",
    }
)

_VOCAB_CACHE: tuple[int, frozenset[str]] | None = None
_CJK_VOCAB_CACHE: tuple[int, frozenset[str]] | None = None

#: Words that only mean "urgent" together with the absence of routine context.
WEAK_URGENT_CUES = frozenset({"help", "madad", "मदद", "ਮਦਦ", "urgent", "urgently"})

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
        # Devanagari routine nouns: keep "... में मदद" requests routine.
        "बैग", "सामान", "कंबल", "तकिया", "पानी", "चाय", "कॉफ़ी", "खाना", "सीट",
        "टॉयलेट", "वॉशरूम", "स्क्रीन", "हेडफोन", "बच्चा", "बच्चे", "बोतल", "फॉर्म",
        "दूध", "रिमोट", "कपड़ा",
        # Gurmukhi routine nouns.
        "ਬੈਗ", "ਸਮਾਨ", "ਕੰਬਲ", "ਤਕੀਆ", "ਪਾਣੀ", "ਚਾਹ", "ਕੌਫੀ", "ਖਾਣਾ", "ਸੀਟ",
        "ਟਾਇਲਟ", "ਵਾਸ਼ਰੂਮ", "ਸਕ੍ਰੀਨ", "ਹੈੱਡਫੋਨ", "ਬੱਚਾ", "ਬੱਚੇ", "ਬੋਤਲ", "ਫਾਰਮ",
        "ਦੁੱਧ", "ਰਿਮੋਟ", "ਕੱਪੜਾ",
    }
)

#: Prior domain keywords for boosting low-resource multilingual transcripts (Indic scripts).
ROUTINE_KEYWORD_MAP: dict[str, list[str]] = {
    "seat_issue": ["ਸੀਟ", "ਸਿਟ", "ਸੀਟਬੈਲਟ", "ਕੁਰਸੀ", "सीट", "सीटबेल्ट"],
    "meal_inquiry": ["ਖਾਣਾ", "ਭੋਜਨ", "ਖਾਣ", "ਰੋਟੀ", "khana", "खाना", "भोजन", "लंच", "डिनर"],
    "water_request": ["ਪਾਣੀ", "ਜਲ", "paani", "पानी", "जल"],
    "tea_coffee": ["ਕੌਫੀ", "ਕਾਫੀ", "ਚਾਹ", "chai", "चाय", "कॉफी", "कॉफ़ी"],
    "bag_help": ["ਸੂਟਕੇਸ", "ਅਟੈਚੀ", "ਬੈਗ", "ਸਮਾਨ", "बैग", "सूटकेस", "सामान"],
    "blanket_request": ["ਕੰਬਲ", "kambal", "कंबल"],
    "pillow_request": ["ਤਕੀਆ", "ਸਿਰਹਾਣਾ", "takiya", "तकिया", "सिरहाना"],
    "lavatory_assist": ["ਵਾਸ਼ਰੂਮ", "ਟਾਇਲਟ", "ਗੁਸਲਖਾਨਾ", "वॉशरूम", "शौचालय", "टॉयलेट"],
    "customs_form": ["ਕਸਟਮ", "ਫਾਰਮ", "ਡੈਕਲਰੇਸ਼ਨ", "ਕਾਰਡ", "फॉर्म", "कस्टम", "कार्ड"],
    "headphone_request": ["ਹੈੱਡਫੋਨ", "ਈਅਰਫੋਨ", "हेडफोन", "इयरफोन"],
    "baby_care": ["ਬੇਬੀ", "ਡਾਇਪਰ", "ਦੁੱਧ ਦੀ ਬੋਤਲ", "डायपर", "बेबी"],
}

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
#: Japanese/Korean-script detection. These scripts have no word spaces, so the
#: whitespace-token coverage gate would reject every phrase; coverage for them is
#: measured with character bigrams instead.
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]")
_CJK_RUN_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]+")


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
def fix_mixed_indic(text: str) -> str:
    """Harmonize stray Devanagari characters in Gurmukhi phrases (or vice versa)."""
    if not text:
        return ""
    dev_count = sum(1 for ch in text if 0x0900 <= ord(ch) <= 0x097F)
    gur_count = sum(1 for ch in text if 0x0A00 <= ord(ch) <= 0x0A7F)
    if gur_count > 0 and dev_count > 0:
        if gur_count >= dev_count:
            chars = []
            for ch in text:
                code = ord(ch)
                if 0x0900 <= code <= 0x097F:
                    target = code + 0x0100
                    try:
                        name = unicodedata.name(chr(target))
                        if "GURMUKHI" in name:
                            chars.append(chr(target))
                            continue
                    except ValueError:
                        pass
                chars.append(ch)
            return "".join(chars)
        else:
            chars = []
            for ch in text:
                code = ord(ch)
                if 0x0A00 <= code <= 0x0A7F:
                    target = code - 0x0100
                    try:
                        name = unicodedata.name(chr(target))
                        if "DEVANAGARI" in name:
                            chars.append(chr(target))
                            continue
                    except ValueError:
                        pass
                chars.append(ch)
            return "".join(chars)
    return text


def normalize_text(text: str | None) -> str:
    """Trim control characters/extra whitespace/repeated punctuation.

    Unicode is NFC-normalised so Devanagari and Gurmukhi stay intact; stray mixed
    Indic script characters are harmonized.
    """
    if text is None:
        return ""
    value = unicodedata.normalize("NFC", str(text))
    value = fix_mixed_indic(value)
    value = _CONTROL_CHARS_RE.sub(" ", value)
    value = _REPEATED_PUNCT_RE.sub(r"\1", value)
    value = _WHITESPACE_RE.sub(" ", value)
    return value.strip()


#: Whisper spells Hindi/Punjabi loanwords inconsistently ("pani" vs the catalog's
#: "paani"). Folding the known variants onto the trained spelling makes keyword
#: matching and the vocabulary gate survive common ASR spellings.
_ROMANIZED_VARIANTS: dict[str, str] = {
    "pani": "paani",
    "panee": "paani",
    "panni": "paani",
    "dudh": "doodh",
    "dood": "doodh",
    "kambhal": "kambal",
    "kambl": "kambal",
    "kambaal": "kambal",
    "takia": "takiya",
    "takiyaa": "takiya",
    "takiye": "takiya",
    "khaana": "khana",
    "khanna": "khana",
    "chay": "chai",
    "chae": "chai",
    "davai": "dawa",
    "dawai": "dawa",
    "dava": "dawa",
    "thandaa": "thanda",
    "tanda": "thanda",
    "garm": "garam",
    "bachche": "bache",
    "bachhe": "bache",
    "bacha": "bache",
    "washrom": "washroom",
    "toilit": "toilet",
    "blankit": "blanket",
    "sikbag": "sick bag",
}

#: Diacritics Whisper emits for transliterated loanwords.
_ROMAN_DIACRITICS = str.maketrans(
    {
        "ā": "a", "á": "a", "à": "a", "ī": "i", "í": "i", "ū": "u", "ú": "u",
        "ē": "e", "é": "e", "ō": "o", "ó": "o", "ṇ": "n", "ñ": "n", "ṭ": "t",
        "ḍ": "d", "ṛ": "r", "ś": "s", "ṃ": "m", "ṁ": "m",
    }
)
_LATIN_WORD_RE = re.compile(r"[A-Za-z\u00C0-\u024F]+")
#: Conversational fillers Whisper puts in front of a request ("Okay, can I get...").
_LEADING_FILLER_RE = re.compile(
    r"^(?:(?:okay|ok|so|um+|uh+|hmm+|yeah|alright|well|actually)[,.!\s]+)+", re.IGNORECASE
)


def canonicalize_romanized(text: str | None) -> str:
    """Fold known ASR spellings of Hinglish/Hindi/Punjabi words onto catalog spellings."""
    if not text:
        return ""

    def merge(match: re.Match[str]) -> str:
        token = match.group(0)
        folded = token.casefold().translate(_ROMAN_DIACRITICS)
        return _ROMANIZED_VARIANTS.get(folded, token)

    return _LATIN_WORD_RE.sub(merge, str(text))


def strip_asr_noise(text: str | None) -> str:
    """Drop leading conversational fillers the ASR prepends to a real request."""
    value = normalize_text(text)
    previous = None
    while previous != value:
        previous = value
        value = _LEADING_FILLER_RE.sub("", value).strip()
    return value


def asr_transcript_uncertain(asr: dict[str, Any] | None) -> bool:
    """True when Whisper's own confidence says the transcript is shaky."""
    if not asr:
        return False
    try:
        avg = asr.get("avg_logprob")
        if avg is not None and float(avg) < ASR_MIN_AVG_LOGPROB:
            return True
        no_speech = asr.get("no_speech_prob")
        if no_speech is not None and float(no_speech) > ASR_MAX_NO_SPEECH_PROB:
            return True
    except (TypeError, ValueError):
        return False
    return False


def matching_view(text: str | None) -> str:
    """The text used for cues, attributes and coverage (never shown to the user)."""
    return canonicalize_romanized(strip_asr_noise(text))


def _tokens(text: str) -> set[str]:
    return {tok.casefold() for tok in _TOKEN_RE.findall(text)}


def _phrase_present(text_lower: str, phrase: str) -> bool:
    """Whole-word/phrase match that also tolerates apostrophes, punctuation, and nuktas."""
    if _CJK_RE.search(phrase):
        # CJK has no word boundaries; substring matching is the practical rule.
        return phrase in text_lower

    def _match(t: str, p: str) -> bool:
        if " " in p or "'" in p:
            pattern = re.escape(p).replace(r"\ ", r"[\s,.;!?]+")
            return re.search(rf"(?<!\w){pattern}(?!\w)", t) is not None
        return re.search(rf"(?<!\w){re.escape(p)}(?!\w)", t) is not None

    if _match(text_lower, phrase):
        return True

    # Tolerate Indic nukta variations (U+093C Devanagari, U+0A3C Gurmukhi)
    if "\u093c" in text_lower or "\u0a3c" in text_lower or "\u093c" in phrase or "\u0a3c" in phrase:
        clean_t = text_lower.replace("\u093c", "").replace("\u0a3c", "")
        clean_p = phrase.replace("\u093c", "").replace("\u0a3c", "")
        return _match(clean_t, clean_p)

    return False


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
    for kws in ROUTINE_KEYWORD_MAP.values():
        for kw in kws:
            vocabulary.update(_TOKEN_RE.findall(str(kw).casefold()))
    frozen = frozenset(vocabulary)
    _VOCAB_CACHE = (key, frozen)
    return frozen


def _cjk_dominant(text: str) -> bool:
    """True when most letters in ``text`` are Japanese/CJK characters."""
    letters = [ch for ch in text if ch.isalnum()]
    cjk = sum(1 for ch in text if _CJK_RE.match(ch))
    return cjk >= 2 and cjk / max(1, len(letters)) >= 0.5


def _bigrams(value: str) -> set[str]:
    return {value[index] + value[index + 1] for index in range(len(value) - 1)}


def request_cjk_vocabulary(contract: dict[str, Any]) -> frozenset[str]:
    """Character bigrams of every CJK chunk the catalog knows."""
    global _CJK_VOCAB_CACHE
    key = id(contract)
    if _CJK_VOCAB_CACHE is not None and _CJK_VOCAB_CACHE[0] == key:
        return _CJK_VOCAB_CACHE[1]
    grams: set[str] = set()
    for entry in contract["intents"]:
        chunks: list[str] = [entry["intent_id"]]
        chunks.extend(entry.get("training_examples", []))
        chunks.extend(entry.get("urgent_keywords", []))
        chunks.extend((entry.get("labels") or {}).values())
        for chunk in chunks:
            for run in _CJK_RUN_RE.findall(str(chunk)):
                grams.update(_bigrams(run))
    frozen = frozenset(grams)
    _CJK_VOCAB_CACHE = (key, frozen)
    return frozen


def vocabulary_coverage(text: str, contract: dict[str, Any] | None = None) -> float:
    """Fraction of content units that appear in the catalog vocabulary.

    Whitespace tokens are used for Latin/Devanagari/Gurmukhi text; Japanese and
    other CJK scripts are measured with character bigrams because they have no
    word spaces (token-based coverage would reject every phrase).
    """
    contract = contract or load_intent_contract()
    normalized = normalize_text(text).casefold()
    if _cjk_dominant(normalized):
        text_bigrams: set[str] = set()
        for run in _CJK_RUN_RE.findall(normalized):
            text_bigrams.update(_bigrams(run))
        if not text_bigrams:
            return 1.0
        vocabulary = request_cjk_vocabulary(contract)
        return sum(1 for gram in text_bigrams if gram in vocabulary) / len(text_bigrams)
    tokens = [t for t in _TOKEN_RE.findall(normalized) if len(t) > 1]
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
    model_dir: str | None = None


_STATE = _ClassifierState()
_STATE_LOCK = threading.Lock()


def _classifier_dir() -> Path:
    env_dir = os.environ.get("SORALINK_MODEL_DIR") or os.environ.get("SORALINK_CLASSIFIER_DIR")
    if env_dir:
        return Path(env_dir)
    if UPDATED_MODEL_DIR.exists():
        return UPDATED_MODEL_DIR
    return DEFAULT_CLASSIFIER_DIR


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


REQUIRED_MODEL_FILES = ("config.json", "config_setfit.json", "model_head.pkl")


def _validate_model_files(model_dir: Path) -> tuple[bool, str | None]:
    """Validate that required SetFit model assets exist and are non-empty."""
    if not model_dir.exists() or not model_dir.is_dir():
        return False, f"Directory does not exist: {model_dir}"
    for req in REQUIRED_MODEL_FILES:
        target = model_dir / req
        if not target.exists():
            return False, f"Missing required model file: {req}"
        if target.stat().st_size == 0:
            return False, f"Corrupted empty model file: {req}"
    has_weights = (model_dir / "model.safetensors").exists() or (model_dir / "pytorch_model.bin").exists()
    if not has_weights:
        return False, "Missing model weights (neither model.safetensors nor pytorch_model.bin found)"
    weights_path = (model_dir / "model.safetensors") if (model_dir / "model.safetensors").exists() else (model_dir / "pytorch_model.bin")
    if weights_path.stat().st_size == 0:
        return False, f"Corrupted empty model weights file: {weights_path.name}"
    return True, None


def init_classifier(force: bool = False) -> bool:
    """Load the fine-tuned SetFit model once. Returns True when usable."""
    with _STATE_LOCK:
        if _STATE.model is not None and not force:
            return True
        _STATE.model = None
        _STATE.labels = []
        _STATE.load_error = None
        _STATE.model_dir = None

        env_dir = os.environ.get("SORALINK_MODEL_DIR") or os.environ.get("SORALINK_CLASSIFIER_DIR")
        candidate_dirs: list[tuple[Path, bool]] = []
        if env_dir:
            candidate_dirs = [(Path(env_dir), False)]
        else:
            candidate_dirs = [(UPDATED_MODEL_DIR, False)]
            if FALLBACK_MODEL_DIR.exists() and FALLBACK_MODEL_DIR != UPDATED_MODEL_DIR:
                candidate_dirs.append((FALLBACK_MODEL_DIR, True))

        last_exc: Exception | None = None
        for model_dir, is_fallback in candidate_dirs:
            if not model_dir.exists():
                logger.warning("Classifier directory not found: %s", model_dir)
                continue

            valid, validation_err = _validate_model_files(model_dir)
            if not valid:
                logger.warning("Classifier validation failed for %s: %s", model_dir, validation_err)
                last_exc = ValueError(validation_err)
                continue

            if is_fallback:
                logger.warning(
                    "EXPLICIT FALLBACK: Primary model at %s is unavailable. Falling back to legacy model at %s",
                    UPDATED_MODEL_DIR,
                    model_dir,
                )

            try:
                logger.info("Loading SetFit intent classifier from %s", model_dir)
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
                _STATE.model_dir = str(model_dir)
                logger.info(
                    "Loaded SetFit intent classifier from %s on device %s (fallback=%s)",
                    model_dir,
                    device,
                    is_fallback,
                )
                return True
            except Exception as exc:  # pragma: no cover - depends on local weights
                last_exc = exc
                logger.error("Failed to load classifier from %s: %s", model_dir, exc)

        _STATE.model = None
        _STATE.labels = []
        if last_exc:
            _STATE.load_error = f"{type(last_exc).__name__}: {last_exc}"
        else:
            primary_path = candidate_dirs[0][0] if candidate_dirs else "none"
            _STATE.load_error = f"classifier directory not found at {primary_path}"
        return False


def get_loaded_model_dir() -> str | None:
    """Return the filesystem path of the loaded intent classifier model, if any."""
    return getattr(_STATE, "model_dir", None)


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
    strong_urgent_ids: Iterable[str] = (),
) -> list[tuple[str, float]]:
    """Top ``limit`` intents, guaranteeing every flagged urgent intent is present.
    Strong urgent intents with verified cues are prioritized to the top.
    """
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

    strong_set = set(strong_urgent_ids)
    if strong_set:
        for idx, (intent_id, score) in enumerate(selected):
            if intent_id in strong_set:
                if idx != 0:
                    item = selected.pop(idx)
                    selected.insert(0, item)
                break

    return selected[:limit]


def classify_text(transcript: str, *, asr: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify a transcript into the frozen vocabulary and pick a preview outcome.

    ``asr`` is optional Whisper telemetry (``avg_logprob``, ``no_speech_prob``).
    When the recogniser itself doubts the transcript, an otherwise confident
    prediction is capped at REQUIRES_CHOICE so the passenger confirms rather
    than the pipeline guessing on a misheard request.
    """
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

    # Cues, attributes and the vocabulary gate run on the ASR-tolerant view;
    # the returned transcript stays what the passenger actually said.
    matched = matching_view(text) or text
    asr_uncertain = asr_transcript_uncertain(asr)

    scores = _model_probabilities(matched)
    signals = urgent_signals(matched, contract)
    matched_lower = matched.casefold()

    # 1. Prioritize strong urgent cues (safety, medical, sickness, accessibility)
    strong_signals = [s for s in signals if s.get("strength") == "strong"]
    for s in strong_signals:
        intent_id = s["intent_id"]
        if intent_id in scores:
            scores[intent_id] = max(scores[intent_id], 0.95)

    # 2. Routine domain keyword prior boosting with baby care disambiguation
    has_medical_signal = any(s["intent_id"] == "medical_help" for s in signals)
    for intent_id, kws in ROUTINE_KEYWORD_MAP.items():
        if intent_id == "baby_care":
            # Don't boost baby_care when a medical condition or water request is present
            if has_medical_signal or any(
                w in matched_lower
                for w in ["ਬੁਖਾਰ", "ਦਰਦ", "ਉਲਟੀ", "ਦਵਾਈ", "चोट", "दर्द", "बुखार", "उल्टी", "दवा", "fever", "pain", "sick"]
            ):
                continue
            if "water_request" in scores and any(w in matched_lower for w in ["ਪਾਣੀ", "पानी", "water", "paani"]):
                continue
        for kw in kws:
            if _phrase_present(matched_lower, kw.casefold()):
                if intent_id in scores:
                    scores[intent_id] = min(0.98, scores[intent_id] + 0.40)
                break

    ranked = _rank(scores)
    top1_id, top1_score = ranked[0]
    top2_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = top1_score - top2_score

    in_vocabulary = vocabulary_coverage(matched, contract) >= min_vocab_coverage()
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
        and not asr_uncertain  # a shaky transcript is confirmed, never auto-filed
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

    candidates = _merge_urgent_candidates(
        ranked,
        flagged,
        limit=3,
        strong_urgent_ids=[s["intent_id"] for s in strong_signals],
    )
    candidates_payload = [
        {"intent_id": intent_id, "score": round(float(score), 4)}
        for intent_id, score in candidates
    ]

    if outcome == "SUGGESTED":
        return {
            "transcript": text,
            "suggested_intent": {"intent_id": top1_id, "score": round(float(top1_score), 4)},
            "attributes": extract_attributes(top1_id, matched, contract),
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
    "ASR_MAX_NO_SPEECH_PROB",
    "ASR_MIN_AVG_LOGPROB",
    "asr_transcript_uncertain",
    "canonicalize_romanized",
    "classify_text",
    "extract_attributes",
    "matching_view",
    "strip_asr_noise",
    "get_classifier_readiness",
    "init_classifier",
    "load_intent_contract",
    "normalize_text",
    "probability_labels",
    "thresholds",
    "urgent_signals",
    "vocabulary_coverage",
    "get_loaded_model_dir",
    "ClassifierError",
    "load_intent_catalog",
    "get_confidence_threshold",
    "classify_intent",
    "reset_classifier",
]


# ---------------------------------------------------------------------------
# Backend compatibility adapter
# ---------------------------------------------------------------------------

class ClassifierError(Exception):
    """Raised when the intent catalog or classifier configuration is invalid."""


def load_intent_catalog(
    catalog_path: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    """Expose the validated AI contract in the format expected by app.py."""
    contract = load_intent_contract(catalog_path)
    catalog: list[dict[str, Any]] = []

    for entry in contract["intents"]:
        labels = entry.get("labels") or {}
        catalog.append({
            **entry,
            "id": entry["intent_id"],
            "label": labels.get("en") or entry["intent_id"],
            "priority": entry["priority"].lower(),
        })

    return catalog


def get_confidence_threshold() -> float:
    """Compatibility accessor for the AI classifier's suggestion threshold."""
    return thresholds()["suggested"]


def classify_intent(text: str) -> dict[str, Any]:
    """Adapt strict AI outcomes to the legacy backend response shape.

    A request is only suggested when classify_text explicitly returns
    SUGGESTED. Ambiguous and unreliable outcomes never become guesses.
    """
    result = classify_text(text)
    outcome = result["outcome"]
    catalog = {
        item["id"]: item for item in load_intent_catalog()
    }

    candidates = []
    for candidate in result.get("candidates", []):
        intent_id = candidate["intent_id"]
        item = catalog.get(intent_id, {})
        candidates.append({
            "intent_id": intent_id,
            "label": item.get("label", intent_id),
            "priority": item.get("priority", "routine"),
            "confidence": float(candidate["score"]),
        })

    suggested = result.get("suggested_intent")
    if outcome == "SUGGESTED" and suggested:
        intent_id = suggested["intent_id"]
        item = catalog[intent_id]
        return {
            "ok": True,
            "intent_id": intent_id,
            "confidence": float(suggested["score"]),
            "priority": item["priority"],
            "alternatives": [
                candidate for candidate in candidates
                if candidate["intent_id"] != intent_id
            ],
            "needs_visual_fallback": False,
            "reason": None,
            "outcome": outcome,
            "attributes": result.get("attributes", {}),
            "requires_choice": False,
        }

    return {
        "ok": False,
        "intent_id": None,
        "confidence": candidates[0]["confidence"] if candidates else 0.0,
        "priority": None,
        "alternatives": candidates,
        "needs_visual_fallback": True,
        "reason": outcome.lower(),
        "outcome": outcome,
        "attributes": {},
        "requires_choice": True,
    }


def reset_classifier() -> None:
    """Reset the cached AI model state for tests and model replacement."""
    with _STATE_LOCK:
        _STATE.model = None
        _STATE.labels = []
        _STATE.device = None
        _STATE.load_error = None
