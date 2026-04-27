"""Abstract base annotator."""

from abc import ABC, abstractmethod
from typing import Optional


class BaseAnnotator(ABC):
    def __init__(self, file_id: int):
        self.file_id = file_id
        self.file_path: Optional[str] = None

    @abstractmethod
    def load_file(self, file_path: str) -> None: ...

    @abstractmethod
    def get_display_data(self) -> dict: ...

    @abstractmethod
    def save_annotation(
        self, question: str, answer: str, additional: Optional[dict] = None
    ) -> None: ...
