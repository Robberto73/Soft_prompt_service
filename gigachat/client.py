"""Wrappers around the existing `gigachat_request` callable.

`gigachat_request` lives in `external.py` (mock by default) and must
not be modified per the spec.
"""

from __future__ import annotations

import json
from typing import List, TYPE_CHECKING

from external import gigachat_request

from .prompts import (
    SYSTEM_PROMPT_BENCHMARK,
    SYSTEM_PROMPT_CHECK_PROMPT,
    SYSTEM_PROMPT_GENERATE_CONFIG,
    SYSTEM_PROMPT_IMPROVE_PROMPT,
)

if TYPE_CHECKING:
    from models.model_registry import ModelConfig


def _safe_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


async def check_prompt_with_giga(
    question: str, answer: str, model_config: "ModelConfig"
) -> dict:
    user_prompt = (
        f"Модель: {model_config.name}\n"
        f"output_type: {model_config.output_type}\n"
        f"input_format: {model_config.input_format}\n\n"
        f"Вопрос: {question}\nОтвет: {answer}"
    )
    raw = await gigachat_request(user_prompt, SYSTEM_PROMPT_CHECK_PROMPT)
    parsed = _safe_json(raw) or {}
    return {
        "valid": bool(parsed.get("valid", False)),
        "message": parsed.get("message", raw or ""),
        "suggestions": parsed.get("suggestions", []) or [],
    }


async def improve_prompt_with_giga(
    question: str, model_config: "ModelConfig"
) -> str:
    user_prompt = (
        f"Модель: {model_config.name}\noutput_type: {model_config.output_type}\n\n"
        f"Исходный вопрос: {question}"
    )
    raw = await gigachat_request(user_prompt, SYSTEM_PROMPT_IMPROVE_PROMPT)
    parsed = _safe_json(raw) or {}
    return parsed.get("improved_question", raw or question)


async def generate_model_config(description: str) -> dict:
    raw = await gigachat_request(description, SYSTEM_PROMPT_GENERATE_CONFIG)
    if not raw or not raw.strip():
        return {"error": "Пустой ответ от GigaChat"}
    return {"yaml": raw.strip()}


async def benchmark_models(
    questions: List[str],
    answers_before: List[str],
    answers_after: List[str],
    model_config: "ModelConfig",
) -> str:
    n = min(len(questions), len(answers_before), len(answers_after))
    lines = [f"Модель: {model_config.name}", f"Примеров: {n}", ""]
    for i in range(n):
        lines.append(f"Q{i+1}: {questions[i]}")
        lines.append(f"  before: {answers_before[i]}")
        lines.append(f"  after:  {answers_after[i]}")
    return await gigachat_request("\n".join(lines), SYSTEM_PROMPT_BENCHMARK)
