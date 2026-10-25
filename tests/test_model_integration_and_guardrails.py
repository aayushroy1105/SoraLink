"""Tests for model integration, fallback, canonical intent categories, and normalization guardrails."""

import os
from pathlib import Path
import pytest

import classifier


def test_15_canonical_intents_exist_and_match():
    contract = classifier.load_intent_contract()
    intents = contract["intents"]
    assert len(intents) == 15
    intent_ids = [item["intent_id"] for item in intents]
    expected_ids = [
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
    ]
    assert intent_ids == expected_ids
    assert set(classifier.REQUIRED_INTENT_IDS) == set(expected_ids)


def test_soralink_model_dir_env_override(monkeypatch):
    custom_dir = Path("/nonexistent/model/dir")
    monkeypatch.setenv("SORALINK_MODEL_DIR", str(custom_dir))
    # Should resolve to custom_dir and fail init with clear error rather than silently loading old model
    resolved = classifier._classifier_dir()
    assert resolved == custom_dir
    assert classifier.init_classifier(force=True) is False
    assert "not found" in (classifier._STATE.load_error or "").lower()

    # Valid dir should be used
    real_dir = classifier.DEFAULT_CLASSIFIER_DIR
    monkeypatch.setenv("SORALINK_MODEL_DIR", str(real_dir))
    assert classifier._classifier_dir() == real_dir


def test_strip_asr_noise():
    assert classifier.strip_asr_noise("Um, okay, can I get a bottle of water?") == "can I get a bottle of water?"
    assert classifier.strip_asr_noise("Well, actually, I feel dizzy") == "I feel dizzy"
    assert classifier.strip_asr_noise("Alright, please help me") == "please help me"
    assert classifier.strip_asr_noise("Um uh okay so can I have tea") == "can I have tea"


def test_romanized_speech_normalization():
    assert classifier.canonicalize_romanized("pani please") == "paani please"
    assert classifier.canonicalize_romanized("panee chahiye") == "paani chahiye"
    assert classifier.canonicalize_romanized("washrom kahan hai") == "washroom kahan hai"
    assert classifier.canonicalize_romanized("davai de do") == "dawa de do"
    assert classifier.canonicalize_romanized("kambhal la do") == "kambal la do"
    assert classifier.canonicalize_romanized("takia chahiye") == "takiya chahiye"
    assert classifier.canonicalize_romanized("khaana kab milega") == "khana kab milega"
    assert classifier.canonicalize_romanized("chay milegi") == "chai milegi"


def test_indic_grammar_and_routine_filtering():
    contract = classifier.load_intent_contract()
    # Hindi function words ignored in coverage
    cov = classifier.vocabulary_coverage("मुझे पानी चाहिए", contract)
    assert cov == 1.0

    # Punjabi function words ignored in coverage
    cov_pa = classifier.vocabulary_coverage("ਮੈਨੂੰ ਪਾਣੀ ਚਾਹੀਦਾ ਹੈ", contract)
    assert cov_pa == 1.0


def test_cjk_bigram_matching():
    contract = classifier.load_intent_contract()
    # Japanese character matching without word spaces
    cov_ja = classifier.vocabulary_coverage("お水をください", contract)
    assert cov_ja == 1.0

    cov_blanket = classifier.vocabulary_coverage("毛布をもう一枚いただけますか", contract)
    assert cov_blanket >= classifier.min_vocab_coverage()


def test_safety_guardrails_weak_vs_strong_cues():
    contract = classifier.load_intent_contract()

    # "Help me with my bag" -> routine context suppresses weak "help" cue
    signals = classifier.urgent_signals("Help me with my bag", contract)
    assert signals == []

    # "Help me, I cannot breathe" -> "breathe" is strong urgent medical cue
    signals = classifier.urgent_signals("Help me, I cannot breathe", contract)
    assert any(s["intent_id"] == "medical_help" and s["strength"] == "strong" for s in signals)

    # "There is smoke in the cabin" -> "smoke" is strong safety cue
    signals = classifier.urgent_signals("There is smoke in the cabin", contract)
    assert any(s["intent_id"] == "safety_concern" and s["strength"] == "strong" for s in signals)

    # "I feel dizzy and might vomit" -> "dizzy", "vomit" are strong motion sickness cues
    signals = classifier.urgent_signals("I feel dizzy and might vomit", contract)
    assert any(s["intent_id"] == "motion_sickness" and s["strength"] == "strong" for s in signals)


def test_attribute_extraction_water_and_meals():
    contract = classifier.load_intent_contract()

    attrs_cold = classifier.extract_attributes("water_request", "Can I get some cold water please", contract)
    assert attrs_cold == {"temperature": "COLD"}

    attrs_warm = classifier.extract_attributes("water_request", "गरम पानी चाहिए", contract)
    assert attrs_warm == {"temperature": "WARM"}

    attrs_veg = classifier.extract_attributes("meal_inquiry", "Do you have vegetarian meal", contract)
    assert attrs_veg == {"dietary": "VEG"}

    attrs_nonveg = classifier.extract_attributes("meal_inquiry", "I want the chicken dinner", contract)
    assert attrs_nonveg == {"dietary": "NON_VEG"}

    attrs_snack = classifier.extract_attributes("meal_inquiry", "Can I have some snacks and chips", contract)
    assert attrs_snack == {"dietary": "SNACK"}


def test_default_model_path_resolution(monkeypatch):
    monkeypatch.delenv("SORALINK_MODEL_DIR", raising=False)
    monkeypatch.delenv("SORALINK_CLASSIFIER_DIR", raising=False)
    resolved = classifier._classifier_dir()
    assert resolved == classifier.UPDATED_MODEL_DIR
    assert "Updated_Model" in str(resolved)
    assert resolved.exists()


def test_explicit_fallback_behavior(caplog):
    import logging
    original_updated_dir = classifier.UPDATED_MODEL_DIR
    nonexistent = classifier.PROJECT_ROOT / "Updated_Model" / "nonexistent_classifier"
    try:
        classifier.UPDATED_MODEL_DIR = nonexistent
        with caplog.at_level(logging.WARNING):
            # When UPDATED_MODEL_DIR is missing, init_classifier logs explicit fallback warning
            success = classifier.init_classifier(force=True)
            # If legacy model weights exist locally, fallback succeeds and logs explicit fallback
            if classifier.FALLBACK_MODEL_DIR.exists():
                assert success is True
                assert any("EXPLICIT FALLBACK" in rec.message for rec in caplog.records)
                assert classifier.get_loaded_model_dir() == str(classifier.FALLBACK_MODEL_DIR)
    finally:
        classifier.UPDATED_MODEL_DIR = original_updated_dir
        classifier.reset_classifier()
        classifier.init_classifier(force=True)


def test_app_health_endpoint_returns_classifier_info():
    from app import create_app
    app = create_app("testing")
    with app.test_client() as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["ok"] is True
        assert payload["data"]["status"] == "ok"
        clf = payload["data"]["classifier"]
        assert clf["framework"] == "SetFit"
        assert clf["labels"] == 15
        assert "Updated_Model" in (clf["model_dir"] or "")
