"""File type detection, metadata extraction and an in-memory cache.

Cache entries older than 30 days are evicted by `purge_metadata_cache`,
which is meant to be called periodically from the application startup
event (see `app.py`).
"""

from __future__ import annotations

import asyncio
import os
import struct
from datetime import datetime, timedelta
from pathlib import Path
from typing import Tuple


VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff", ".gif"}
TEXT_EXT = {".txt", ".md", ".json", ".csv", ".log", ".tsv", ".yaml", ".yml"}


_metadata_cache: dict[str, tuple[dict, datetime]] = {}
_CACHE_TTL = timedelta(days=30)


def _abs(path: str) -> str:
    return str(Path(path).resolve())


def detect_file(file_path: str) -> Tuple[str, dict]:
    """Detect file type and return its metadata.

    Returns a tuple `(type, metadata)` where `type` is one of
    `"video"`, `"image"`, `"text"` or `"unknown"`.
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(file_path)
    ext = p.suffix.lower()
    if ext in VIDEO_EXT:
        return "video", get_video_metadata(str(p))
    if ext in IMAGE_EXT:
        return "image", get_image_metadata(str(p))
    if ext in TEXT_EXT:
        return "text", get_text_metadata(str(p))
    return "unknown", {"size_kb": int(p.stat().st_size / 1024)}


def _cache_get(key: str) -> dict | None:
    item = _metadata_cache.get(key)
    if not item:
        return None
    data, ts = item
    if datetime.utcnow() - ts > _CACHE_TTL:
        _metadata_cache.pop(key, None)
        return None
    return data


def _cache_put(key: str, value: dict) -> None:
    _metadata_cache[key] = (value, datetime.utcnow())


def get_video_metadata(file_path: str) -> dict:
    key = _abs(file_path)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    import cv2

    cap = cv2.VideoCapture(key)
    if not cap.isOpened():
        meta = {
            "duration": 0.0,
            "width": 0,
            "height": 0,
            "bitrate": 0,
            "fps": 0.0,
            "video_codec": "unknown",
            "audio_codec": None,
        }
    else:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        try:
            codec = struct.pack("<I", fourcc_int).decode("ascii", errors="replace").strip()
        except Exception:
            codec = "unknown"
        duration = (frames / fps) if fps > 0 else 0.0
        size_bytes = os.path.getsize(key)
        bitrate = int(size_bytes * 8 / duration) if duration > 0 else 0
        cap.release()
        meta = {
            "duration": float(duration),
            "width": width,
            "height": height,
            "bitrate": bitrate,
            "fps": float(fps),
            "video_codec": codec or "unknown",
            "audio_codec": None,
        }

    _cache_put(key, meta)
    return meta


def get_image_metadata(file_path: str) -> dict:
    key = _abs(file_path)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    from PIL import Image

    with Image.open(key) as img:
        width, height = img.size
        fmt = (img.format or "").lower()
    size_kb = int(os.path.getsize(key) / 1024)
    meta = {"width": width, "height": height, "format": fmt, "size_kb": size_kb}
    _cache_put(key, meta)
    return meta


def get_text_metadata(file_path: str) -> dict:
    key = _abs(file_path)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    with open(key, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    meta = {
        "chars": len(content),
        "words": len(content.split()),
        "lines": content.count("\n") + (0 if content.endswith("\n") else 1),
    }
    _cache_put(key, meta)
    return meta


def purge_metadata_cache() -> int:
    """Drop entries older than the TTL. Returns number of removed entries."""
    now = datetime.utcnow()
    stale = [k for k, (_, ts) in _metadata_cache.items() if now - ts > _CACHE_TTL]
    for k in stale:
        _metadata_cache.pop(k, None)
    return len(stale)


async def cache_purge_loop(interval_seconds: int = 3600) -> None:
    """Background task: every `interval_seconds` purge stale cache."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            purge_metadata_cache()
        except asyncio.CancelledError:
            return
        except Exception:
            continue
