"""Mock GigaChat client.

Replace this file with the real implementation when wiring against the
actual GigaChat API. The signature must stay identical.
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import Optional


_YAML_TEMPLATE = """name: {name}
type: monolithic
modalities:
  - image
  - text
input_format: "<image> {{question}}"
output_type: free_text
min_examples_for_soft_prompt: 30
recommended_annotation_style: qa_pairs
soft_prompt_guide: |
  Use short, factual question-answer pairs. Reference visible objects.
coop_supported: true
coop_default_num_vectors: 16
coop_context_init: "a photo of a"
class_token_position: end
coop_net_depth: 3
"""


def _looks_like(needle: str, haystack: str) -> bool:
    return needle.lower() in (haystack or "").lower()


async def gigachat_request(
    prompt: str,
    system_prompt: str,
    timeout: float = 30.0,
) -> str:
    """Pretend to call GigaChat. Returns deterministic-ish fake responses
    based on the system prompt content so the rest of the system can be
    exercised end-to-end without network access.
    """
    await asyncio.sleep(0.1)

    sp = system_prompt or ""

    if _looks_like("сгенерируй yaml", sp) or _looks_like("model config", sp) or _looks_like("конфиг модели", sp):
        name = (prompt or "auto-model").strip().split()[0][:40] or "auto-model"
        return _YAML_TEMPLATE.format(name=name)

    if _looks_like("проверь промпт", sp) or _looks_like("check prompt", sp):
        return json.dumps(
            {
                "valid": True,
                "message": "Промпт выглядит корректно (мок-ответ).",
                "suggestions": [
                    "Можно уточнить контекст вопроса",
                    "Старайтесь давать конкретные ответы",
                ],
            },
            ensure_ascii=False,
        )

    if _looks_like("улучши вопрос", sp) or _looks_like("improve prompt", sp):
        return json.dumps(
            {"improved_question": f"{prompt.strip()} (уточните детали и контекст)"},
            ensure_ascii=False,
        )

    if _looks_like("benchmark", sp) or _looks_like("сравнение моделей", sp):
        return (
            "Мок-отчёт GigaChat:\n"
            "- Модель после оптимизации даёт более точные и краткие ответы.\n"
            "- Замечено снижение количества галлюцинаций на ~15%.\n"
            "- Рекомендуется добавить ещё 20 примеров для устойчивости."
        )

    if _looks_like("оцени минимально", sp) or _looks_like("estimate min", sp):
        return json.dumps({"min_examples": random.choice([20, 30, 50])})

    return "OK"
