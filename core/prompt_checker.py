"""Local rule-based prompt validation. No network calls."""

from __future__ import annotations

import re


_YESNO_TOKENS = {"yes", "no", "да", "нет", "y", "n"}


def check_prompt_local(question: str, answer: str, expected_output_type: str) -> dict:
    """Check a Q&A pair against simple rules.

    Returns `{"valid": bool, "issues": [str], "suggestions": [str]}`.
    """
    issues: list[str] = []
    suggestions: list[str] = []

    q = (question or "").strip()
    a = (answer or "").strip()

    if not q:
        issues.append("Вопрос пустой.")
    elif len(q) < 3:
        issues.append("Вопрос слишком короткий.")
        suggestions.append("Опишите вопрос подробнее (от 3 символов).")
    elif len(q) > 1000:
        issues.append("Вопрос длиннее 1000 символов.")

    if not q.endswith("?"):
        suggestions.append("Желательно завершать вопрос знаком «?».")

    if not a:
        issues.append("Ответ пустой.")

    expected = (expected_output_type or "").lower()

    if expected == "yesno":
        if a.lower() not in _YESNO_TOKENS:
            issues.append("Для yesno ожидается ответ из {yes, no, да, нет}.")
            suggestions.append("Используйте только yes / no / да / нет.")
    elif expected == "classification":
        if len(a.split()) > 5:
            suggestions.append("Для classification обычно достаточно 1–2 слов.")
        if re.search(r"[.!?]$", a):
            suggestions.append("Уберите завершающий знак препинания у класса.")
    elif expected == "free_text":
        if len(a) < 2:
            suggestions.append("Дайте более развёрнутый ответ для free_text.")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "suggestions": suggestions,
    }
