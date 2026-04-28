"""Launch CoOp/CoCoOp training as a subprocess and inspect its status.

The actual training is a stub script (see `templates/`); the control
plane (start, status, logs, output dir, run metadata) is real.
"""

from __future__ import annotations

import asyncio
import json
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
    run_meta = {
        "run_id": out.name,
        "model_name": model_config.name,
        "dataset_path": str(dataset_path),
        "coop_type": coop_type,
        "num_vectors": int(num_vectors),
        "context_init": context_init,
        "class_token_position": class_token_position,
        "net_depth": int(net_depth),
        "started_at": datetime.utcnow().isoformat(),
        "script": str(script_path),
    }
    (out / "run.json").write_text(
        json.dumps(run_meta, ensure_ascii=False, indent=2),
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


def _read_metrics(out: Path) -> dict | None:
    metrics_file = out / "metrics.json"
    if not metrics_file.exists():
        return None
    try:
        return json.loads(metrics_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_run_meta(out: Path) -> dict:
    meta_file = out / "run.json"
    if not meta_file.exists():
        return {}
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


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
    metrics = _read_metrics(out)
    meta = _read_run_meta(out)
    has_vectors = (out / "prompt_vectors.bin").exists()

    base = {
        "log": log_tail,
        "output_dir": str(out),
        "metrics": metrics,
        "meta": meta,
        "has_vectors": has_vectors,
    }
    if not lock_file.exists():
        return {"status": "unknown", **base}
    lock_text = lock_file.read_text(encoding="utf-8", errors="replace")
    if "status=" in lock_text:
        for line in lock_text.splitlines():
            if line.startswith("status="):
                return {"status": line.split("=", 1)[1].strip(), **base}
    return {"status": "running", **base}


def list_coop_runs(limit: int = 50) -> list[dict]:
    """Scan COOP_OUTPUTS for past runs, newest first."""
    if not COOP_OUTPUTS.exists():
        return []
    runs: list[dict] = []
    for d in COOP_OUTPUTS.iterdir():
        if not d.is_dir():
            continue
        meta = _read_run_meta(d)
        metrics = _read_metrics(d)
        status = get_coop_status(str(d))["status"]
        try:
            mtime = d.stat().st_mtime
        except OSError:
            mtime = 0.0
        runs.append({
            "run_id": d.name,
            "output_dir": str(d),
            "status": status,
            "started_at": meta.get("started_at"),
            "model_name": meta.get("model_name"),
            "dataset_path": meta.get("dataset_path"),
            "coop_type": meta.get("coop_type"),
            "num_vectors": meta.get("num_vectors"),
            "context_init": meta.get("context_init"),
            "metrics": metrics,
            "has_vectors": (d / "prompt_vectors.bin").exists(),
            "mtime": mtime,
        })
    runs.sort(key=lambda r: r["mtime"], reverse=True)
    return runs[:limit]


async def cancel_coop_run(output_dir: str) -> dict:
    """Terminate a running training subprocess if it is still alive.

    Best-effort: signals the process and updates the lock file. If awaiting
    the subprocess fails (e.g. the call comes from a different event loop
    than the one that spawned it — the TestClient case), we still mark
    the run as cancelled so the UI reflects the user's intent.
    """
    proc = _running.get(output_dir)
    if not proc:
        return {"status": "not_running", "output_dir": output_dir}
    try:
        proc.terminate()
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except (asyncio.TimeoutError, RuntimeError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.lock").write_text(
        f"finished_at={datetime.utcnow().isoformat()}\nstatus=cancelled\n",
        encoding="utf-8",
    )
    _running.pop(output_dir, None)
    return {"status": "cancelled", "output_dir": output_dir}


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
