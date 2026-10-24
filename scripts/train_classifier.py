"""Train + calibrate the SoraLink SetFit intent classifier on the local GPU.

Run after ``scripts/download_models.py``::

    python scripts/train_classifier.py

Writes:
  * ``models/setfit_intent_classifier/`` — SetFit weights (+ label manifest)
  * ``models/training_report.json``       — metrics, thresholds, timings
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# The catalog and validation transcripts contain Devanagari/Gurmukhi; a default
# Windows cp1252 console would crash while printing them.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:  # pragma: no cover - non-standard streams
    pass

from classifier import REQUIRED_INTENT_IDS, load_intent_contract, probability_labels  # noqa: E402

MODELS_DIR = PROJECT_ROOT / "models"
DEFAULT_EMBEDDING_DIR = MODELS_DIR / "embeddings" / "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_OUTPUT_DIR = MODELS_DIR / "setfit_intent_classifier"


def build_split(
    contract: dict,
    val_ratio: float = 0.15,
    seed: int = 42,
) -> tuple[list[str], list[str], list[str], list[str], dict[str, int]]:
    """Stratified per-intent split. Validation keeps 2-4 utterances per intent."""
    rng = random.Random(seed)
    train_texts: list[str] = []
    train_labels: list[str] = []
    val_texts: list[str] = []
    val_labels: list[str] = []
    val_counts: dict[str, int] = {}

    for intent in contract["intents"]:
        intent_id = intent["intent_id"]
        examples = list(
            dict.fromkeys(str(e).strip() for e in intent["training_examples"] if str(e).strip())
        )
        rng.shuffle(examples)
        n_val = max(2, min(4, int(round(len(examples) * val_ratio))))
        val_part, train_part = examples[:n_val], examples[n_val:]
        val_texts.extend(val_part)
        val_labels.extend([intent_id] * len(val_part))
        train_texts.extend(train_part)
        train_labels.extend([intent_id] * len(train_part))
        val_counts[intent_id] = len(val_part)

    return train_texts, train_labels, val_texts, val_labels, val_counts


def _device_report() -> dict:
    info = {"device": "cpu", "name": "CPU", "total_vram_gb": None, "torch": None, "cuda": None}
    try:
        import torch

        info["torch"] = torch.__version__
        info["cuda"] = torch.version.cuda
        if torch.cuda.is_available():
            info["device"] = "cuda"
            info["name"] = torch.cuda.get_device_name(0)
            info["total_vram_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / (1024**3), 2
            )
    except Exception as exc:  # pragma: no cover
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


def _probabilities(model, texts: list[str]) -> list[list[float]]:
    raw = model.predict_proba(texts)
    if hasattr(raw, "detach"):
        raw = raw.detach().cpu().numpy()
    return [[float(v) for v in row] for row in raw]


def evaluate(model, texts: list[str], labels: list[str], class_labels: list[str]) -> dict:
    probs = _probabilities(model, texts)
    predictions = [class_labels[max(range(len(row)), key=row.__getitem__)] for row in probs]
    correct = sum(1 for p, y in zip(predictions, labels) if p == y)
    per_intent: dict[str, dict[str, float | int]] = {}
    for intent_id in class_labels:
        idx = [i for i, y in enumerate(labels) if y == intent_id]
        if not idx:
            continue
        hits = sum(1 for i in idx if predictions[i] == intent_id)
        per_intent[intent_id] = {"support": len(idx), "recall": round(hits / len(idx), 3)}
    confusions = [
        {"expected": y, "predicted": p, "text": t}
        for t, y, p in zip(texts, labels, predictions)
        if p != y
    ]
    return {
        "accuracy": round(correct / len(labels), 4) if labels else 0.0,
        "correct": correct,
        "total": len(labels),
        "per_intent": per_intent,
        "confusions": confusions,
        "probabilities": probs,
        "predictions": predictions,
    }


def calibrate(
    probs: list[list[float]],
    labels: list[str],
    class_labels: list[str],
) -> dict:
    """Grid-search SUGGESTED/MARGIN thresholds: maximise auto-accept coverage
    subject to >= 95% precision among auto-accepted utterances."""
    scored: list[tuple[float, float, bool, bool]] = []
    for row, expected in zip(probs, labels):
        order = sorted(range(len(row)), key=row.__getitem__, reverse=True)
        top1, top2 = row[order[0]], row[order[1]]
        predicted = class_labels[order[0]]
        scored.append((top1, top1 - top2, predicted == expected, predicted in REQUIRED_INTENT_IDS[:4]))

    grid = []
    for suggested in [round(0.50 + 0.05 * i, 2) for i in range(9)]:
        for margin in [round(0.05 + 0.05 * i, 2) for i in range(6)]:
            accepted = [s for s in scored if s[0] >= suggested and s[1] >= margin and not s[3]]
            if not accepted:
                continue
            precision = sum(1 for s in accepted if s[2]) / len(accepted)
            coverage = len(accepted) / len(scored)
            grid.append(
                {
                    "suggested_threshold": suggested,
                    "margin_threshold": margin,
                    "coverage": round(coverage, 3),
                    "precision": round(precision, 3),
                    "auto_accept_f1": round(
                        2 * precision * coverage / (precision + coverage), 3
                    )
                    if precision + coverage
                    else 0.0,
                }
            )

    eligible = [g for g in grid if g["precision"] >= 0.95]
    best = max(eligible, key=lambda g: g["coverage"]) if eligible else (
        max(grid, key=lambda g: g["auto_accept_f1"]) if grid else None
    )
    return {"best": best, "grid": grid}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-model", default=str(DEFAULT_EMBEDDING_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args(argv)

    embedding_dir = Path(args.embedding_model)
    output_dir = Path(args.output_dir)
    if not (embedding_dir / "config.json").exists():
        print(
            f"Embedding model missing at {embedding_dir}. "
            "Run scripts/download_models.py first.",
            file=sys.stderr,
        )
        return 2

    contract = load_intent_contract()
    train_texts, train_labels, val_texts, val_labels, val_counts = build_split(
        contract, args.val_ratio, args.seed
    )
    print(
        f"[data] train={len(train_texts)} val={len(val_texts)} "
        f"intents={len(contract['intents'])} ({min(val_counts.values())}-{max(val_counts.values())} val/class)"
    )

    device = _device_report()
    print(f"[device] {device['device']} — {device['name']} (torch {device['torch']}, CUDA {device['cuda']})")

    import torch
    from datasets import Dataset
    from setfit import SetFitModel, Trainer, TrainingArguments

    torch.manual_seed(args.seed)
    random.seed(args.seed)

    started = time.perf_counter()
    model = SetFitModel.from_pretrained(str(embedding_dir), labels=list(REQUIRED_INTENT_IDS))
    print(f"[model] loaded sentence encoder in {time.perf_counter() - started:.1f}s")

    train_dataset = Dataset.from_dict({"text": train_texts, "label": train_labels})
    training_args = TrainingArguments(
        batch_size=args.batch_size,
        num_epochs=args.epochs,
        num_iterations=args.iterations,
        seed=args.seed,
        # SetFit's Trainer writes ~1.4 GB of intermediate checkpoints to ./checkpoints
        # by default. We keep the final model only.
        output_dir=str(output_dir / ".trainer"),
        save_strategy="no",
        report_to=[],
        show_progress_bar=True,
    )

    trainer = Trainer(model=model, args=training_args, train_dataset=train_dataset)
    train_started = time.perf_counter()
    trainer.train()
    train_seconds = time.perf_counter() - train_started
    vram_peak = (
        round(torch.cuda.max_memory_allocated() / (1024**2), 1) if device["device"] == "cuda" else None
    )
    print(f"[train] finished in {train_seconds:.1f}s (peak torch VRAM {vram_peak} MB)")

    # Probability columns follow the head's class order (alphabetical for the
    # sklearn head), not model.labels. Using model.labels here silently mislabels
    # every validation prediction.
    class_labels = probability_labels(model)
    if sorted(class_labels) != sorted(REQUIRED_INTENT_IDS):
        print(f"[error] model labels do not match the frozen vocabulary: {class_labels}", file=sys.stderr)
        return 3

    results = evaluate(model, val_texts, val_labels, class_labels)
    calibration = calibrate(results["probabilities"], val_labels, class_labels)
    print(f"[eval] validation accuracy {results['accuracy']:.3f} ({results['correct']}/{results['total']})")
    if results["confusions"]:
        print("[eval] confusions:")
        for row in results["confusions"][:10]:
            print(f"    {row['expected']} -> {row['predicted']}: {row['text']}")
    if calibration["best"]:
        best = calibration["best"]
        print(
            f"[calibrate] suggested>={best['suggested_threshold']} margin>={best['margin_threshold']} "
            f"(coverage {best['coverage']:.2f}, precision {best['precision']:.2f})"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir))
    manifest = {
        "probability_column_order": class_labels,
        "frozen_intent_ids": list(REQUIRED_INTENT_IDS),
        "embedding_model": str(embedding_dir),
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "validation_accuracy": results["accuracy"],
        "recommended_thresholds": calibration["best"],
    }
    (output_dir / "intent_labels.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    report = {
        "generated_at": manifest["trained_at"],
        "device": device,
        "params": {
            "batch_size": args.batch_size,
            "num_epochs": args.epochs,
            "num_iterations": args.iterations,
            "seed": args.seed,
            "val_ratio": args.val_ratio,
        },
        "data": {
            "train": len(train_texts),
            "validation": len(val_texts),
            "val_per_intent": val_counts,
        },
        "training_seconds": round(train_seconds, 2),
        "peak_torch_vram_mb": vram_peak,
        "validation": {
            "accuracy": results["accuracy"],
            "correct": results["correct"],
            "total": results["total"],
            "per_intent": results["per_intent"],
            "confusions": results["confusions"],
        },
        "calibration": {"best": calibration["best"], "grid_size": len(calibration["grid"])},
    }
    report_path = MODELS_DIR / "training_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[save] model -> {output_dir}")
    print(f"[save] report -> {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
