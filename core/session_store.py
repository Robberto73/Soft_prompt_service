"""JSON-file based annotation session store."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import List, Optional


SESSIONS_DIR = Path("storage/sessions")
DATASETS_DIR = Path("storage/datasets")


def _path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _read(session_id: str) -> dict:
    p = _path(session_id)
    if not p.exists():
        raise FileNotFoundError(f"Сессия не найдена: {session_id}")
    return json.loads(p.read_text(encoding="utf-8"))


def _write(session: dict) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _path(session["session_id"]).write_text(
        json.dumps(session, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_session(
    dataset_name: str,
    model_name: str,
    files: List[dict],
) -> dict:
    """`files` is a list of `{"id": int, "path": str, "type": str}` dicts."""
    session = {
        "session_id": str(uuid.uuid4()),
        "dataset_name": dataset_name,
        "model_name": model_name,
        "files": [
            {**f, "annotated": False} for f in files
        ],
        "current_index": 0,
        "annotations": [],
    }
    _write(session)
    return session


def get_session(session_id: str) -> dict:
    return _read(session_id)


def get_active_session() -> Optional[dict]:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    for p in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def save_annotation_to_session(
    session_id: str, question: str, answer: str, additional: Optional[dict] = None
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
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATASETS_DIR / f"{session['dataset_name']}.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for ann in session["annotations"]:
            f.write(json.dumps(ann, ensure_ascii=False) + "\n")
    _path(session_id).unlink(missing_ok=True)
    return str(out_path)
