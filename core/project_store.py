"""Project storage: each project owns its own uploads/annotations/sessions/datasets.

Layout:
    storage/projects/<name>/
        uploads/        original media
        annotations/    YOLO/COCO/VOC bbox + polygon exports
        datasets/       finalized JSONL datasets
        sessions/       in-progress annotation sessions
        exports/        FFmpeg-burned videos
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import List


PROJECTS_DIR = Path("storage/projects")
DEFAULT_PROJECT = "default"
_NAME_RE = re.compile(r"^[A-Za-z0-9_\-А-Яа-яЁё ]{1,64}$")
_SUBDIRS = ("uploads", "annotations", "datasets", "sessions", "exports", "coop_outputs")


def validate_name(name: str) -> str:
    name = (name or "").strip()
    if not _NAME_RE.match(name):
        raise ValueError(
            "Имя проекта должно быть 1–64 символа: буквы/цифры/пробел/дефис/подчёркивание"
        )
    return name


def project_root(name: str) -> Path:
    return PROJECTS_DIR / validate_name(name)


def project_paths(name: str) -> dict:
    root = project_root(name)
    return {
        "name": name,
        "root": root,
        **{k: root / k for k in _SUBDIRS},
    }


def list_projects() -> List[dict]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    for p in sorted(PROJECTS_DIR.iterdir()):
        if not p.is_dir():
            continue
        uploads = p / "uploads"
        n_files = sum(1 for _ in uploads.iterdir()) if uploads.exists() else 0
        out.append({"name": p.name, "files": n_files})
    return out


def create_project(name: str) -> dict:
    paths = project_paths(name)
    if paths["root"].exists():
        raise FileExistsError(f"Проект «{name}» уже существует")
    for k in _SUBDIRS:
        paths[k].mkdir(parents=True, exist_ok=True)
    return {"name": name, "files": 0}


def delete_project(name: str) -> None:
    root = project_root(name)
    if not root.exists():
        raise FileNotFoundError(f"Проект «{name}» не найден")
    shutil.rmtree(root)


def ensure_default() -> None:
    """Create the `default` project if no projects exist yet."""
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    if not any(p.is_dir() for p in PROJECTS_DIR.iterdir()):
        create_project(DEFAULT_PROJECT)


def project_exists(name: str) -> bool:
    try:
        return project_root(name).is_dir()
    except ValueError:
        return False
