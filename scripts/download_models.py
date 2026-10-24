"""Download and verify the local SoraLink AI weights (run once, internet required).

This script is the only place in the project allowed to reach the network on the
AI side.  After it finishes, ``classifier.py`` and ``voice.py`` load everything
from ``./models`` with ``local_files_only=True`` and work fully offline.

Usage::

    python scripts/download_models.py                     # whisper-small + embeddings
    python scripts/download_models.py --whisper-model medium
    python scripts/download_models.py --verify-only       # offline sanity check
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "models"
WHISPER_DIR = MODELS_DIR / "whisper"
EMBEDDINGS_DIR = MODELS_DIR / "embeddings" / "paraphrase-multilingual-MiniLM-L12-v2"

EMBEDDING_REPO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
WHISPER_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}

# Files required inside a faster-whisper CTranslate2 model directory.
WHISPER_REQUIRED_FILES = ("model.bin", "config.json", "tokenizer.json")


def _device_and_compute() -> tuple[str, str]:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda", "int8_float16"
    except Exception:
        pass
    return "cpu", "int8"


def _dir_size_mb(path: Path) -> float:
    total = 0
    if not path.exists():
        return 0.0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return round(total / (1024 * 1024), 1)


def download_whisper(model_size: str) -> None:
    """Snapshot a faster-whisper model into ./models/whisper."""
    from huggingface_hub import snapshot_download

    repo_id = WHISPER_REPOS.get(model_size)
    if repo_id is None:
        raise SystemExit(
            f"Unknown whisper model '{model_size}'. Choose one of: {', '.join(WHISPER_REPOS)}"
        )

    WHISPER_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[whisper] downloading {repo_id} -> {WHISPER_DIR}")
    started = time.perf_counter()
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(WHISPER_DIR),
        allow_patterns=[
            "config.json",
            "model.bin",
            "tokenizer.json",
            "vocabulary.*",
            "preprocessor_config.json",
        ],
    )
    print(f"[whisper] done in {time.perf_counter() - started:.1f}s ({_dir_size_mb(WHISPER_DIR)} MB)")


def download_embeddings() -> None:
    """Snapshot the multilingual MiniLM sentence encoder into ./models/embeddings."""
    from huggingface_hub import snapshot_download

    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[embeddings] downloading {EMBEDDING_REPO} -> {EMBEDDINGS_DIR}")
    started = time.perf_counter()
    snapshot_download(
        repo_id=EMBEDDING_REPO,
        local_dir=str(EMBEDDINGS_DIR),
        ignore_patterns=["*.h5", "*.ot", "*.msgpack", "*.onnx", "onnx/*", "openvino/*"],
    )
    print(
        f"[embeddings] done in {time.perf_counter() - started:.1f}s "
        f"({_dir_size_mb(EMBEDDINGS_DIR)} MB)"
    )


def verify_whisper(load_model: bool = True) -> dict:
    """Verify the cached Whisper directory loads with local_files_only=True."""
    result = {"component": "whisper", "path_ok": False, "load_ok": False, "detail": ""}
    missing = [f for f in WHISPER_REQUIRED_FILES if not (WHISPER_DIR / f).exists()]
    if not WHISPER_DIR.exists() or missing:
        result["detail"] = f"missing files: {missing or 'whole directory'}"
        return result
    result["path_ok"] = True
    if not load_model:
        result["detail"] = "files present (load skipped)"
        return result

    device, compute_type = _device_and_compute()
    try:
        from faster_whisper import WhisperModel

        started = time.perf_counter()
        model = WhisperModel(
            str(WHISPER_DIR),
            device=device,
            compute_type=compute_type,
            local_files_only=True,
        )
        # Touch the model so a broken CTranslate2 engine fails here, not in prod.
        import numpy as np

        list(model.transcribe(np.zeros(8000, dtype=np.float32), vad_filter=False)[0])
        result["load_ok"] = True
        result["detail"] = f"loaded on {device}/{compute_type} in {time.perf_counter() - started:.1f}s"
        del model
    except Exception as exc:  # pragma: no cover - environment dependent
        result["detail"] = f"{type(exc).__name__}: {exc}"
    return result


def verify_embeddings(load_model: bool = True) -> dict:
    result = {"component": "embeddings", "path_ok": False, "load_ok": False, "detail": ""}
    if not (EMBEDDINGS_DIR / "config.json").exists():
        result["detail"] = "missing config.json in embeddings directory"
        return result
    result["path_ok"] = True
    if not load_model:
        result["detail"] = "files present (load skipped)"
        return result
    try:
        from sentence_transformers import SentenceTransformer

        started = time.perf_counter()
        model = SentenceTransformer(str(EMBEDDINGS_DIR), local_files_only=True)
        dim_fn = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
        dim = dim_fn()
        result["load_ok"] = True
        result["detail"] = (
            f"loaded in {time.perf_counter() - started:.1f}s, embedding dim {dim}"
        )
        del model
    except Exception as exc:  # pragma: no cover - environment dependent
        result["detail"] = f"{type(exc).__name__}: {exc}"
    return result


def verify_setfit(load_model: bool = True) -> dict:
    result = {"component": "setfit", "path_ok": False, "load_ok": False, "detail": ""}
    path = MODELS_DIR / "setfit_intent_classifier"
    if not path.exists():
        result["detail"] = "not trained yet (run scripts/train_classifier.py)"
        return result
    result["path_ok"] = True
    if not load_model:
        result["detail"] = "files present (load skipped)"
        return result
    try:
        from setfit import SetFitModel

        model = SetFitModel.from_pretrained(str(path))
        labels = list(model.labels)
        result["load_ok"] = len(labels) == 15
        result["detail"] = f"{len(labels)} labels"
        del model
    except Exception as exc:  # pragma: no cover
        result["detail"] = f"{type(exc).__name__}: {exc}"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--whisper-model",
        default=os.environ.get("SORALINK_WHISPER_MODEL", "small"),
        choices=sorted(WHISPER_REPOS),
        help="faster-whisper size to cache (default: env SORALINK_WHISPER_MODEL or 'small')",
    )
    parser.add_argument("--skip-whisper", action="store_true")
    parser.add_argument("--skip-embeddings", action="store_true")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="do not download; only verify what is already on disk",
    )
    parser.add_argument(
        "--no-load",
        action="store_true",
        help="verify file presence only, do not instantiate models",
    )
    args = parser.parse_args(argv)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    if not args.verify_only:
        try:
            if not args.skip_whisper:
                download_whisper(args.whisper_model)
            if not args.skip_embeddings:
                download_embeddings()
        except Exception as exc:  # pragma: no cover - network dependent
            traceback.print_exc()
            print(f"\n[download] FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            print(
                "[download] If you are offline, copy ./models from a machine that has it "
                "and re-run with --verify-only.",
                file=sys.stderr,
            )
            return 1

    print("\n[verify] checking offline load with local_files_only=True ...")
    checks = [
        verify_whisper(load_model=not args.no_load),
        verify_embeddings(load_model=not args.no_load),
        verify_setfit(load_model=not args.no_load),
    ]
    for check in checks:
        mark = "OK  " if check["load_ok"] else ("MISS" if not check["path_ok"] else "FAIL")
        print(f"  [{mark}] {check['component']}: {check['detail']}")
        # SetFit is trained later, so it is reported but not a download failure.
        if check["component"] != "setfit" and not check["load_ok"]:
            failures.append(check["component"])

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "whisper_model": args.whisper_model,
        "models_dir": str(MODELS_DIR),
        "checks": checks,
        "ok": not failures,
    }
    report_path = MODELS_DIR / "download_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\n[verify] report written to {report_path}")

    if failures:
        print(f"\n[verify] FAILED components: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("\n[verify] all required local weights are ready for offline use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
