
"""Local intent classification for SoraLink.

The classifier proposes an intent only. It never creates a passenger
request; the passenger must review and confirm the suggestion.

SetFit is loaded lazily so the rest of the application can start even
when the optional model dependencies or local model files are missing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CATALOG_PATH = BASE_DIR / "data" / "intents.json"
DEFAULT_MODEL_PATH = BASE_DIR / "models" / "intent-classifier"

DEFAULT_CONFIDENCE_THRESHOLD = 0.72


class ClassifierError(Exception):
    """Raised when the intent catalog or classifier configuration is invalid."""


def load_intent_catalog(
    catalog_path: str | Path = DEFAULT_CATALOG_PATH,
) -> list[dict[str, Any]]:
    """Load and validate the canonical intent catalog."""
    path = Path(catalog_path)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClassifierError(f"Cannot load intent catalog: {path}") from exc

    intents = payload.get("intents")
    if not isinstance(intents, list) or not intents:
        raise ClassifierError("Intent catalog must contain a non-empty intents list")

    seen: set[str] = set()
    validated: list[dict[str, Any]] = []

    for item in intents:
        if not isinstance(item, dict):
            raise ClassifierError("Every catalog intent must be an object")

        intent_id = item.get("id")
        priority = item.get("priority")

        if not isinstance(intent_id, str) or not intent_id.strip():
            raise ClassifierError("Every intent must have a non-empty ID")

        if intent_id in seen:
            raise ClassifierError(f"Duplicate intent ID: {intent_id}")

        if priority not in {"urgent", "routine"}:
            raise ClassifierError(f"Invalid priority for intent: {intent_id}")

        seen.add(intent_id)
        validated.append(item)

    return validated


def get_confidence_threshold() -> float:
    """Read the configurable initial confidence threshold."""
    raw = os.environ.get("SORALINK_CONFIDENCE_THRESHOLD")

    if raw is None:
        try:
            catalog = json.loads(
                DEFAULT_CATALOG_PATH.read_text(encoding="utf-8")
            )
            raw = str(
                catalog.get(
                    "confidence_threshold",
                    DEFAULT_CONFIDENCE_THRESHOLD,
                )
            )
        except (OSError, json.JSONDecodeError):
            raw = str(DEFAULT_CONFIDENCE_THRESHOLD)

    try:
        threshold = float(raw)
    except (TypeError, ValueError) as exc:
        raise ClassifierError("Confidence threshold must be numeric") from exc

    if not 0.0 <= threshold <= 1.0:
        raise ClassifierError("Confidence threshold must be between 0 and 1")

    return threshold


def _normalise_probabilities(
    probabilities: Any,
    catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert model probabilities to ranked catalog candidates."""
    if hasattr(probabilities, "tolist"):
        probabilities = probabilities.tolist()

    # SetFit predict_proba commonly returns one row per input.
    if (
        isinstance(probabilities, list)
        and probabilities
        and isinstance(probabilities[0], list)
    ):
        probabilities = probabilities[0]

    if not isinstance(probabilities, (list, tuple)):
        raise ClassifierError("Model returned an unsupported probability format")

    if len(probabilities) != len(catalog):
        raise ClassifierError(
            "Model output count does not match the intent catalog. "
            "Check the model's label order and catalog version."
        )

    candidates = []

    for intent, probability in zip(catalog, probabilities):
        try:
            confidence = float(probability)
        except (TypeError, ValueError) as exc:
            raise ClassifierError("Model returned a non-numeric probability") from exc

        if not 0.0 <= confidence <= 1.0:
            raise ClassifierError("Model returned an invalid probability")

        candidates.append({
            "intent_id": intent["id"],
            "label": intent.get("label", intent["id"]),
            "priority": intent["priority"],
            "confidence": confidence,
        })

    candidates.sort(key=lambda item: item["confidence"], reverse=True)
    return candidates


