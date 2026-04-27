"""Launch CoOp/CoCoOp training as a subprocess and inspect its status.

The actual training is a stub script (see `templates/`); the control
plane (start, status, logs, output dir) is real.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .prompt_generator import generate_coop_script

if TYPE_CHECKING:
    from models.model_registry import ModelConfig


COOP_OUTPUTS = Path("storage/coop_outputs")


_running: dict[str, asyncio.subprocess.Process] = {}


async def run_coop_training(
    model_config: "ModelConfig",
    dataset_path: str,
    output_dir: str,
    coop_type: str,
    num_vectors: int,
    context_init: str,
    class_token_position: str,
    net_depth: int = 3,
) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    script_path = generate_coop_script(
        model_config=model_config,
        dataset_path=dataset_path,
        output_dir=str(out),
        coop_type=coop_type,
        num_vectors=num_vectors,
        context_init=context_init,
        class_token_position=class_token_position,
        net_depth=net_depth,
    )
    log_file = out / "train.log"
    lock_file = out / "run.lock"
    lock_file.write_text(
        f"started_at={datetime.utcnow().isoformat()}\nscript={script_path}\n",
        encoding="utf-8",
    )

    log_handle = open(log_file, "a", encoding="utf-8")
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        script_path,
        stdout=log_handle,
        stderr=log_handle,
    )
    _running[str(out)] = proc

    asyncio.create_task(_wait_and_finalize(str(out), proc, log_handle))

    return {
        "status": "running",
        "log_file": str(log_file),
        "output_dir": str(out),
        "pid": proc.pid,
    }


async def _wait_and_finalize(output_dir: str, proc, log_handle) -> None:
    try:
        rc = await proc.wait()
    finally:
        try:
            log_handle.close()
        except Exception:
            pass
    status = "completed" if rc == 0 else "failed"
    Path(output_dir, "run.lock").write_text(
        f"finished_at={datetime.utcnow().isoformat()}\nstatus={status}\nreturncode={rc}\n",
        encoding="utf-8",
    )
    _running.pop(output_dir, None)


def get_coop_status(output_dir: str) -> dict:
    out = Path(output_dir)
    log_file = out / "train.log"
    lock_file = out / "run.lock"
    log_tail = ""
    if log_file.exists():
        try:
            text = log_file.read_text(encoding="utf-8", errors="replace")
            log_tail = "\n".join(text.splitlines()[-30:])
        except Exception:
            log_tail = ""
    if not lock_file.exists():
        return {"status": "unknown", "log": log_tail, "output_dir": str(out)}
    lock_text = lock_file.read_text(encoding="utf-8", errors="replace")
    if "status=" in lock_text:
        for line in lock_text.splitlines():
            if line.startswith("status="):
                return {
                    "status": line.split("=", 1)[1].strip(),
                    "log": log_tail,
                    "output_dir": str(out),
                }
    return {"status": "running", "log": log_tail, "output_dir": str(out)}


def apply_learned_prompt(
    model_config: "ModelConfig", prompt_vectors_path: str
) -> None:
    """Stub: in the real system this would inject vectors into the model."""
    p = Path(prompt_vectors_path)
    if not p.exists():
        raise FileNotFoundError(prompt_vectors_path)
    log = COOP_OUTPUTS / "apply.log"
    COOP_OUTPUTS.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(
            f"{datetime.utcnow().isoformat()} loaded vectors for "
            f"{model_config.name} from {p} ({p.stat().st_size}B)\n"
        )
