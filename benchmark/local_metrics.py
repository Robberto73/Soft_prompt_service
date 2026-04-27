"""Local accuracy / F1 metrics. No external ML libraries."""

from __future__ import annotations

from typing import List


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def accuracy(predictions: List[str], targets: List[str]) -> float:
    n = min(len(predictions), len(targets))
    if n == 0:
        return 0.0
    correct = sum(1 for i in range(n) if _normalize(predictions[i]) == _normalize(targets[i]))
    return correct / n


def macro_f1(predictions: List[str], targets: List[str]) -> float:
    n = min(len(predictions), len(targets))
    if n == 0:
        return 0.0
    classes = sorted({_normalize(targets[i]) for i in range(n)})
    f1_sum = 0.0
    for c in classes:
        tp = sum(
            1 for i in range(n)
            if _normalize(predictions[i]) == c and _normalize(targets[i]) == c
        )
        fp = sum(
            1 for i in range(n)
            if _normalize(predictions[i]) == c and _normalize(targets[i]) != c
        )
        fn = sum(
            1 for i in range(n)
            if _normalize(predictions[i]) != c and _normalize(targets[i]) == c
        )
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)
        f1_sum += f1
    return f1_sum / max(len(classes), 1)


def compute_metrics(
    predictions: List[str], targets: List[str], output_type: str
) -> dict:
    out = {"accuracy": accuracy(predictions, targets)}
    if (output_type or "").lower() == "classification":
        out["f1_score"] = macro_f1(predictions, targets)
    return out
