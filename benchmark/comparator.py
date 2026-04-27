"""Compare answers before / after optimization using GigaChat + local metrics."""

from __future__ import annotations

from typing import List, TYPE_CHECKING

from gigachat.client import benchmark_models

from .local_metrics import compute_metrics

if TYPE_CHECKING:
    from models.model_registry import ModelConfig


async def compare_models(
    questions: List[str],
    answers_before: List[str],
    answers_after: List[str],
    model_config: "ModelConfig",
) -> dict:
    report = await benchmark_models(
        questions, answers_before, answers_after, model_config
    )
    metrics_before = compute_metrics(
        answers_before, answers_after, model_config.output_type
    )
    metrics_after = compute_metrics(
        answers_after, answers_after, model_config.output_type
    )
    return {
        "gigachat_report": report,
        "local_metrics": {
            "before_vs_after_agreement": metrics_before,
            "after_self_consistency": metrics_after,
        },
    }
