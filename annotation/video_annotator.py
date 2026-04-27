"""Video annotator: streams the file via /files/{file_id}, attaches a
`timestamp` to each annotation."""

from __future__ import annotations

from typing import Optional

from .base import BaseAnnotator


class VideoAnnotator(BaseAnnotator):
    def __init__(self, file_id: int, session_id: Optional[str] = None):
        super().__init__(file_id)
        self.session_id = session_id

    def load_file(self, file_path: str) -> None:
        self.file_path = file_path

    def get_display_data(self) -> dict:
        return {
            "kind": "video",
            "file_id": self.file_id,
            "url": f"/files/{self.file_id}",
        }

    def save_annotation(
        self, question: str, answer: str, additional: Optional[dict] = None
    ) -> None:
        from core.session_store import save_annotation_to_session

        extra = dict(additional or {})
        if "timestamp" not in extra:
            extra["timestamp"] = 0.0
        save_annotation_to_session(
            self.session_id, question, answer, extra
        )
