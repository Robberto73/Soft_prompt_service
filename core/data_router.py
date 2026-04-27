"""File type detection, metadata extraction and an in-memory cache.

Cache entries older than 30 days are evicted by `purge_metadata_cache`,
which is meant to be called periodically from the application startup
event (see `app.py`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import struct
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)


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


def _empty_video_meta() -> dict:
    return {
        "duration": 0.0,
        "width": 0,
        "height": 0,
        "bitrate": 0,
        "fps": 0.0,
        "video_codec": "unknown",
        "audio_codec": None,
    }


def _ffprobe_video_metadata(key: str) -> dict | None:
    """Use ffprobe (ships with FFmpeg) to extract metadata.

    Returned only on success; otherwise None so callers can fall back.
    """
    if shutil.which("ffprobe") is None:
        return None
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-print_format", "json",
                "-show_format", "-show_streams",
                key,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        logger.warning("ffprobe failed for %s: %s", key, e)
        return None

    streams = data.get("streams", []) or []
    fmt = data.get("format", {}) or {}
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video:
        return None

    def _parse_fps(s: str | None) -> float:
        if not s:
            return 0.0
        if "/" in s:
            num, _, den = s.partition("/")
            try:
                num_f = float(num); den_f = float(den)
                return num_f / den_f if den_f else 0.0
            except ValueError:
                return 0.0
        try: return float(s)
        except ValueError: return 0.0

    def _to_int(x) -> int:
        try: return int(x)
        except (TypeError, ValueError): return 0
    def _to_float(x) -> float:
        try: return float(x)
        except (TypeError, ValueError): return 0.0

    duration = _to_float(video.get("duration") or fmt.get("duration"))
    bitrate = _to_int(video.get("bit_rate") or fmt.get("bit_rate"))

    return {
        "duration": duration,
        "width": _to_int(video.get("width")),
        "height": _to_int(video.get("height")),
        "bitrate": bitrate,
        "fps": _parse_fps(video.get("r_frame_rate") or video.get("avg_frame_rate")),
        "video_codec": video.get("codec_name") or "unknown",
        "audio_codec": audio.get("codec_name") if audio else None,
    }


def _cv2_video_metadata(key: str) -> dict | None:
    """Fallback to OpenCV if ffprobe is not available. Tolerates a broken
    cv2 install (e.g. NumPy ABI mismatch) by returning None."""
    try:
        import cv2  # type: ignore
    except (ImportError, AttributeError) as e:
        logger.warning("cv2 import failed: %s", e)
        return None
    try:
        cap = cv2.VideoCapture(key)
        if not cap.isOpened():
            cap.release()
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        cap.release()
        try:
            codec = struct.pack("<I", fourcc_int).decode("ascii", errors="replace").strip()
        except Exception:
            codec = "unknown"
        duration = (frames / fps) if fps > 0 else 0.0
        size_bytes = os.path.getsize(key)
        bitrate = int(size_bytes * 8 / duration) if duration > 0 else 0
        return {
            "duration": float(duration),
            "width": width,
            "height": height,
            "bitrate": bitrate,
            "fps": float(fps),
            "video_codec": codec or "unknown",
            "audio_codec": None,
        }
    except Exception as e:
        logger.warning("cv2 video probe failed: %s", e)
        return None


def get_video_metadata(file_path: str) -> dict:
    key = _abs(file_path)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    meta = _ffprobe_video_metadata(key)
    if meta is None:
        meta = _cv2_video_metadata(key)
    if meta is None:
        meta = _empty_video_meta()
        meta["size_kb"] = int(os.path.getsize(key) / 1024)
        meta["probe_error"] = "ни ffprobe, ни cv2 не доступны"

    _cache_put(key, meta)
    return meta


def get_image_metadata(file_path: str) -> dict:
    key = _abs(file_path)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    size_kb = int(os.path.getsize(key) / 1024)
    try:
        from PIL import Image  # type: ignore
        with Image.open(key) as img:
            width, height = img.size
            fmt = (img.format or "").lower()
        meta = {"width": width, "height": height, "format": fmt, "size_kb": size_kb}
    except (ImportError, AttributeError) as e:
        logger.warning("Pillow import failed: %s", e)
        meta = {"width": 0, "height": 0, "format": Path(key).suffix.lstrip("."), "size_kb": size_kb}
    except Exception as e:
        logger.warning("PIL probe failed: %s", e)
        meta = {"width": 0, "height": 0, "format": Path(key).suffix.lstrip("."), "size_kb": size_kb}
    _cache_put(key, meta)
    return meta


def invalidate_metadata_cache(file_path: str) -> None:
    """Drop a single cached entry by absolute path."""
    _metadata_cache.pop(_abs(file_path), None)


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
