from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = Path(os.getenv("AI_MATH_DATA_PATH", str(ROOT_DIR / "data" / "processed" / "questions.json")))
if not QUESTIONS_PATH.is_absolute():
    QUESTIONS_PATH = ROOT_DIR / QUESTIONS_PATH


class QuestionStore:
    def __init__(self) -> None:
        self.questions: list[dict[str, Any]] = []
        self.by_id: dict[str, dict[str, Any]] = {}
        self.loaded_at: float | None = None
        self.reload()

    def reload(self) -> None:
        if not QUESTIONS_PATH.exists():
            self.questions = []
            self.by_id = {}
            return
        with QUESTIONS_PATH.open("r", encoding="utf-8") as handle:
            self.questions = json.load(handle)
        self.by_id = {item["id"]: item for item in self.questions}
        self.loaded_at = QUESTIONS_PATH.stat().st_mtime

    def ensure_fresh(self) -> None:
        if QUESTIONS_PATH.exists() and self.loaded_at != QUESTIONS_PATH.stat().st_mtime:
            self.reload()

    def get(self, question_id: str) -> dict[str, Any] | None:
        self.ensure_fresh()
        return self.by_id.get(question_id)

    def list(self) -> list[dict[str, Any]]:
        self.ensure_fresh()
        return self.questions


question_store = QuestionStore()
