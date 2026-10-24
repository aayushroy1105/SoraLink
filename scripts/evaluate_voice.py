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

SPEECH_CLIPS: list[tuple[str, str]] = [
    ("water_warm", "Could I have some warm water, please?"),
    ("blanket", "Can I get an extra blanket please?"),
    ("meal_veg", "I would like the vegetarian meal."),
    ("urgent_medical", "I need a doctor, I feel very sick."),
]

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
    for clip_id, sentence in SPEECH_CLIPS:
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
                    last = {
                        "ok": True,
                        "transcript": preview["transcript"],
                        "outcome": preview["outcome"],
                        "suggested": (preview["suggested_intent"] or {}).get("intent_id"),
                        "attributes": preview["attributes"],
                        "candidates": preview["candidates"],
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
    lines.append("| clip | sentence | runs | median | whisper-only median | VRAM peak | transcript | outcome |")
    lines.append("| :--- | :--- | ---: | ---: | ---: | ---: | :--- | :--- |")
    for clip in clips:
        if not clip.get("ok"):
            lines.append(
                f"| {clip['clip']} | {clip['sentence']} | 0 | n/a | n/a | n/a | "
                f"skipped: {clip.get('detail', 'no audio')} | — |"
            )
            continue
        result = clip.get("result") or {}
        peak = (clip.get("vram") or {}).get("peak_mb")
        base = (clip.get("vram") or {}).get("baseline_mb")
        vram_text = (
            f"{peak:.0f} MB (Δ{peak - base:+.0f})" if peak is not None and base is not None else "n/a"
        )
        lines.append(
            f"| {clip['clip']} | {clip['sentence']} | {clip['runs']} | "
            f"{_fmt(clip.get('median_ms'), ' ms')} | {_fmt(clip.get('whisper_median_ms'), ' ms')} | "
            f"{vram_text} | “{(result.get('transcript') or '')[:60]}” | {result.get('outcome', result.get('error', '—'))} |"
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
        "classifier_cases": cases,
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
