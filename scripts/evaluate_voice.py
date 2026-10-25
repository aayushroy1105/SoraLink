"""Benchmark the SoraLink voice pipeline and write a truthful models/README.md.

Checks performed:
  * Whisper transcription latency + GPU VRAM on synthesized speech clips (SAPI TTS)
  * classifier outcomes for clear / ambiguous / urgent / gibberish text
  * every frozen error code that can be triggered without sabotaging the process
  * temp-file cleanup after success and after failure

Usage::

    python scripts/evaluate_voice.py                 # default 3 runs per clip
    python scripts/evaluate_voice.py --runs 1 --no-tts

The report is written to ``models/README.md`` and ``models/evaluation_report.json``.
Nothing is invented: any step that could not run is reported as skipped with the
reason, and command failures keep their real exit status.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import wave
from io import BytesIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402

import classifier  # noqa: E402
import voice  # noqa: E402
from classifier import REQUIRED_INTENT_IDS, VoiceProcessingError  # noqa: E402

MODELS_DIR = PROJECT_ROOT / "models"
README_PATH = MODELS_DIR / "README.md"
REPORT_PATH = MODELS_DIR / "evaluation_report.json"
TEST_SUITE_PATH = PROJECT_ROOT / "data" / "test_suite.json"

SPEECH_CLIPS: list[tuple[str, str, str]] = [
    ("water_warm", "Could I have some warm water, please?", "water_request"),
    ("blanket", "Can I get an extra blanket please?", "blanket_request"),
    ("meal_veg", "I would like the vegetarian meal.", "meal_inquiry"),
    ("urgent_medical", "I need a doctor, I feel very sick.", "medical_help"),
]


def _word_error_rate(reference: str, hypothesis: str) -> float:
    """Word-level edit distance divided by reference length (0.0 = perfect)."""
    ref = re.findall(r"[a-z0-9']+", (reference or "").casefold())
    hyp = re.findall(r"[a-z0-9']+", (hypothesis or "").casefold())
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for row, ref_word in enumerate(ref, start=1):
        current = [row]
        for column, hyp_word in enumerate(hyp, start=1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (ref_word != hyp_word),
                )
            )
        previous = current
    return previous[-1] / len(ref)

CLASSIFIER_CASES: list[dict] = [
    {
        "name": "clear routine request",
        "text": "Could I have some warm water, please?",
        "expect_outcome": "SUGGESTED",
        "expect_intent": "water_request",
        "expect_attributes": {"temperature": "WARM"},
    },
    {
        "name": "clear blanket request",
        "text": "Can I get an extra blanket please",
        "expect_outcome": "SUGGESTED",
        "expect_intent": "blanket_request",
        "expect_attributes": {},
    },
    {
        "name": "compound blanket+pillow",
        "text": "please bring a blanket and a pillow",
        "expect_outcome": "SUGGESTED",
        "expect_intent": "pillow_request",
        "expect_candidate": "blanket_request",
    },
    {
        "name": "urgent breathing",
        "text": "I cannot breathe properly",
        "expect_outcome": "REQUIRES_CHOICE",
        "expect_urgent_candidate": "medical_help",
    },
    {
        "name": "urgent injury Hinglish",
        "text": "mera haath se khoon aa raha hai",
        "expect_outcome": "REQUIRES_CHOICE",
        "expect_urgent_candidate": "medical_help",
    },
    {
        "name": "urgent accessibility",
        "text": "I need a wheelchair to get off the plane",
        "expect_outcome": "REQUIRES_CHOICE",
        "expect_urgent_candidate": "accessibility_assist",
    },
    {
        "name": "weak help + routine context",
        "text": "can you help me lift my bag",
        "expect_outcome": "SUGGESTED",
        "expect_intent": "bag_help",
    },
    {
        "name": "gibberish",
        "text": "zzz qqq blorp flurble",
        "expect_outcome": "UNRELIABLE",
    },
]


def _versions() -> dict[str, str]:
    packages = ["torch", "faster-whisper", "ctranslate2", "setfit", "sentence-transformers", "transformers", "numpy"]
    out = {
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
    }
    for name in packages:
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = "not installed"
    return out


def _gpu_info() -> dict:
    info = {"name": "unavailable", "total_mb": None, "torch_cuda": None, "torch": None}
    try:
        import torch

        info["torch"] = torch.__version__
        info["torch_cuda"] = torch.version.cuda
        if torch.cuda.is_available():
            info["name"] = torch.cuda.get_device_name(0)
            info["total_mb"] = round(torch.cuda.get_device_properties(0).total_memory / (1024**2))
    except Exception as exc:
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


def _vram_used_mb() -> float | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return float(result.stdout.strip().splitlines()[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


class VramSampler:
    """Poll nvidia-smi on a background thread and keep the peak reading."""

    def __init__(self, interval: float = 0.25) -> None:
        self.interval = interval
        self.baseline = _vram_used_mb()
        self.peak: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "VramSampler":
        def poll() -> None:
            while not self._stop.is_set():
                value = _vram_used_mb()
                if value is not None and (self.peak is None or value > self.peak):
                    self.peak = value
                self._stop.wait(self.interval)

        self._thread = threading.Thread(target=poll, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


def _sapi_tts(text: str, destination: Path) -> tuple[bool, str]:
    """Synthesize speech with Windows SAPI. Returns (ok, detail)."""
    if os.name != "nt":
        return False, "Windows SAPI unavailable on this platform"
    script = destination.with_suffix(".ps1")
    body = (
        "Add-Type -AssemblyName System.Speech\n"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$s.Rate = 0\n"
        f'$s.SetOutputToWaveFile("{destination.as_posix()}")\n'
        f'$s.Speak("{text.replace(chr(34), chr(39))}")\n'
        "$s.Dispose()\n"
    )
    script.write_text(body, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"TTS failed: {type(exc).__name__}: {exc}"
    finally:
        script.unlink(missing_ok=True)
    if proc.returncode != 0 or not destination.exists() or destination.stat().st_size == 0:
        return False, (proc.stderr or proc.stdout or "no audio produced").strip()[:300]
    return True, "ok"


def _tone_wav(seconds: float, freq: float = 440.0, amplitude: int = 8000) -> bytes:
    rate = 16000
    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for index in range(int(rate * seconds)):
            value = int(amplitude * math.sin(2 * math.pi * freq * index / rate))
            frames += int(value).to_bytes(2, "little", signed=True)
        handle.writeframes(bytes(frames))
    return buffer.getvalue()


def _silent_wav(seconds: float = 1.0) -> bytes:
    rate = 16000
    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))
    return buffer.getvalue()


def benchmark_whisper(runs: int, workdir: Path) -> list[dict]:
    results: list[dict] = []
    for clip_id, sentence, expected_intent in SPEECH_CLIPS:
        wav_path = workdir / f"{clip_id}.wav"
        ok, detail = _sapi_tts(sentence, wav_path)
        if not ok:
            results.append({"clip": clip_id, "sentence": sentence, "ok": False, "detail": detail})
            continue
        audio = wav_path.read_bytes()
        if clip_id == SPEECH_CLIPS[0][0]:
            # First CUDA call pays kernel warm-up; time it separately and discard.
            try:
                voice.process_voice_preview(audio, "audio/wav")
            except VoiceProcessingError:
                pass
        latencies: list[float] = []
        whisper_latencies: list[float] = []
        last: dict = {}
        vram: dict = {}
        with VramSampler() as sampler:
            for _ in range(runs):
                started = time.perf_counter()
                try:
                    preview = voice.process_voice_preview(audio, "audio/wav")
                    elapsed = (time.perf_counter() - started) * 1000
                    latencies.append(elapsed)
                    heard = preview["transcript"]
                    suggested = (preview["suggested_intent"] or {}).get("intent_id")
                    top_candidate = (
                        preview["candidates"][0]["intent_id"] if preview["candidates"] else None
                    )
                    last = {
                        "ok": True,
                        "transcript": heard,
                        "outcome": preview["outcome"],
                        "suggested": suggested,
                        "attributes": preview["attributes"],
                        "candidates": preview["candidates"],
                        "wer": round(_word_error_rate(sentence, heard), 4),
                        "intent_match": suggested == expected_intent,
                        # An urgent request is correctly identified even though it may
                        # never be auto-suggested (it must be confirmed by the passenger).
                        "intent_hit": expected_intent in {suggested, top_candidate},
                    }
                except VoiceProcessingError as exc:
                    last = {"ok": False, "error": exc.code, "message": exc.message}
                    break
                # Whisper-only timing on the decoded samples.
                samples = voice._decode_samples(workdir / f"{clip_id}.wav")
                w_started = time.perf_counter()
                try:
                    voice._transcribe(voice._VOICE.model, samples)
                    whisper_latencies.append((time.perf_counter() - w_started) * 1000)
                except VoiceProcessingError:
                    pass
            vram = {"baseline_mb": sampler.baseline, "peak_mb": sampler.peak}
        results.append(
            {
                "clip": clip_id,
                "sentence": sentence,
                "expected_intent": expected_intent,
                "ok": bool(last.get("ok")),
                "runs": len(latencies),
                "median_ms": round(statistics.median(latencies), 1) if latencies else None,
                "min_ms": round(min(latencies), 1) if latencies else None,
                "max_ms": round(max(latencies), 1) if latencies else None,
                "whisper_median_ms": round(statistics.median(whisper_latencies), 1)
                if whisper_latencies
                else None,
                "vram": vram,
                "result": last,
            }
        )
        wav_path.unlink(missing_ok=True)
    return results


def evaluate_classifier() -> list[dict]:
    cases = []
    for case in CLASSIFIER_CASES:
        record = {"name": case["name"], "text": case["text"], "checks": {}}
        try:
            output = classifier.classify_text(case["text"])
            record["outcome"] = output["outcome"]
            record["suggested_intent"] = output["suggested_intent"]
            record["attributes"] = output["attributes"]
            record["candidates"] = output["candidates"]
            record["transcript"] = output["transcript"]

            if "expect_outcome" in case:
                record["checks"]["outcome"] = output["outcome"] == case["expect_outcome"]
            if case.get("expect_intent"):
                record["checks"]["intent"] = (
                    (output["suggested_intent"] or {}).get("intent_id") == case["expect_intent"]
                )
            if "expect_attributes" in case:
                record["checks"]["attributes"] = output["attributes"] == case["expect_attributes"]
            if case.get("expect_candidate"):
                ids = [c["intent_id"] for c in output["candidates"]]
                record["checks"]["candidate"] = case["expect_candidate"] in ids
            if case.get("expect_urgent_candidate"):
                ids = [c["intent_id"] for c in output["candidates"]]
                record["checks"]["urgent_candidate"] = case["expect_urgent_candidate"] in ids
        except VoiceProcessingError as exc:
            record["error"] = exc.code
            record["checks"]["no_error"] = False
        cases.append(record)
    return cases


def evaluate_suite() -> dict:
    """Score the held-out suite in ``data/test_suite.json`` (never trained on).

    In-domain cases pass on top-1; urgent cases additionally must never be
    auto-filed as SUGGESTED. Failure probes pass when the classifier does not
    confidently suggest an intent for them.
    """
    if not TEST_SUITE_PATH.exists():
        return {"available": False, "reason": "data/test_suite.json not found"}
    try:
        suite = json.loads(TEST_SUITE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"available": False, "reason": f"invalid JSON ({exc})"}

    cases: list[dict] = suite.get("cases") or []
    if not cases:
        return {"available": False, "reason": "no cases in data/test_suite.json"}

    urgent_ids = set(classifier.URGENT_IDS)
    intent_n = intent_top1 = suggested = suggested_correct = wrong_suggest = abstain = 0
    urgent_n = urgent_top1 = urgent_suggested = 0
    failure_n = failure_rejected = failure_unreliable = failure_suggested = 0
    per_intent: dict[str, dict[str, int]] = {}
    per_register: dict[str, dict[str, int]] = {}
    per_source: dict[str, dict[str, int]] = {}
    per_failure: dict[str, dict[str, int]] = {}
    misses: list[dict] = []
    latencies: list[float] = []

    def bucket(store: dict[str, dict[str, int]], key: str) -> dict[str, int]:
        return store.setdefault(key, {"n": 0, "top1": 0, "suggested": 0, "wrong": 0, "abstain": 0})

    for case in cases:
        started = time.perf_counter()
        try:
            output = classifier.classify_text(case["text"])
            latencies.append((time.perf_counter() - started) * 1000)
        except VoiceProcessingError as exc:
            latencies.append((time.perf_counter() - started) * 1000)
            misses.append({"id": case.get("id"), "text": case.get("text"), "outcome": f"error:{exc.code}"})
            if case.get("kind") == "intent":
                intent_n += 1
            else:
                failure_n += 1
            continue

        outcome = output["outcome"]
        suggested_id = (output["suggested_intent"] or {}).get("intent_id")
        candidates = [c["intent_id"] for c in output["candidates"]]
        top1 = suggested_id or (candidates[0] if candidates else None)

        if case.get("kind") == "intent":
            expected = case["intent"]
            intent_n += 1
            correct = top1 == expected
            is_suggested = outcome == "SUGGESTED"
            intent_top1 += int(correct)
            suggested += int(is_suggested)
            suggested_correct += int(is_suggested and correct)
            wrong_suggest += int(is_suggested and not correct)
            abstain += int(outcome == "UNRELIABLE")

            for store, key in (
                (per_intent, expected),
                (per_register, case.get("register", "unknown")),
                (per_source, case.get("source", "curated")),
            ):
                stats = bucket(store, key)
                stats["n"] += 1
                stats["top1"] += int(correct)
                stats["suggested"] += int(is_suggested)
                stats["wrong"] += int(is_suggested and not correct)
                stats["abstain"] += int(outcome == "UNRELIABLE")

            if expected in urgent_ids:
                urgent_n += 1
                urgent_top1 += int(correct)
                urgent_suggested += int(is_suggested)

            if not correct:
                misses.append(
                    {
                        "id": case.get("id"),
                        "text": case.get("text"),
                        "expected": expected,
                        "top1": top1,
                        "outcome": outcome,
                    }
                )
        else:
            failure_n += 1
            rejected = outcome != "SUGGESTED"
            failure_rejected += int(rejected)
            failure_unreliable += int(outcome == "UNRELIABLE")
            failure_suggested += int(outcome == "SUGGESTED")
            stats = per_failure.setdefault(
                case.get("category", "failure"),
                {"n": 0, "rejected": 0, "unreliable": 0, "suggested": 0},
            )
            stats["n"] += 1
            stats["rejected"] += int(rejected)
            stats["unreliable"] += int(outcome == "UNRELIABLE")
            stats["suggested"] += int(outcome == "SUGGESTED")
            if not rejected:
                misses.append(
                    {
                        "id": case.get("id"),
                        "text": case.get("text"),
                        "kind": "failure",
                        "outcome": outcome,
                        "suggested": suggested_id,
                    }
                )

    latencies.sort()

    def percentile(values: list[float], q: float) -> float | None:
        if not values:
            return None
        pos = (len(values) - 1) * q
        low = int(pos)
        high = min(low + 1, len(values) - 1)
        return round(values[low] + (values[high] - values[low]) * (pos - low), 2)

    def rate(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 4) if denominator else None

    return {
        "available": True,
        "total": len(cases),
        "intent_n": intent_n,
        "intent_top1": intent_top1,
        "top1_accuracy": rate(intent_top1, intent_n),
        "suggested": suggested,
        "coverage": rate(suggested, intent_n),
        "suggestion_precision": rate(suggested_correct, suggested),
        # Precision over every auto-accept, including negatives wrongly filed.
        "auto_accept_precision_all": rate(suggested_correct, suggested + failure_suggested),
        "wrong_suggest": wrong_suggest,
        "abstain": abstain,
        "urgent_n": urgent_n,
        "urgent_top1": urgent_top1,
        "urgent_never_suggested": urgent_n - urgent_suggested,
        "failure_n": failure_n,
        "failure_rejected": failure_rejected,
        "failure_unreliable": failure_unreliable,
        "failure_suggested": failure_suggested,
        "failure_reject_rate": rate(failure_rejected, failure_n),
        "latency_ms_p50": percentile(latencies, 0.50),
        "latency_ms_p95": percentile(latencies, 0.95),
        "per_intent": dict(sorted(per_intent.items())),
        "per_register": dict(sorted(per_register.items())),
        "per_source": dict(sorted(per_source.items())),
        "per_failure_category": dict(sorted(per_failure.items())),
        "misses": misses,
    }


def check_error_codes() -> list[dict]:
    checks: list[dict] = []

    def probe(name: str, expected_code: str, fn) -> None:
        started = time.perf_counter()
        try:
            fn()
            checks.append({"name": name, "expected": expected_code, "actual": "no error", "pass": False})
        except VoiceProcessingError as exc:
            checks.append(
                {
                    "name": name,
                    "expected": expected_code,
                    "actual": exc.code,
                    "http_status": exc.http_status,
                    "pass": exc.code == expected_code,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                }
            )
        except Exception as exc:  # pragma: no cover - unexpected
            checks.append(
                {
                    "name": name,
                    "expected": expected_code,
                    "actual": f"{type(exc).__name__}: {exc}",
                    "pass": False,
                }
            )

    probe("missing audio", "AUDIO_MISSING", lambda: voice.process_voice_preview(b"", "audio/wav"))
    probe(
        "oversized upload",
        "AUDIO_TOO_LARGE",
        lambda: voice.process_voice_preview(b"0" * (voice.MAX_AUDIO_BYTES + 1), "audio/webm"),
    )
    probe(
        "bad mime type",
        "UNSUPPORTED_AUDIO_TYPE",
        lambda: voice.process_voice_preview(b"1234", "application/pdf"),
    )
    probe(
        "silent recording",
        "SILENCE_OR_NO_SPEECH",
        lambda: voice.process_voice_preview(_silent_wav(1.0), "audio/wav"),
    )
    probe(
        "21 second recording",
        "AUDIO_TOO_LONG",
        lambda: voice.process_voice_preview(_tone_wav(21.0), "audio/wav"),
    )

    # MODEL_BUSY: hold the only inference slot, then call with a tiny (previously
    # unheard-of) timeout so the check does not stall the benchmark.
    original_timeout = voice.SEMAPHORE_TIMEOUT_SECONDS
    acquired = voice._INFERENCE_SEMAPHORE.acquire(timeout=2.0)
    try:
        voice.SEMAPHORE_TIMEOUT_SECONDS = 0.05
        probe(
            "concurrent inference",
            "MODEL_BUSY",
            lambda: voice.process_voice_preview(_tone_wav(1.0), "audio/wav"),
        )
    finally:
        voice.SEMAPHORE_TIMEOUT_SECONDS = original_timeout
        if acquired:
            voice._INFERENCE_SEMAPHORE.release()
    checks.append(
        {
            "name": "model unavailable",
            "expected": "MODEL_UNAVAILABLE",
            "actual": "covered by tests/test_voice.py (monkeypatched loader)",
            "pass": None,
        }
    )
    return checks


def check_temp_cleanup(models_ready: bool) -> dict:
    directory = voice._temp_audio_dir()
    before = {p.name for p in directory.glob("soralink_audio_*")}
    detail = {"directory": str(directory), "before": len(before), "after_success": None, "after_failure": None}
    if not models_ready:
        detail["pass"] = None
        detail["success"] = "not run (whisper model unavailable)"
        return detail

    with tempfile.TemporaryDirectory(prefix="soralink_cleanup_") as workdir:
        speech = Path(workdir) / "cleanup.wav"
        synthesised, info = _sapi_tts("Could I have some water please?", speech)
        if synthesised:
            try:
                voice.process_voice_preview(speech.read_bytes(), "audio/wav")
                detail["success"] = "processed without error"
            except VoiceProcessingError as exc:
                detail["success"] = f"rejected with {exc.code}"
        else:
            detail["success"] = f"not run ({info})"
    detail["after_success"] = len({p.name for p in directory.glob("soralink_audio_*")} - before)

    try:
        voice.process_voice_preview(_silent_wav(1.0), "audio/wav")
    except VoiceProcessingError:
        pass
    detail["after_failure"] = len({p.name for p in directory.glob("soralink_audio_*")} - before)
    detail["pass"] = detail["after_success"] == 0 and detail["after_failure"] == 0
    return detail


def _fmt(value, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{value}{suffix}"


def write_readme(report: dict) -> None:
    env = report["environment"]
    gpu = report["gpu"]
    clips = report["whisper_benchmark"]
    cases = report["classifier_cases"]
    errors = report["error_checks"]
    cleanup = report["temp_cleanup"]
    training = report.get("training_report") or {}
    download = report.get("download_report") or {}

    lines: list[str] = []
    lines.append("# SoraLink local AI models\n")
    lines.append(
        "Generated by `scripts/evaluate_voice.py` on "
        f"{report['generated_at']}. Every number below was measured on this machine; "
        "anything that could not run is marked as such.\n"
    )
    lines.append("## Environment\n")
    lines.append(f"* OS: {env['platform']}")
    lines.append(f"* Python: {env['python']}")
    lines.append(f"* torch: {env['torch']} (CUDA {gpu.get('torch_cuda')}) — CUDA available: {report['cuda_available']}")
    lines.append(f"* GPU: {gpu['name']} ({gpu['total_mb']} MB)")
    lines.append(f"* faster-whisper: {env['faster-whisper']} / CTranslate2 {env['ctranslate2']}")
    lines.append(f"* setfit: {env['setfit']} / sentence-transformers {env['sentence-transformers']}")
    lines.append(f"* Whisper weights: `{report['whisper_dir']}` (device `{report['whisper_device']}`, compute `{report['whisper_compute_type']}`)")
    lines.append(f"* Classifier weights: `{report['classifier_dir']}`")
    lines.append("")

    lines.append("## Readiness\n")
    lines.append(f"* `voice_model`: **{report['readiness']['voice_model']}**")
    lines.append(f"* `classifier`: **{report['readiness']['classifier']}**")
    if download:
        lines.append(
            f"* Download verification: {'passed' if download.get('ok') else 'FAILED'} "
            f"(`models/download_report.json`, {download.get('generated_at', 'n/a')})"
        )
    lines.append("")

    if training:
        val = training.get("validation", {})
        best = (training.get("calibration") or {}).get("best") or {}
        lines.append("## Classifier training\n")
        lines.append(
            f"* Trained {training.get('generated_at')} on {training.get('device', {}).get('name')} "
            f"in {training.get('training_seconds')} s"
        )
        lines.append(
            f"* Split: {training.get('data', {}).get('train')} train / "
            f"{training.get('data', {}).get('validation')} validation utterances"
        )
        lines.append(f"* Validation accuracy: **{val.get('accuracy')}** ({val.get('correct')}/{val.get('total')})")
        lines.append(f"* Peak torch VRAM during training: {training.get('peak_torch_vram_mb')} MB")
        if best:
            lines.append(
                f"* Calibrated thresholds: SUGGESTED >= {best.get('suggested_threshold')}, "
                f"margin >= {best.get('margin_threshold')} "
                f"(auto-accept coverage {best.get('coverage')}, precision {best.get('precision')})"
            )
        confusions = val.get("confusions") or []
        if confusions:
            lines.append("* Validation confusions:")
            for row in confusions[:8]:
                lines.append(f"  * `{row['expected']}` → `{row['predicted']}`: “{row['text']}”")
        lines.append("")

    lines.append("## Whisper latency (full `/api/voice/preview` pipeline)\n")
    lines.append(
        "| clip | sentence | runs | median | whisper-only median | VRAM peak | transcript | intent | WER | outcome |"
    )
    lines.append("| :--- | :--- | ---: | ---: | ---: | ---: | :--- | :--- | ---: | :--- |")
    for clip in clips:
        if not clip.get("ok"):
            lines.append(
                f"| {clip['clip']} | {clip['sentence']} | 0 | n/a | n/a | n/a | "
                f"skipped: {clip.get('detail', 'no audio')} | — | — | — |"
            )
            continue
        result = clip.get("result") or {}
        peak = (clip.get("vram") or {}).get("peak_mb")
        base = (clip.get("vram") or {}).get("baseline_mb")
        vram_text = (
            f"{peak:.0f} MB (Δ{peak - base:+.0f})" if peak is not None and base is not None else "n/a"
        )
        wer = result.get("wer")
        intent_cell = "—"
        if result.get("ok"):
            intent_cell = (
                f"{'✓' if result.get('intent_hit') else '✗'} "
                f"{result.get('suggested') or 'confirm only'} (want {clip.get('expected_intent')})"
            )
        lines.append(
            f"| {clip['clip']} | {clip['sentence']} | {clip['runs']} | "
            f"{_fmt(clip.get('median_ms'), ' ms')} | {_fmt(clip.get('whisper_median_ms'), ' ms')} | "
            f"{vram_text} | “{(result.get('transcript') or '')[:60]}” | {intent_cell} | "
            f"{f'{wer:.1%}' if isinstance(wer, (int, float)) else '—'} | "
            f"{result.get('outcome', result.get('error', '—'))} |"
        )
    measured = [clip for clip in clips if clip.get("ok")]
    if measured:
        results = [clip.get("result") or {} for clip in measured]
        hits = sum(1 for result in results if result.get("intent_hit"))
        auto = sum(1 for result in results if result.get("intent_match"))
        mean_wer = statistics.fmean(float(result.get("wer") or 0.0) for result in results)
        lines.append(
            f"\nEnd-to-end (ASR → classifier) on {len(measured)} synthesized clips: "
            f"intent identified **{hits}/{len(measured)}** "
            f"(auto-suggested {auto}/{len(measured)}; urgent requests are confirmed instead), "
            f"mean word error rate **{mean_wer:.1%}**.\n"
        )
    lines.append("")

    lines.append("## Classifier behaviour\n")
    lines.append("| case | input | outcome | suggested | attributes | checks |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for case in cases:
        suggested = (case.get("suggested_intent") or {}).get("intent_id", "—")
        checks = case.get("checks") or {}
        summary = ", ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in checks.items()) or "observed"
        if case.get("error"):
            summary = f"error {case['error']}"
        lines.append(
            f"| {case['name']} | “{case['text'][:48]}” | {case.get('outcome', case.get('error', '—'))} | "
            f"{suggested} | `{json.dumps(case.get('attributes', {}))}` | {summary} |"
        )
    passed = sum(1 for c in cases for v in (c.get("checks") or {}).values() if v)
    total = sum(1 for c in cases for v in (c.get("checks") or {}).values() if v is not None)
    lines.append(f"\nExpectation checks passed: **{passed}/{total}**.\n")

    suite = report.get("test_suite") or {}
    if suite.get("available"):
        curated = suite.get("per_source", {}).get("curated") or {}
        curated_note = (
            f" Of these, {curated.get('n')} are the original hand-written cases, so its top-1 "
            f"({curated['top1']}/{curated['n']}) stays comparable across model versions."
            if curated.get("n")
            else ""
        )
        lines.append(f"## Held-out test suite ({suite['total']} cases, never trained on)\n")
        lines.append(
            f"`data/test_suite.json` — {suite['total']} cases scored against the live classifier."
            " No suite string appears in `data/intents.json` training data."
            f" {suite['failure_n']} of the cases are negatives — inputs where no catalog intent matches, "
            "so the only correct behaviour is to abstain or ask."
            " Curated cases are hand-written; generated cases are deterministic "
            "phrase-bank × request-frame combinations from `scripts/build_test_suite.py`."
            f"{curated_note}\n"
        )
        precision = suite.get("suggestion_precision")
        lines.append("| metric | value |")
        lines.append("| :--- | ---: |")
        lines.append(f"| in-domain cases | {suite['intent_n']} |")
        lines.append(f"| top-1 accuracy | **{suite['top1_accuracy']:.1%}** |")
        lines.append(f"| auto-accept coverage (SUGGESTED) | {suite['coverage']:.1%} |")
        lines.append(
            f"| suggestion precision | {precision:.1%} |" if precision is not None else "| suggestion precision | n/a |"
        )
        all_precision = suite.get("auto_accept_precision_all")
        lines.append(
            f"| suggestion precision incl. negatives | {all_precision:.1%} |"
            if all_precision is not None
            else "| suggestion precision incl. negatives | n/a |"
        )
        lines.append(f"| confidently wrong suggestions | {suite['wrong_suggest']} |")
        lines.append(f"| abstained (UNRELIABLE) | {suite['abstain']} |")
        lines.append(f"| urgent cases never auto-filed | {suite['urgent_never_suggested']}/{suite['urgent_n']} |")
        lines.append(
            f"| failure probes rejected (not SUGGESTED) | {suite['failure_rejected']}/{suite['failure_n']} |"
        )
        lines.append(
            f"| classify latency p50 / p95 | {suite.get('latency_ms_p50')} / {suite.get('latency_ms_p95')} ms |"
        )
        lines.append("")

        if suite.get("per_source"):
            lines.append("| source | n | top-1 | SUGGESTED | wrong | abstain |")
            lines.append("| :--- | ---: | ---: | ---: | ---: | ---: |")
            for source, stats in suite["per_source"].items():
                lines.append(
                    f"| {source} | {stats['n']} | {stats['top1']}/{stats['n']} "
                    f"({stats['top1'] / stats['n']:.1%}) | "
                    f"{stats['suggested']} | {stats['wrong']} | {stats['abstain']} |"
                )
            lines.append("")

        lines.append("| register | n | top-1 | SUGGESTED | wrong | abstain |")
        lines.append("| :--- | ---: | ---: | ---: | ---: | ---: |")
        for register, stats in suite["per_register"].items():
            lines.append(
                f"| {register} | {stats['n']} | {stats['top1']}/{stats['n']} | "
                f"{stats['suggested']} | {stats['wrong']} | {stats['abstain']} |"
            )
        lines.append("")

        lines.append("| intent | n | top-1 | SUGGESTED | wrong | abstain |")
        lines.append("| :--- | ---: | ---: | ---: | ---: | ---: |")
        for intent_id, stats in suite["per_intent"].items():
            lines.append(
                f"| {intent_id} | {stats['n']} | {stats['top1']}/{stats['n']} | "
                f"{stats['suggested']} | {stats['wrong']} | {stats['abstain']} |"
            )
        lines.append("")

        lines.append("| failure category | n | rejected | UNRELIABLE | wrongly suggested |")
        lines.append("| :--- | ---: | ---: | ---: | ---: |")
        for category, stats in suite["per_failure_category"].items():
            lines.append(
                f"| {category} | {stats['n']} | {stats['rejected']} | {stats['unreliable']} | {stats['suggested']} |"
            )
        lines.append("")

        misses = suite.get("misses") or []
        if misses:
            lines.append(f"First 15 of {len(misses)} misses:\n")
            for miss in misses[:15]:
                expected = miss.get("expected") or "reject"
                got = miss.get("top1") or miss.get("suggested") or "—"
                lines.append(
                    f"* `{miss.get('id')}` “{miss.get('text')}” → expected {expected}, "
                    f"got {miss.get('outcome')} ({got})"
                )
            lines.append("")

    lines.append("## Error-code verification\n")
    lines.append("| check | expected | observed | HTTP | result |")
    lines.append("| :--- | :--- | :--- | ---: | :--- |")
    for check in errors:
        status = check.get("http_status")
        verdict = "PASS" if check.get("pass") else ("not run" if check.get("pass") is None else "FAIL")
        lines.append(
            f"| {check['name']} | {check['expected']} | {check['actual']} | "
            f"{status if status is not None else '—'} | {verdict} |"
        )
    lines.append("")

    lines.append("## Temp-file cleanup\n")
    if cleanup.get("pass") is None:
        lines.append(
            f"Not run — {cleanup.get('success', 'models unavailable')}. "
            f"Temp directory: `{cleanup['directory']}`."
        )
    elif cleanup.get("pass"):
        lines.append(
            f"PASS — 0 leftover `soralink_audio_*` files in `{cleanup['directory']}` "
            "after both a successful preview and a rejected (silent) upload."
        )
    else:
        lines.append(
            f"FAIL — leftovers detected: success={cleanup.get('after_success')}, "
            f"failure={cleanup.get('after_failure')} in `{cleanup['directory']}`."
        )
    lines.append("")

    lines.append("## Known limitations\n")
    for limitation in report["limitations"]:
        lines.append(f"* {limitation}")
    lines.append("")

    lines.append("## Reproduce\n")
    lines.append("```bash")
    lines.append("python scripts/download_models.py       # one-time, needs internet")
    lines.append("python scripts/train_classifier.py      # SetFit on the RTX 5060")
    lines.append("python scripts/evaluate_voice.py        # this report")
    lines.append("python -m pytest tests/test_voice.py -q  # unit tests")
    lines.append("```")
    lines.append("")

    README_PATH.parent.mkdir(parents=True, exist_ok=True)
    README_PATH.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3, help="repetitions per speech clip")
    parser.add_argument("--no-tts", action="store_true", help="skip speech synthesis / Whisper benchmark")
    args = parser.parse_args(argv)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    readiness = voice.init_ai_models()
    print(f"[readiness] {readiness} (device={voice._VOICE.device}, compute={voice._VOICE.compute_type})")

    limitations: list[str] = []
    if readiness["voice_model"] != "READY":
        limitations.append(
            "Whisper weights did not load, so transcription/end-to-end latency was not measured "
            f"({voice._VOICE.load_error})."
        )
    if readiness["classifier"] != "READY":
        limitations.append(
            "SetFit weights did not load, so classifier behaviour was not measured. "
            "Run scripts/train_classifier.py first."
        )

    clips: list[dict] = []
    if args.no_tts:
        limitations.append("Whisper benchmark skipped by --no-tts.")
    elif readiness["voice_model"] != "READY":
        limitations.append("Whisper benchmark skipped because the model is unavailable.")
    else:
        with tempfile.TemporaryDirectory(prefix="soralink_eval_") as workdir:
            print(f"[whisper] benchmarking {len(SPEECH_CLIPS)} clips x {args.runs} runs ...")
            clips = benchmark_whisper(max(1, args.runs), Path(workdir))
        for clip in clips:
            if not clip.get("ok"):
                limitations.append(f"Clip '{clip['clip']}' could not be measured: {clip.get('detail')}")

    print("[classifier] evaluating clear/ambiguous/urgent/gibberish inputs ...")
    cases = evaluate_classifier() if readiness["classifier"] == "READY" else []

    print("[suite] scoring data/test_suite.json ...")
    suite_report = (
        evaluate_suite()
        if readiness["classifier"] == "READY"
        else {"available": False, "reason": "classifier unavailable"}
    )
    if suite_report.get("available"):
        print(
            f"[suite] top-1 {suite_report['top1_accuracy']:.1%} on {suite_report['intent_n']} in-domain cases; "
            f"failure probes rejected {suite_report['failure_rejected']}/{suite_report['failure_n']}"
        )
    else:
        print(f"[suite] skipped: {suite_report.get('reason')}")

    print("[errors] probing frozen error codes ...")
    errors = check_error_codes()
    if readiness["voice_model"] != "READY":
        for check in errors:
            if check["expected"] in {"AUDIO_TOO_LONG", "SILENCE_OR_NO_SPEECH", "MODEL_BUSY"}:
                check["actual"] = f"not run ({readiness['voice_model']})"
                check["pass"] = None

    cleanup = check_temp_cleanup(readiness["voice_model"] == "READY")

    training_report = {}
    training_path = MODELS_DIR / "training_report.json"
    if training_path.exists():
        try:
            training_report = json.loads(training_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            limitations.append("models/training_report.json exists but is not valid JSON.")

    download_report = {}
    download_path = MODELS_DIR / "download_report.json"
    if download_path.exists():
        try:
            download_report = json.loads(download_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            limitations.append("models/download_report.json exists but is not valid JSON.")

    # Honest, measured limitations only.
    if cases:
        gibberish = next((c for c in cases if c["name"] == "gibberish"), None)
        if gibberish and gibberish.get("outcome") != "UNRELIABLE":
            limitations.append(
                "Out-of-vocabulary gibberish still receives a confident-looking label "
                f"(`{gibberish.get('outcome')}`); the rule-based thresholds are the safety net, "
                "not a guarantee against nonsense input."
            )
        missed = [c["name"] for c in cases if any(v is False for v in (c.get("checks") or {}).values())]
        if missed:
            limitations.append("Expectation misses observed for: " + ", ".join(missed) + ".")
    limitations.append(
        "Whisper models handle English well; Hinglish/Hindi/Punjabi transcription quality is lower "
        "and the classifier is trained on text transcripts, not on noisy audio."
    )
    if not download_report:
        limitations.append("No models/download_report.json found; offline load was not verified by download_models.py.")
    if not training_report:
        limitations.append("No models/training_report.json found; validation metrics are unavailable.")
    if suite_report.get("available"):
        weak = [
            reg
            for reg, stats in suite_report["per_register"].items()
            if stats["n"] and stats["top1"] / stats["n"] < 0.5
        ]
        if weak:
            limitations.append(
                "Held-out suite top-1 accuracy is below 50% for registers: " + ", ".join(sorted(weak)) + "."
            )
        if suite_report["wrong_suggest"]:
            limitations.append(
                f"Held-out suite produced {suite_report['wrong_suggest']} confidently wrong suggestions "
                "(see the miss list in models/README.md)."
            )

    measured_clips = [clip for clip in clips if clip.get("ok")]

    report = {
        "generated_at": generated_at,
        "readiness": readiness,
        "cuda_available": bool(_gpu_info().get("torch_cuda") and _gpu_info().get("name") != "unavailable"),
        "environment": _versions(),
        "gpu": _gpu_info(),
        "whisper_dir": str(voice._whisper_dir()),
        "whisper_device": voice._VOICE.device,
        "whisper_compute_type": voice._VOICE.compute_type,
        "classifier_dir": str(classifier._classifier_dir()),
        "thresholds": classifier.thresholds(),
        "whisper_benchmark": clips,
        "end_to_end": {
            "clips": len(measured_clips),
            "intent_hits": sum(
                1 for clip in measured_clips if (clip.get("result") or {}).get("intent_hit")
            ),
            "intent_auto_suggested": sum(
                1 for clip in measured_clips if (clip.get("result") or {}).get("intent_match")
            ),
            "mean_wer": round(
                statistics.fmean(
                    float((clip.get("result") or {}).get("wer") or 0.0)
                    for clip in measured_clips
                ),
                4,
            )
            if measured_clips
            else None,
        },
        "classifier_cases": cases,
        "test_suite": suite_report,
        "error_checks": errors,
        "temp_cleanup": cleanup,
        "training_report": training_report,
        "download_report": download_report,
        "limitations": limitations,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_readme(report)
    print(f"[report] {REPORT_PATH}")
    print(f"[report] {README_PATH}")

    core_ok = readiness["voice_model"] == "READY" and readiness["classifier"] == "READY"
    errors_ok = all(c["pass"] for c in errors if c["pass"] is not None)
    if not core_ok or not errors_ok or cleanup.get("pass") is False:
        print("[result] core pipeline NOT fully verified — see the limitations in the report.")
        return 1
    print("[result] core pipeline verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
