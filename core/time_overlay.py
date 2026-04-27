"""Video timestamp overlay utilities.

`add_timestamp_to_frame` is used for in-process previews on the backend
(unit tests, debugging). The interactive preview in the browser is a
canvas overlay drawn by `static/script.js`.

`burn_timestamp_to_video` produces an exported MP4 with a baked-in
HH:MM:SS overlay using FFmpeg's `drawtext` filter.
"""

from __future__ import annotations

import asyncio
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple


def add_timestamp_to_frame(
    frame,
    timestamp_str: str,
    position: Tuple[int, int] = (10, 30),
    font_scale: float = 1.0,
):
    """Draw `timestamp_str` on top of an OpenCV BGR `frame`. Returns the
    modified frame (operates in place)."""
    import cv2

    cv2.putText(
        frame,
        timestamp_str,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return frame


def check_ffmpeg_available() -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        return True
    except Exception:
        return False


def _select_codec(use_gpu: bool, codec: Optional[str]) -> str:
    if codec:
        return codec
    if use_gpu and platform.system().lower() == "linux":
        return "h264_nvenc"
    return "libx264"


async def burn_timestamp_to_video(
    input_path: str,
    output_path: str,
    start: Optional[float] = None,
    end: Optional[float] = None,
    bitrate: Optional[str] = None,
    codec: Optional[str] = None,
    use_gpu: bool = False,
) -> dict:
    """Run FFmpeg to overlay HH:MM:SS on every frame.

    Returns `{"returncode": int, "stdout": str, "stderr": str, "output": str}`.
    Raises `RuntimeError` if FFmpeg is not available.
    """
    if not check_ffmpeg_available():
        raise RuntimeError("FFmpeg не найден в PATH")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    args: list[str] = ["ffmpeg", "-y"]
    if start is not None:
        args += ["-ss", f"{float(start):.3f}"]
    args += ["-i", input_path]
    if end is not None and start is not None:
        args += ["-t", f"{max(float(end) - float(start), 0):.3f}"]
    elif end is not None:
        args += ["-to", f"{float(end):.3f}"]

    drawtext = (
        "drawtext=text='%{pts\\:hms}':x=10:y=10:fontsize=40:"
        "fontcolor=white:box=1:boxcolor=black@0.7"
    )
    args += ["-vf", drawtext]
    args += ["-c:v", _select_codec(use_gpu, codec)]
    if bitrate:
        args += ["-b:v", str(bitrate)]
    args += ["-c:a", "copy", output_path]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    return {
        "returncode": proc.returncode,
        "stdout": stdout_b.decode("utf-8", errors="replace"),
        "stderr": stderr_b.decode("utf-8", errors="replace"),
        "output": output_path,
    }
