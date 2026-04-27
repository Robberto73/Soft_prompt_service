"""JSON-file based annotation session store, project-aware.

Each session lives in:
    storage/projects/<project>/sessions/<session_id>.json
Or, if no project is given, in the legacy `storage/sessions/`.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import List, Optional

from . import project_store


LEGACY_SESSIONS_DIR = Path("storage/sessions")
LEGACY_DATASETS_DIR = Path("storage/datasets")


def _sessions_dir(project: Optional[str]) -> Path:
    if project:
        return project_store.project_paths(project)["sessions"]
    return LEGACY_SESSIONS_DIR


def _datasets_dir(project: Optional[str]) -> Path:
    if project:
        return project_store.project_paths(project)["datasets"]
    return LEGACY_DATASETS_DIR


def _session_path(session_id: str, project: Optional[str] = None) -> Path:
    return _sessions_dir(project) / f"{session_id}.json"


def _find_session_path(session_id: str) -> Path:
    """Locate a session file across all projects + legacy."""
    candidate = LEGACY_SESSIONS_DIR / f"{session_id}.json"
    if candidate.exists():
        return candidate
    project_store.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    for proj in project_store.PROJECTS_DIR.iterdir():
        if not proj.is_dir():
            continue
        candidate = proj / "sessions" / f"{session_id}.json"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Сессия не найдена: {session_id}")


def _read(session_id: str) -> dict:
    return json.loads(_find_session_path(session_id).read_text(encoding="utf-8"))


def _write(session: dict) -> None:
    project = session.get("project")
    out_dir = _sessions_dir(project)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{session['session_id']}.json").write_text(
        json.dumps(session, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_session(
    dataset_name: str,
    model_name: str,
    files: List[dict],
    project: Optional[str] = None,
) -> dict:
    """`files` is a list of `{"id": int, "path": str, "type": str}` dicts."""
    session = {
        "session_id": str(uuid.uuid4()),
        "project": project,
        "dataset_name": dataset_name,
        "model_name": model_name,
        "files": [{**f, "annotated": False} for f in files],
        "current_index": 0,
        "annotations": [],
    }
    _write(session)
    return session


def get_session(session_id: str) -> dict:
    return _read(session_id)


def get_active_session(project: Optional[str] = None) -> Optional[dict]:
    """Return the most-recent in-progress session for a project (or any project)."""
    candidates: list[Path] = []
    if project:
        d = _sessions_dir(project)
        if d.exists():
            candidates.extend(d.glob("*.json"))
    else:
        if LEGACY_SESSIONS_DIR.exists():
            candidates.extend(LEGACY_SESSIONS_DIR.glob("*.json"))
        if project_store.PROJECTS_DIR.exists():
            for proj in project_store.PROJECTS_DIR.iterdir():
                ses = proj / "sessions"
                if ses.exists():
                    candidates.extend(ses.glob("*.json"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    try:
        return json.loads(candidates[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def save_annotation_to_session(
    session_id: str,
    question: str,
    answer: str,
    additional: Optional[dict] = None,
) -> dict:
    session = _read(session_id)
    idx = session["current_index"]
    file_info = session["files"][idx] if idx < len(session["files"]) else {}
    record = {
        "file_id": file_info.get("id"),
        "file_path": file_info.get("path"),
        "type": file_info.get("type"),
        "question": question,
        "answer": answer,
        "additional": additional or {},
    }
    session["annotations"].append(record)
    if idx < len(session["files"]):
        session["files"][idx]["annotated"] = True
    _write(session)
    return session


def advance_session(session_id: str) -> dict:
    session = _read(session_id)
    if session["current_index"] < len(session["files"]) - 1:
        session["current_index"] += 1
    _write(session)
    return session


def progress_string(session_id: str) -> str:
    session = _read(session_id)
    annotated = sum(1 for f in session["files"] if f.get("annotated"))
    return f"{annotated}/{len(session['files'])}"


def finalize_session(session_id: str) -> str:
    session = _read(session_id)
    out_dir = _datasets_dir(session.get("project"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{session['dataset_name']}.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for ann in session["annotations"]:
            f.write(json.dumps(ann, ensure_ascii=False) + "\n")
    _find_session_path(session_id).unlink(missing_ok=True)
    return str(out_path)
