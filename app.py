"""AutoPrompt Annotator 5.0 — FastAPI application.

All 21 endpoints from §14 of the spec are implemented here.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict


class _Body(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

from annotation.image_bbox_annotator import save_bbox_annotation
from benchmark.comparator import compare_models
from core.data_router import (
    cache_purge_loop,
    detect_file,
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
from optimization.coop_trainer import get_coop_status, run_coop_training


logger = logging.getLogger("autoprompt")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="AutoPrompt Annotator 5.0")

UPLOADS_DIR = Path("storage/uploads")
EXPORTS_DIR = Path("storage/exports")
COOP_DIR = Path("storage/coop_outputs")

_uploaded_files: dict[int, str] = {}
_next_file_id = 1
_coop_runs: dict[str, str] = {}  # run_id -> output_dir


def _register_file(path: str) -> int:
    global _next_file_id
    fid = _next_file_id
    _next_file_id += 1
    _uploaded_files[fid] = str(Path(path).resolve())
    return fid


# ----------------- startup -----------------


@app.on_event("startup")
async def _startup() -> None:
    for d in (UPLOADS_DIR, EXPORTS_DIR, COOP_DIR, Path("storage/sessions"),
              Path("storage/datasets"), Path("storage/annotations")):
        d.mkdir(parents=True, exist_ok=True)
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


@app.post("/upload")
async def upload(request: Request):
    """Multipart (Windows) or JSON `{"paths":[...]}` (Linux)."""
    content_type = (request.headers.get("content-type") or "").lower()
    file_ids: list[int] = []
    metadata: list[dict] = []

    if "application/json" in content_type:
        body = UploadPathsBody(**(await request.json()))
        for src in body.paths:
            src_path = Path(src)
            if not src_path.exists():
                continue
            if src_path.is_dir():
                for child in src_path.rglob("*"):
                    if child.is_file():
                        fid = _register_file(str(child))
                        ftype, meta = detect_file(str(child))
                        file_ids.append(fid)
                        metadata.append({"file_id": fid, "type": ftype, "metadata": meta, "path": str(child)})
            else:
                fid = _register_file(str(src_path))
                ftype, meta = detect_file(str(src_path))
                file_ids.append(fid)
                metadata.append({"file_id": fid, "type": ftype, "metadata": meta, "path": str(src_path)})
        return {"file_ids": file_ids, "metadata": metadata}

    # multipart
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    form = await request.form()
    for _, value in form.multi_items():
        if not isinstance(value, UploadFile):
            continue
        dest = UPLOADS_DIR / value.filename
        with dest.open("wb") as f:
            shutil.copyfileobj(value.file, f)
        fid = _register_file(str(dest))
        ftype, meta = detect_file(str(dest))
        file_ids.append(fid)
        metadata.append({"file_id": fid, "type": ftype, "metadata": meta, "path": str(dest)})
    return {"file_ids": file_ids, "metadata": metadata}


# ----------------- 14.3 files -----------------


@app.get("/files/{file_id}")
async def serve_file(file_id: int):
    path = _uploaded_files.get(file_id)
    if not path or not Path(path).exists():
        raise HTTPException(404, "Файл не найден")
    return FileResponse(path)


# ----------------- 14.4 annotate/start -----------------


class AnnotateStartBody(_Body):
    dataset_name: str
    model_name: str
    file_ids: List[int]


@app.post("/annotate/start")
async def annotate_start(body: AnnotateStartBody):
    files: list[dict] = []
    for fid in body.file_ids:
        path = _uploaded_files.get(fid)
        if not path:
            continue
        ftype, _ = detect_file(path)
        files.append({"id": fid, "path": path, "type": ftype})
    if not files:
        raise HTTPException(400, "Нет валидных файлов")
    session = create_session(body.dataset_name, body.model_name, files)
    return {"session_id": session["session_id"]}


# ----------------- 14.5 annotate/current -----------------


@app.get("/annotate/current")
async def annotate_current():
    session = get_active_session()
    return {"session": session}


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


# ----------------- 14.15 image/bbox/save -----------------


class BboxSaveBody(BaseModel):
    file_id: int
    format: str
    boxes: List[dict]


@app.post("/image/bbox/save")
async def image_bbox_save(body: BboxSaveBody):
    path = _uploaded_files.get(body.file_id)
    if not path:
        raise HTTPException(404, "Файл не найден")
    out = save_bbox_annotation(path, body.boxes, body.format)
    return {"annotation_file": out}


# ----------------- 14.16 video/burn_timestamp -----------------


class BurnTimestampBody(BaseModel):
    file_id: int
    start: Optional[float] = None
    end: Optional[float] = None
    bitrate: Optional[str] = None
    codec: Optional[str] = None
    use_gpu: bool = False


@app.post("/video/burn_timestamp")
async def video_burn_timestamp(body: BurnTimestampBody):
    src = _uploaded_files.get(body.file_id)
    if not src:
        raise HTTPException(404, "Файл не найден")
    src_path = Path(src)
    out_path = EXPORTS_DIR / f"{src_path.stem}_timestamped.mp4"
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
    fid = _register_file(str(out_path))
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


@app.post("/coop/train")
async def coop_train(body: CoopTrainBody):
    cfg = load_model_config(body.model_name)
    run_id = uuid.uuid4().hex[:12]
    output_dir = str(COOP_DIR / run_id)
    dataset_path = str(Path("storage/datasets") / f"{body.dataset_name}.jsonl")
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


@app.get("/coop/status/{run_id}")
async def coop_status(run_id: str):
    output_dir = _coop_runs.get(run_id)
    if not output_dir:
        candidate = COOP_DIR / run_id
        if candidate.exists():
            output_dir = str(candidate)
    if not output_dir:
        raise HTTPException(404, "run_id не найден")
    return get_coop_status(output_dir)


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
