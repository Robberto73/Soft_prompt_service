"""Text annotator: returns full text content for monospaced display."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import BaseAnnotator


class TextAnnotator(BaseAnnotator):
    def __init__(self, file_id: int, session_id: Optional[str] = None):
        super().__init__(file_id)
        self.session_id = session_id
        self._content: str = ""

    def load_file(self, file_path: str) -> None:
        self.file_path = file_path
        self._content = Path(file_path).read_text(encoding="utf-8", errors="replace")

    def get_display_data(self) -> dict:
        return {
            "kind": "text",
            "file_id": self.file_id,
            "content": self._content,
        }

    def save_annotation(
        self, question: str, answer: str, additional: Optional[dict] = None
    ) -> None:
        from core.session_store import save_annotation_to_session

        save_annotation_to_session(
            self.session_id, question, answer, additional or {}
        )