class IntentClassifier:
    """Optional local SetFit classifier with safe fallback behavior."""

    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        catalog_path: str | Path = DEFAULT_CATALOG_PATH,
        confidence_threshold: float | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.catalog_path = Path(catalog_path)
        self.catalog = load_intent_catalog(self.catalog_path)

        self.confidence_threshold = (
            get_confidence_threshold()
            if confidence_threshold is None
            else float(confidence_threshold)
        )

        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ClassifierError("Confidence threshold must be between 0 and 1")

        self._model = None
        self._load_attempted = False
        self._load_error: str | None = None

    def _load_model(self) -> bool:
        """Load the local SetFit model once, without network downloads."""
        if self._load_attempted:
            return self._model is not None

        self._load_attempted = True

        if not self.model_path.is_dir():
            self._load_error = f"Local model directory not found: {self.model_path}"
            return False

        try:
            from setfit import SetFitModel

            # Local-only loading prevents accidental model downloads.
            self._model = SetFitModel.from_pretrained(
                str(self.model_path),
                local_files_only=True,
            )
            return True
        except Exception as exc:
            self._model = None
            self._load_error = (
                f"Unable to load local SetFit model: {type(exc).__name__}"
            )
            return False

    KEYWORD_MAP = {
        # Urgent intents
        "medical_help": ["medical", "doctor", "heart", "chest pain", "bleeding", "emergency", "ambulance", "physician", "help"],
        "motion_sickness": ["airsick", "vomit", "barf", "nausea", "throw up", "throwup", "queasy", "dizzy", "sick"],
        "safety_concern": ["safety", "smoke", "fire", "danger", "hazard", "sparks"],
        "accessibility_assist": ["wheelchair", "blind", "deaf", "mobility", "walk", "disabled"],
        # Routine intents
        "water_request": ["water", "drink", "thirsty", "hydrate", "mineral water"],
        "blanket_request": ["blanket", "cold", "chilly", "freeze", "freezing"],
        "pillow_request": ["pillow", "cushion", "headrest"],
        "tea_coffee": ["tea", "coffee", "latte", "espresso", "cappuccino", "hot drink", "green tea"],
        "bag_help": ["bag", "luggage", "overhead", "bin", "suitcase", "carry-on", "carryon"],
        "headphone_request": ["headphone", "headphones", "earphone", "earphones", "earbuds", "audio jack"],
        "meal_inquiry": ["meal", "food", "dinner", "lunch", "breakfast", "snack", "eat", "menu", "vegetarian"],
        "lavatory_assist": ["lavatory", "toilet", "bathroom", "restroom", "wc"],
        "seat_issue": ["seat", "recline", "seatbelt", "broken seat", "tray table", "armrest"],
        "customs_form": ["customs", "immigration", "arrival form", "landing card", "passport control", "declaration"],
        "baby_care": ["baby", "infant", "diaper", "nappy", "stroller", "bassinet", "formula", "bottle"],
    }

    def _match_rules(self, text: str) -> dict[str, Any] | None:
        """Rule-based pattern matching for offline and urgent intent fallback."""
        import re
        lower = text.lower()
        scores: dict[str, float] = {}
        catalog_map = {item["id"]: item for item in self.catalog}

        for intent_id, keywords in self.KEYWORD_MAP.items():
            if intent_id not in catalog_map:
                continue
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", lower):
                    item = catalog_map[intent_id]
                    base_score = 0.88 if item["priority"] == "urgent" else 0.85
                    scores[intent_id] = max(scores.get(intent_id, 0.0), base_score)

        if not scores:
            return None

        sorted_ids = sorted(
            scores.keys(),
            key=lambda i_id: (
                scores[i_id],
                1 if catalog_map[i_id]["priority"] == "urgent" else 0,
            ),
            reverse=True,
        )

        candidates = []
        for i_id in sorted_ids:
            item = catalog_map[i_id]
            candidates.append({
                "intent_id": i_id,
                "label": item.get("label", i_id),
                "priority": item["priority"],
                "confidence": scores[i_id],
            })

        best = candidates[0]
        if len(candidates) > 1 and candidates[0]["confidence"] == candidates[1]["confidence"] and candidates[0]["priority"] == candidates[1]["priority"]:
            return {
                "ok": False,
                "intent_id": None,
                "confidence": 0.50,
                "alternatives": candidates[:3],
                "needs_visual_fallback": True,
                "reason": "ambiguous_match",
            }

        return {
            "ok": True,
            "intent_id": best["intent_id"],
            "confidence": best["confidence"],
            "priority": best["priority"],
            "alternatives": candidates[1:4],
            "needs_visual_fallback": False,
            "reason": None,
        }

    def classify(self, text: str) -> dict[str, Any]:
        """Suggest an intent and ranked alternatives for passenger review."""
        if not isinstance(text, str) or not text.strip():
            return {
                "ok": False,
                "intent_id": None,
                "confidence": 0.0,
                "alternatives": [],
                "needs_visual_fallback": True,
                "reason": "empty_input",
            }

        if not self._load_model():
            rule_match = self._match_rules(text)
            if rule_match is not None:
                return rule_match
            return {
                "ok": False,
                "intent_id": None,
                "confidence": 0.0,
                "alternatives": [],
                "needs_visual_fallback": True,
                "reason": "model_unavailable",
            }

        try:
            probabilities = self._model.predict_proba([text.strip()])
            candidates = _normalise_probabilities(
                probabilities,
                self.catalog,
            )
        except Exception:
            return {
                "ok": False,
                "intent_id": None,
                "confidence": 0.0,
                "alternatives": [],
                "needs_visual_fallback": True,
                "reason": "classification_failed",
            }

        best = candidates[0] if candidates else None

        if best is None or best["confidence"] < self.confidence_threshold:
            rule_match = self._match_rules(text)
            if rule_match is not None and rule_match.get("priority") == "urgent":
                return rule_match
            return {
                "ok": False,
                "intent_id": None,
                "confidence": best["confidence"] if best else 0.0,
                "alternatives": candidates[:3],
                "needs_visual_fallback": True,
                "reason": "low_confidence",
            }

        return {
            "ok": True,
            "intent_id": best["intent_id"],
            "confidence": best["confidence"],
            "priority": best["priority"],
            "alternatives": candidates[1:4],
            "needs_visual_fallback": False,
            "reason": None,
        }


_default_classifier: IntentClassifier | None = None


def classify_intent(text: str) -> dict[str, Any]:
    """Convenience function used by application code."""
    global _default_classifier

    if _default_classifier is None:
        _default_classifier = IntentClassifier()

    return _default_classifier.classify(text)


def reset_classifier() -> None:
    """Reset the cached classifier, useful for tests and model replacement."""
    global _default_classifier
    _default_classifier = None
