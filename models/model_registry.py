"""Model YAML registry with Pydantic validation and TTL cache."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel, ValidationError


CONFIGS_DIR = Path(__file__).parent / "configs"
EXAMPLE_PATH = Path(__file__).parent / "yaml_example.yaml"
_CACHE_TTL = timedelta(hours=1)
_config_cache: dict[str, tuple["ModelConfig", datetime]] = {}


class ModelConfig(BaseModel):
    name: str
    type: Literal["composite", "monolithic"]
    components: Optional[List[dict]] = None
    modalities: List[str]
    input_format: str
    output_type: str
    min_examples_for_soft_prompt: int = 30
    recommended_annotation_style: str
    soft_prompt_guide: str
    coop_supported: Optional[bool] = False
    coop_default_num_vectors: Optional[int] = 16
    coop_context_init: Optional[str] = "a photo of a"
    class_token_position: Optional[str] = "end"
    coop_net_depth: Optional[int] = 3


def _config_path(model_name: str) -> Path:
    return CONFIGS_DIR / f"{model_name}.yml"


def list_available_models() -> List[str]:
    if not CONFIGS_DIR.exists():
        return []
    names = []
    for p in CONFIGS_DIR.glob("*.yml"):
        names.append(p.stem)
    for p in CONFIGS_DIR.glob("*.yaml"):
        if p.stem not in names:
            names.append(p.stem)
    return sorted(names)


def load_model_config(model_name: str) -> ModelConfig:
    cached = _config_cache.get(model_name)
    if cached and datetime.utcnow() - cached[1] < _CACHE_TTL:
        return cached[0]

    path = _config_path(model_name)
    if not path.exists():
        path = CONFIGS_DIR / f"{model_name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Конфиг модели не найден: {model_name}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    cfg = ModelConfig(**data)
    _config_cache[model_name] = (cfg, datetime.utcnow())
    return cfg


def save_model_config(model_name: str, yaml_content: str) -> None:
    data = yaml.safe_load(yaml_content)
    if not isinstance(data, dict):
        raise ValueError("YAML должен быть словарём верхнего уровня")
    cfg = ModelConfig(**data)
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(_config_path(model_name), "w", encoding="utf-8") as f:
        yaml.safe_dump(
            cfg.model_dump(exclude_none=True),
            f,
            allow_unicode=True,
            sort_keys=False,
        )
    _config_cache.pop(model_name, None)


_FALLBACK_PROMPT = (
    "Сгенерируй YAML-конфиг модели для AutoPrompt Annotator. Поля: "
    "name, type (composite|monolithic), modalities (список), input_format, "
    "output_type (free_text|yesno|classification), "
    "min_examples_for_soft_prompt, recommended_annotation_style, "
    "soft_prompt_guide. Для multimodal моделей укажи components."
)


def _example_yaml_text() -> str:
    if EXAMPLE_PATH.exists():
        return EXAMPLE_PATH.read_text(encoding="utf-8")
    return ""


async def generate_model_config_via_gigachat(model_identifier: str) -> dict:
    """Ask the GigaChat mock for a YAML config and validate it.

    Returns either `{"yaml": "..."}` or
    `{"error": "...", "fallback_prompt": "...", "example_yaml": "..."}`.
    """
    from gigachat.client import generate_model_config as _gen

    try:
        result = await _gen(model_identifier)
    except Exception as e:
        return {
            "error": f"Сбой обращения к GigaChat: {e}",
            "fallback_prompt": _FALLBACK_PROMPT,
            "example_yaml": _example_yaml_text(),
        }

    if "error" in result:
        result.setdefault("fallback_prompt", _FALLBACK_PROMPT)
        result.setdefault("example_yaml", _example_yaml_text())
        return result

    yaml_text = result.get("yaml", "")
    try:
        data = yaml.safe_load(yaml_text)
        ModelConfig(**data)
    except (yaml.YAMLError, ValidationError, TypeError) as e:
        return {
            "error": f"Сгенерированный YAML невалиден: {e}",
            "fallback_prompt": _FALLBACK_PROMPT,
            "example_yaml": _example_yaml_text(),
        }
    return {"yaml": yaml_text}


def generate_model_config_via_gigachat_sync(model_identifier: str) -> dict:
    """Synchronous facade for places that cannot await."""
    return asyncio.run(generate_model_config_via_gigachat(model_identifier))
