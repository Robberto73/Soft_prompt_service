"""Image annotator: serves the file URL; bbox drawing is delegated to
the frontend canvas + `image_bbox_annotator.save_bbox_annotation`."""

from __future__ import annotations

from typing import Optional

from .base import BaseAnnotator


class ImageAnnotator(BaseAnnotator):
    def __init__(self, file_id: int, session_id: Optional[str] = None):
        super().__init__(file_id)
        self.session_id = session_id

    def load_file(self, file_path: str) -> None:
        self.file_path = file_path

    def get_display_data(self) -> dict:
        return {
            "kind": "image",
            "file_id": self.file_id,
            "url": f"/files/{self.file_id}",
        }

    def save_annotation(
        self, question: str, answer: str, additional: Optional[dict] = None
    ) -> None:
        from core.session_store import save_annotation_to_session

        save_annotation_to_session(
            self.session_id, question, answer, additional or {}
        )
