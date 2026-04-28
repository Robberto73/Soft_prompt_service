"""AutoPrompt Annotator 5.0 — FastAPI application.

All 21 endpoints from §14 of the spec are implemented here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile as StarletteUploadFile
from pydantic import BaseModel, ConfigDict


class _Body(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

from annotation.image_bbox_annotator import (
    load_shape_annotation,
    save_bbox_annotation,
    save_shape_annotation,
)
from benchmark.comparator import compare_models
from core import project_store
from core.data_router import (
    cache_purge_loop,
    detect_file,
    invalidate_metadata_cache,
    purge_metadata_cache,
)
from core.prompt_checker import check_prompt_local
from core.session_store import (
    advance_session,
    create_session,
    finalize_session,
    get_active_session,
    get_session,
    progress_string,
    save_annotation_to_session,
)
from core.time_overlay import burn_timestamp_to_video, check_ffmpeg_available
from gigachat.client import (
    check_prompt_with_giga,
    improve_prompt_with_giga,
)
from guides.help_data import HELP_TEXTS
from models.model_registry import (
    generate_model_config_via_gigachat,
    list_available_models,
    load_model_config,
    save_model_config,
)
from optimization.coop_trainer import (
    apply_learned_prompt,
    cancel_coop_run,
    get_coop_status,
    list_coop_runs,
    run_coop_training,
)


logger = logging.getLogger("autoprompt")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# When the service runs behind a reverse proxy (JupyterHub / nginx), set
# APP_ROOT_PATH to the proxy prefix, e.g. "/user/aveocr/proxy/5000".
# This keeps OpenAPI/docs and redirects pointing at the proxied URL.
ROOT_PATH = os.environ.get("APP_ROOT_PATH", "").rstrip("/")

app = FastAPI(title="AutoPrompt Annotator 5.0", root_path=ROOT_PATH)

UPLOADS_DIR = Path("storage/uploads")
EXPORTS_DIR = Path("storage/exports")
COOP_DIR = Path("storage/coop_outputs")

# file registry: file_id -> {"path": str, "project": Optional[str]}
_uploaded_files: dict[int, dict] = {}
_next_file_id = 1
_coop_runs: dict[str, str] = {}  # run_id -> output_dir


def _register_file(path: str, project: Optional[str] = None) -> int:
    global _next_file_id
    fid = _next_file_id
    _next_file_id += 1
    _uploaded_files[fid] = {
        "path": str(Path(path).resolve()),
        "project": project,
    }
    return fid


def _file_path(file_id: int) -> Optional[str]:
    rec = _uploaded_files.get(file_id)
    return rec["path"] if rec else None


def _file_project(file_id: int) -> Optional[str]:
    rec = _uploaded_files.get(file_id)
    return rec["project"] if rec else None


# ----------------- startup -----------------


@app.on_event("startup")
async def _startup() -> None:
    for d in (UPLOADS_DIR, EXPORTS_DIR, COOP_DIR, Path("storage/sessions"),
              Path("storage/datasets"), Path("storage/annotations")):
        d.mkdir(parents=True, exist_ok=True)
    project_store.ensure_default()
    if ROOT_PATH:
        logger.info("Сервис работает под префиксом proxy: %s", ROOT_PATH)
    if check_ffmpeg_available():
        logger.info("FFmpeg доступен в PATH")
    else:
        logger.warning("FFmpeg НЕ найден в PATH — экспорт видео работать не будет")
    purge_metadata_cache()
    asyncio.create_task(cache_purge_loop(3600))


# ----------------- root -----------------


@app.get("/")
async def root():
    index = Path("static/index.html")
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"status": "ok", "message": "static/index.html не найден"})


# ----------------- 14.1 OS -----------------


@app.get("/get_os_type")
async def get_os_type():
    sysname = platform.system().lower()
    return {"os": "windows" if "windows" in sysname else "linux"}


# ----------------- 14.2 upload -----------------


class UploadPathsBody(BaseModel):
    paths: List[str]
    project: Optional[str] = None


def _resolve_uploads_dir(project: Optional[str]) -> Path:
    if project and project_store.project_exists(project):
        d = project_store.project_paths(project)["uploads"]
        d.mkdir(parents=True, exist_ok=True)
        return d
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOADS_DIR


@app.post("/upload")
async def upload(request: Request):
    """Multipart (Windows) or JSON `{"paths":[...]}` (Linux).

    Multipart accepts an optional `project` form field.
    JSON body accepts an optional `project` key.
    """
    content_type = (request.headers.get("content-type") or "").lower()
    file_ids: list[int] = []
    metadata: list[dict] = []

    if "application/json" in content_type:
        body = UploadPathsBody(**(await request.json()))
        project = body.project
        if project and not project_store.project_exists(project):
            raise HTTPException(404, f"Проект «{project}» не найден")
        for src in body.paths:
            src_path = Path(src)
            if not src_path.exists():
                continue
            if src_path.is_dir():
                for child in src_path.rglob("*"):
                    if child.is_file():
                        fid = _register_file(str(child), project)
                        ftype, meta = detect_file(str(child))
                        file_ids.append(fid)
                        metadata.append({
                            "file_id": fid, "type": ftype, "metadata": meta,
                            "path": str(child), "project": project,
                        })
            else:
                fid = _register_file(str(src_path), project)
                ftype, meta = detect_file(str(src_path))
                file_ids.append(fid)
                metadata.append({
                    "file_id": fid, "type": ftype, "metadata": meta,
                    "path": str(src_path), "project": project,
                })
        return {"file_ids": file_ids, "metadata": metadata}

    # multipart
    form = await request.form()
    project = form.get("project") or None
    if isinstance(project, StarletteUploadFile):
        project = None
    if project and not project_store.project_exists(project):
        raise HTTPException(404, f"Проект «{project}» не найден")
    uploads_dir = _resolve_uploads_dir(project)
    for _, value in form.multi_items():
        if not isinstance(value, StarletteUploadFile):
            continue
        if not value.filename:
            continue
        dest = uploads_dir / Path(value.filename).name
        with dest.open("wb") as f:
            shutil.copyfileobj(value.file, f)
        fid = _register_file(str(dest), project)
        ftype, meta = detect_file(str(dest))
        file_ids.append(fid)
        metadata.append({
            "file_id": fid, "type": ftype, "metadata": meta,
            "path": str(dest), "project": project,
        })
    return {"file_ids": file_ids, "metadata": metadata}


# ----------------- 14.3 files -----------------


@app.get("/files/{file_id}")
async def serve_file(file_id: int):
    path = _file_path(file_id)
    if not path or not Path(path).exists():
        raise HTTPException(404, "Файл не найден")
    return FileResponse(path)


def _is_under_managed_uploads(p: Path) -> bool:
    """True if `p` is inside one of the upload directories we manage
    (legacy `storage/uploads/` or any project's uploads/ subfolder)."""
    try:
        resolved = p.resolve()
    except OSError:
        return False
    candidates = [UPLOADS_DIR.resolve()]
    if project_store.PROJECTS_DIR.exists():
        for proj in project_store.PROJECTS_DIR.iterdir():
            up = proj / "uploads"
            if up.exists():
                candidates.append(up.resolve())
    return any(c in resolved.parents or c == resolved for c in candidates)


@app.delete("/files/{file_id}")
async def delete_file(file_id: int, keep_disk: bool = False):
    """Remove an uploaded file from the registry and (by default) from disk."""
    rec = _uploaded_files.pop(file_id, None)
    if not rec:
        raise HTTPException(404, "Файл не найден в реестре")
    path = rec["path"]
    invalidate_metadata_cache(path)
    deleted_from_disk = False
    if not keep_disk:
        try:
            p = Path(path)
            if p.exists() and _is_under_managed_uploads(p):
                p.unlink()
                deleted_from_disk = True
        except OSError as e:
            logger.warning("Не удалось удалить %s: %s", path, e)
    return {"status": "ok", "file_id": file_id, "deleted_from_disk": deleted_from_disk}


# ----------------- 14.4 annotate/start -----------------


class AnnotateStartBody(_Body):
    dataset_name: str
    model_name: str
    file_ids: List[int]
    project: Optional[str] = None


@app.post("/annotate/start")
async def annotate_start(body: AnnotateStartBody):
    files: list[dict] = []
    for fid in body.file_ids:
        path = _file_path(fid)
        if not path:
            continue
        ftype, _ = detect_file(path)
        files.append({"id": fid, "path": path, "type": ftype})
    if not files:
        raise HTTPException(400, "Нет валидных файлов")
    project = body.project
    if project and not project_store.project_exists(project):
        raise HTTPException(404, f"Проект «{project}» не найден")
    session = create_session(body.dataset_name, body.model_name, files, project=project)
    return {"session_id": session["session_id"]}


# ----------------- 14.5 annotate/current -----------------


@app.get("/annotate/current")
async def annotate_current(project: Optional[str] = None):
    session = get_active_session(project)
    return {"session": session}


# ----------------- projects -----------------


class CreateProjectBody(BaseModel):
    name: str


@app.get("/projects")
async def projects_list():
    return project_store.list_projects()


@app.post("/projects")
async def projects_create(body: CreateProjectBody):
    try:
        return project_store.create_project(body.name)
    except FileExistsError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/projects/{name}")
async def projects_delete(name: str):
    try:
        project_store.delete_project(name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Drop registry entries belonging to this project
    stale = [fid for fid, rec in _uploaded_files.items() if rec.get("project") == name]
    for fid in stale:
        _uploaded_files.pop(fid, None)
    return {"status": "ok", "removed_files": len(stale)}


@app.get("/projects/{name}/files")
async def projects_files(name: str):
    if not project_store.project_exists(name):
        raise HTTPException(404, f"Проект «{name}» не найден")
    items = []
    for fid, rec in _uploaded_files.items():
        if rec.get("project") == name:
            try:
                ftype, meta = detect_file(rec["path"])
            except Exception:
                ftype, meta = "unknown", {}
            items.append({
                "file_id": fid, "path": rec["path"],
                "type": ftype, "metadata": meta, "project": name,
            })
    return {"files": items}


@app.post("/projects/{name}/rescan")
async def projects_rescan(name: str):
    """Walk `<project>/uploads/` on disk and register any files that are
    not yet in the in-memory registry. Useful after a server restart or
    when files were placed into the folder by hand.
    """
    if not project_store.project_exists(name):
        raise HTTPException(404, f"Проект «{name}» не найден")
    uploads = project_store.project_paths(name)["uploads"]
    if not uploads.exists():
        return {"added": [], "added_count": 0}
    known_paths = {Path(rec["path"]).resolve() for rec in _uploaded_files.values()}
    added: list[dict] = []
    for p in sorted(uploads.iterdir()):
        if not p.is_file():
            continue
        if p.resolve() in known_paths:
            continue
        fid = _register_file(str(p), name)
        try:
            ftype, meta = detect_file(str(p))
        except Exception:
            ftype, meta = "unknown", {}
        added.append({
            "file_id": fid, "path": str(p),
            "type": ftype, "metadata": meta, "project": name,
        })
    return {"added": added, "added_count": len(added)}


# ----------------- 14.6 annotate/next -----------------


class SessionIdBody(BaseModel):
    session_id: str


@app.post("/annotate/next")
async def annotate_next(body: SessionIdBody):
    session = advance_session(body.session_id)
    idx = session["current_index"]
    if idx >= len(session["files"]):
        raise HTTPException(400, "Сессия завершена")
    file_info = session["files"][idx]
    _, meta = detect_file(file_info["path"])
    return {
        "file_id": file_info["id"],
        "type": file_info["type"],
        "metadata": meta,
    }


# ----------------- 14.7 save_annotation -----------------


class SaveAnnotationBody(BaseModel):
    session_id: str
    question: str
    answer: str
    timestamp: Optional[float] = None
    additional: Optional[dict] = None


@app.post("/save_annotation")
async def save_annotation(body: SaveAnnotationBody):
    additional = dict(body.additional or {})
    if body.timestamp is not None:
        additional["timestamp"] = body.timestamp
    save_annotation_to_session(
        body.session_id, body.question, body.answer, additional
    )
    return {"progress": progress_string(body.session_id)}


class FinalizeBody(BaseModel):
    session_id: str


@app.post("/annotate/finalize")
async def annotate_finalize(body: FinalizeBody):
    out_path = finalize_session(body.session_id)
    return {"dataset_path": out_path}


# ----------------- 14.8 check_prompt_giga -----------------


class CheckPromptBody(_Body):
    question: str
    answer: str
    model_name: str


@app.post("/check_prompt_giga")
async def check_prompt_giga(body: CheckPromptBody):
    cfg = load_model_config(body.model_name)
    local = check_prompt_local(body.question, body.answer, cfg.output_type)
    giga = await check_prompt_with_giga(body.question, body.answer, cfg)
    return {
        "valid": bool(local["valid"] and giga.get("valid", False)),
        "message": giga.get("message", ""),
        "suggestions": list(local["suggestions"]) + list(giga.get("suggestions", [])),
        "local": local,
    }


# ----------------- 14.9 improve_prompt_giga -----------------


class ImprovePromptBody(_Body):
    question: str
    model_name: str


@app.post("/improve_prompt_giga")
async def improve_prompt_giga(body: ImprovePromptBody):
    cfg = load_model_config(body.model_name)
    improved = await improve_prompt_with_giga(body.question, cfg)
    return {"improved_question": improved}


# ----------------- 14.10 models/list -----------------


@app.get("/models/list")
async def models_list():
    return list_available_models()


# ----------------- 14.11 generate_config -----------------


class GenerateConfigBody(_Body):
    model_identifier: str


@app.post("/models/generate_config")
async def models_generate_config(body: GenerateConfigBody):
    return await generate_model_config_via_gigachat(body.model_identifier)


# ----------------- 14.12 save_config -----------------


class SaveConfigBody(BaseModel):
    name: str
    yaml: str


@app.post("/models/save_config")
async def models_save_config(body: SaveConfigBody):
    try:
        save_model_config(body.name, body.yaml)
    except Exception as e:
        raise HTTPException(400, f"Ошибка сохранения: {e}")
    return {"status": "ok"}


# ----------------- 14.13 soft_prompt_guide -----------------


@app.get("/models/soft_prompt_guide/{model_name}")
async def models_guide(model_name: str):
    cfg = load_model_config(model_name)
    return {"guide": cfg.soft_prompt_guide}


# ----------------- 14.14 min_examples -----------------


@app.get("/models/min_examples/{model_name}")
async def models_min_examples(model_name: str):
    cfg = load_model_config(model_name)
    return {"min_examples": cfg.min_examples_for_soft_prompt}


# ----------------- model info (full config dump) -----------------


@app.get("/models/info/{model_name}")
async def models_info(model_name: str):
    cfg = load_model_config(model_name)
    return cfg.model_dump()


# ----------------- 14.15 image/bbox/save -----------------


class BboxSaveBody(BaseModel):
    file_id: int
    format: str
    boxes: List[dict]
    project: Optional[str] = None


def _annotations_dir_for(project: Optional[str], file_id: int) -> Path:
    """Resolve the annotations directory: explicit project arg > file's
    project > legacy storage/annotations/."""
    name = project or _file_project(file_id)
    if name and project_store.project_exists(name):
        d = project_store.project_paths(name)["annotations"]
        d.mkdir(parents=True, exist_ok=True)
        return d
    legacy = Path("storage/annotations")
    legacy.mkdir(parents=True, exist_ok=True)
    return legacy


@app.post("/image/bbox/save")
async def image_bbox_save(body: BboxSaveBody):
    path = _file_path(body.file_id)
    if not path:
        raise HTTPException(404, "Файл не найден")
    out_dir = _annotations_dir_for(body.project, body.file_id)
    out = save_bbox_annotation(path, body.boxes, body.format, output_dir=out_dir)
    return {"annotation_file": out}


class ShapesSaveBody(BaseModel):
    """Unified bbox + polygon save. Each shape is either
    `{class, x1, y1, x2, y2}` or `{class, points: [[x,y], ...]}`."""
    file_id: int
    format: str
    shapes: List[dict]
    project: Optional[str] = None


@app.post("/image/shapes/save")
async def image_shapes_save(body: ShapesSaveBody):
    path = _file_path(body.file_id)
    if not path:
        raise HTTPException(404, "Файл не найден")
    out_dir = _annotations_dir_for(body.project, body.file_id)
    out = save_shape_annotation(path, body.shapes, body.format, output_dir=out_dir)
    return {"annotation_file": out, "count": len(body.shapes)}


@app.get("/image/shapes/{file_id}")
async def image_shapes_get(file_id: int, project: Optional[str] = None):
    """Read existing annotation for the file (if any) and return shapes
    in the same format the frontend uses. Coords are in image pixels.
    """
    path = _file_path(file_id)
    if not path:
        raise HTTPException(404, "Файл не найден")
    out_dir = _annotations_dir_for(project, file_id)
    return load_shape_annotation(path, output_dir=out_dir)


# ----------------- 14.16 video/burn_timestamp -----------------


class BurnTimestampBody(BaseModel):
    file_id: int
    start: Optional[float] = None
    end: Optional[float] = None
    bitrate: Optional[str] = None
    codec: Optional[str] = None
    use_gpu: bool = False
    project: Optional[str] = None


@app.post("/video/burn_timestamp")
async def video_burn_timestamp(body: BurnTimestampBody):
    src = _file_path(body.file_id)
    if not src:
        raise HTTPException(404, "Файл не найден")
    src_path = Path(src)
    project = body.project or _file_project(body.file_id)
    if project and project_store.project_exists(project):
        export_dir = project_store.project_paths(project)["exports"]
    else:
        export_dir = EXPORTS_DIR
    export_dir.mkdir(parents=True, exist_ok=True)
    out_path = export_dir / f"{src_path.stem}_timestamped.mp4"
    try:
        result = await burn_timestamp_to_video(
            input_path=str(src_path),
            output_path=str(out_path),
            start=body.start,
            end=body.end,
            bitrate=body.bitrate,
            codec=body.codec,
            use_gpu=body.use_gpu,
        )
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    if result["returncode"] != 0:
        raise HTTPException(500, f"FFmpeg ошибка:\n{result['stderr'][:500]}")
    fid = _register_file(str(out_path), project)
    return {"exported_url": f"/files/{fid}", "file_id": fid}


# ----------------- 14.17 coop/train -----------------


class CoopTrainBody(_Body):
    model_name: str
    dataset_name: str
    coop_type: str = "coop"
    num_vectors: int = 16
    context_init: str = "a photo of a"
    class_token_position: str = "end"
    net_depth: int = 3
    project: Optional[str] = None


def _resolve_dataset_path(dataset_name: str, project: Optional[str]) -> str:
    """Find <name>.jsonl in project's datasets/, then in legacy
    storage/datasets/. Accepts a name with or without .jsonl extension."""
    fname = dataset_name if dataset_name.endswith(".jsonl") else f"{dataset_name}.jsonl"
    if project and project_store.project_exists(project):
        cand = project_store.project_paths(project)["datasets"] / fname
        if cand.exists():
            return str(cand)
    legacy = Path("storage/datasets") / fname
    return str(legacy)


@app.post("/coop/train")
async def coop_train(body: CoopTrainBody):
    cfg = load_model_config(body.model_name)
    if not getattr(cfg, "coop_supported", False):
        raise HTTPException(
            400,
            f"Модель «{cfg.name}» не поддерживает CoOp/CoCoOp "
            f"(в YAML установите coop_supported: true).",
        )
    dataset_path = _resolve_dataset_path(body.dataset_name, body.project)
    if not Path(dataset_path).exists():
        raise HTTPException(
            404,
            f"Датасет не найден: {dataset_path}. "
            f"Сначала завершите сессию разметки или укажите существующий .jsonl.",
        )
    run_id = uuid.uuid4().hex[:12]
    output_dir = str(COOP_DIR / run_id)
    info = await run_coop_training(
        model_config=cfg,
        dataset_path=dataset_path,
        output_dir=output_dir,
        coop_type=body.coop_type,
        num_vectors=body.num_vectors,
        context_init=body.context_init,
        class_token_position=body.class_token_position,
        net_depth=body.net_depth,
    )
    _coop_runs[run_id] = output_dir
    return {"run_id": run_id, **info}


# ----------------- 14.18 coop/status -----------------


def _output_dir_for_run(run_id: str) -> Optional[str]:
    output_dir = _coop_runs.get(run_id)
    if not output_dir:
        candidate = COOP_DIR / run_id
        if candidate.exists():
            output_dir = str(candidate)
    return output_dir


@app.get("/coop/status/{run_id}")
async def coop_status(run_id: str):
    output_dir = _output_dir_for_run(run_id)
    if not output_dir:
        raise HTTPException(404, "run_id не найден")
    return get_coop_status(output_dir)


@app.get("/coop/runs")
async def coop_runs_list(limit: int = 50):
    return {"runs": list_coop_runs(limit=limit)}


@app.post("/coop/cancel/{run_id}")
async def coop_cancel(run_id: str):
    output_dir = _output_dir_for_run(run_id)
    if not output_dir:
        raise HTTPException(404, "run_id не найден")
    return await cancel_coop_run(output_dir)


class CoopApplyBody(_Body):
    model_name: str
    run_id: str


@app.post("/coop/apply")
async def coop_apply(body: CoopApplyBody):
    output_dir = _output_dir_for_run(body.run_id)
    if not output_dir:
        raise HTTPException(404, "run_id не найден")
    vectors = Path(output_dir) / "prompt_vectors.bin"
    if not vectors.exists():
        raise HTTPException(400, "Векторы prompt_vectors.bin ещё не сохранены.")
    cfg = load_model_config(body.model_name)
    apply_learned_prompt(cfg, str(vectors))
    return {"status": "ok", "vectors_path": str(vectors), "model": cfg.name}


# ----------------- datasets list (for CoOp tab dropdown) -----------------


@app.get("/datasets/list")
async def datasets_list(project: Optional[str] = None):
    """List available *.jsonl datasets in the active project and the
    legacy storage/datasets/ folder."""
    items: list[dict] = []
    seen: set[str] = set()
    if project and project_store.project_exists(project):
        d = project_store.project_paths(project)["datasets"]
        if d.exists():
            for p in sorted(d.glob("*.jsonl")):
                items.append({
                    "name": p.stem, "path": str(p),
                    "size": p.stat().st_size, "project": project,
                })
                seen.add(p.stem)
    legacy = Path("storage/datasets")
    if legacy.exists():
        for p in sorted(legacy.glob("*.jsonl")):
            if p.stem in seen:
                continue
            items.append({
                "name": p.stem, "path": str(p),
                "size": p.stat().st_size, "project": None,
            })
    return {"datasets": items}


# ----------------- 14.19 benchmark/compare -----------------


class BenchmarkBody(_Body):
    model_name: str
    questions: List[str]
    answers_before: List[str]
    answers_after: List[str]


@app.post("/benchmark/compare")
async def benchmark_compare(body: BenchmarkBody):
    cfg = load_model_config(body.model_name)
    return await compare_models(
        body.questions, body.answers_before, body.answers_after, cfg
    )


# ----------------- 14.20 help -----------------


@app.get("/help/{element_selector:path}")
async def help_endpoint(element_selector: str):
    selector = element_selector
    if not selector.startswith("#") and not selector.startswith("."):
        selector = "#" + selector
    data = HELP_TEXTS.get(selector)
    if not data:
        raise HTTPException(404, f"Подсказка для {selector} не найдена")
    return data


# Mount static at the very end so it does not shadow API routes.
app.mount("/static", StaticFiles(directory="static"), name="static")
