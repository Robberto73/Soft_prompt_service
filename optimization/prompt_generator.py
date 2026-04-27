"""Pick a template and substitute placeholders to produce a runnable
`train.py` inside the run output directory."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.model_registry import ModelConfig


TEMPLATES_DIR = Path(__file__).parent / "templates"


def _pick_template(model_config: "ModelConfig") -> Path:
    mods = {m.lower() for m in (model_config.modalities or [])}
    if "video" in mods:
        return TEMPLATES_DIR / "coop_video_llm.py"
    return TEMPLATES_DIR / "cocoop_clip.py"


def generate_coop_script(
    model_config: "ModelConfig",
    dataset_path: str,
    output_dir: str,
    coop_type: str = "coop",
    num_vectors: int | None = None,
    context_init: str | None = None,
    class_token_position: str | None = None,
    net_depth: int | None = None,
) -> str:
    template_path = _pick_template(model_config)
    if coop_type == "cocoop":
        template_path = TEMPLATES_DIR / "cocoop_clip.py"

    template = template_path.read_text(encoding="utf-8")

    subs = {
        "__DATASET_PATH__": str(dataset_path).replace("\\", "/"),
        "__OUTPUT_DIR__": str(output_dir).replace("\\", "/"),
        "__NUM_VECTORS__": str(int(num_vectors or model_config.coop_default_num_vectors or 16)),
        "__CONTEXT_INIT__": str(context_init or model_config.coop_context_init or "a photo of a"),
        "__CLASS_TOKEN_POSITION__": str(
            class_token_position or model_config.class_token_position or "end"
        ),
        "__NET_DEPTH__": str(int(net_depth or model_config.coop_net_depth or 3)),
    }
    rendered = template
    for k, v in subs.items():
        rendered = rendered.replace(k, v)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    out_script = Path(output_dir) / "train.py"
    out_script.write_text(rendered, encoding="utf-8")
    return str(out_script)
