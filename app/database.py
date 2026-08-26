from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("AI_MATH_DB_PATH", str(ROOT_DIR / "data" / "ai_math.sqlite3")))
if not DB_PATH.is_absolute():
    DB_PATH = ROOT_DIR / DB_PATH
UPLOADS_DIR = ROOT_DIR / "data" / "uploads"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                answer TEXT NOT NULL DEFAULT '',
                correct INTEGER,
                status TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0,
                max_score REAL NOT NULL DEFAULT 0,
                confidence REAL NOT NULL DEFAULT 0,
                error_type TEXT NOT NULL DEFAULT '',
                concepts_json TEXT NOT NULL DEFAULT '[]',
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                hints_used INTEGER NOT NULL DEFAULT 0,
                mode TEXT NOT NULL DEFAULT 'practice',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_attempts_user ON attempts(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_attempts_question ON attempts(question_id);

            CREATE TABLE IF NOT EXISTS simulations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                exam_type TEXT NOT NULL,
                year INTEGER NOT NULL,
                question_ids_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                score REAL,
                max_score REAL NOT NULL,
                duration_seconds INTEGER NOT NULL DEFAULT 10800,
                created_at TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS simulation_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                simulation_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                answer TEXT NOT NULL DEFAULT '',
                correct INTEGER,
                status TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(simulation_id, question_id),
                FOREIGN KEY(simulation_id) REFERENCES simulations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS answer_attachments (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                storage_path TEXT NOT NULL,
                attempt_id INTEGER,
                simulation_id TEXT,
                practice_session_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_answer_attachments_attempt ON answer_attachments(attempt_id);
            CREATE INDEX IF NOT EXISTS idx_answer_attachments_simulation ON answer_attachments(simulation_id, question_id);

            CREATE TABLE IF NOT EXISTS practice_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                exam_type TEXT NOT NULL,
                concept_id TEXT NOT NULL,
                question_type TEXT NOT NULL,
                question_ids_json TEXT NOT NULL,
                requested_count INTEGER NOT NULL DEFAULT 15,
                status TEXT NOT NULL DEFAULT 'active',
                score REAL,
                max_score REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                submitted_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_practice_sessions_user ON practice_sessions(user_id, status, updated_at);

            CREATE TABLE IF NOT EXISTS practice_session_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                answer TEXT NOT NULL DEFAULT '',
                self_grade REAL,
                correct INTEGER,
                status TEXT NOT NULL DEFAULT 'draft',
                score REAL NOT NULL DEFAULT 0,
                max_score REAL NOT NULL DEFAULT 0,
                result_json TEXT,
                attempt_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(session_id, question_id),
                FOREIGN KEY(session_id) REFERENCES practice_sessions(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_practice_session_answers_session ON practice_session_answers(session_id);

            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '未命名笔记',
                concept_id TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                content_html TEXT NOT NULL DEFAULT '',
                content_markdown TEXT NOT NULL DEFAULT '',
                handwriting_data TEXT NOT NULL DEFAULT '',
                mindmap_json TEXT NOT NULL DEFAULT '[]',
                favorite INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_notes_user_updated ON notes(user_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_notes_user_concept ON notes(user_id, concept_id);

            CREATE TABLE IF NOT EXISTS note_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                concept_id TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                content_html TEXT NOT NULL DEFAULT '',
                content_markdown TEXT NOT NULL DEFAULT '',
                handwriting_data TEXT NOT NULL DEFAULT '',
                mindmap_json TEXT NOT NULL DEFAULT '[]',
                favorite INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_note_versions_note ON note_versions(note_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS note_assets (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                storage_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_note_assets_user ON note_assets(user_id, created_at);

            CREATE TABLE IF NOT EXISTS workbench_template_overrides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                concept_id TEXT NOT NULL,
                question_type TEXT NOT NULL,
                overview TEXT NOT NULL DEFAULT '',
                framework_json TEXT NOT NULL DEFAULT '[]',
                mistakes_json TEXT NOT NULL DEFAULT '[]',
                memory_aid TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, concept_id, question_type)
            );

            CREATE TABLE IF NOT EXISTS workbench_template_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                concept_id TEXT NOT NULL,
                question_type TEXT NOT NULL,
                overview TEXT NOT NULL DEFAULT '',
                framework_json TEXT NOT NULL DEFAULT '[]',
                mistakes_json TEXT NOT NULL DEFAULT '[]',
                memory_aid TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workbench_template_versions ON workbench_template_versions(user_id, concept_id, question_type, created_at DESC);
            """
        )
        attachment_columns = {row["name"] for row in connection.execute("PRAGMA table_info(answer_attachments)").fetchall()}
        if "practice_session_id" not in attachment_columns:
            connection.execute("ALTER TABLE answer_attachments ADD COLUMN practice_session_id TEXT")


def set_setting(key: str, value: Any) -> None:
    serialized = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, serialized, utc_now()),
        )


def get_setting(key: str, default: Any = None) -> Any:
    with get_connection() as connection:
        row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    value = row["value"]
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def insert_attempt(payload: dict[str, Any]) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO attempts(
                user_id, question_id, answer, correct, status, score, max_score,
                confidence, error_type, concepts_json, duration_seconds, hints_used,
                mode, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["user_id"],
                payload["question_id"],
                payload.get("answer", ""),
                payload.get("correct"),
                payload["status"],
                payload.get("score", 0),
                payload.get("max_score", 0),
                payload.get("confidence", 0),
                payload.get("error_type", ""),
                json.dumps(payload.get("concepts", []), ensure_ascii=False),
                payload.get("duration_seconds", 0),
                payload.get("hints_used", 0),
                payload.get("mode", "practice"),
                utc_now(),
            ),
        )
        return int(cursor.lastrowid)


def fetch_attempts(user_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM attempts WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["concepts"] = json.loads(item.pop("concepts_json"))
        except (TypeError, json.JSONDecodeError):
            item["concepts"] = []
        result.append(item)
    return result


def create_simulation(payload: dict[str, Any]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO simulations(
                id, user_id, exam_type, year, question_ids_json, status,
                max_score, duration_seconds, created_at
            ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                payload["id"],
                payload["user_id"],
                payload["exam_type"],
                payload["year"],
                json.dumps(payload["question_ids"], ensure_ascii=False),
                payload["max_score"],
                payload.get("duration_seconds", 10800),
                utc_now(),
            ),
        )


def get_simulation(simulation_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM simulations WHERE id = ?", (simulation_id,)).fetchone()
        if row is None:
            return None
        answers = connection.execute(
            "SELECT * FROM simulation_answers WHERE simulation_id = ? ORDER BY id",
            (simulation_id,),
        ).fetchall()
    item = dict(row)
    item["question_ids"] = json.loads(item.pop("question_ids_json"))
    item["answers"] = []
    for answer in answers:
        answer_item = dict(answer)
        answer_item["attachments"] = attachments_for_simulation(simulation_id, answer_item["question_id"])
        item["answers"].append(answer_item)
    return item


def delete_simulation(simulation_id: str) -> bool:
    """Delete an in-progress simulation and its answers."""
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM simulations WHERE id = ? AND status = 'active'",
            (simulation_id,),
        )
    return cursor.rowcount > 0


def upsert_simulation_answer(payload: dict[str, Any]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO simulation_answers(
                simulation_id, question_id, answer, correct, status, score, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(simulation_id, question_id) DO UPDATE SET
                answer=excluded.answer, correct=excluded.correct, status=excluded.status,
                score=excluded.score, created_at=excluded.created_at
            """,
            (
                payload["simulation_id"],
                payload["question_id"],
                payload.get("answer", ""),
                payload.get("correct"),
                payload["status"],
                payload.get("score", 0),
                utc_now(),
            ),
        )


def finish_simulation(simulation_id: str, score: float) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE simulations SET status = 'finished', score = ?, finished_at = ? WHERE id = ?",
            (score, utc_now(), simulation_id),
        )


def create_practice_session(payload: dict[str, Any]) -> None:
    now = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO practice_sessions(
                id, user_id, exam_type, concept_id, question_type, question_ids_json,
                requested_count, status, max_score, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                payload["id"],
                payload["user_id"],
                payload["exam_type"],
                payload["concept_id"],
                payload["question_type"],
                json.dumps(payload["question_ids"], ensure_ascii=False),
                payload.get("requested_count", 15),
                payload["max_score"],
                now,
                now,
            ),
        )


def get_practice_session(session_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM practice_sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        answers = connection.execute(
            "SELECT * FROM practice_session_answers WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    item = dict(row)
    item["question_ids"] = json.loads(item.pop("question_ids_json"))
    item["answers"] = []
    for answer in answers:
        answer_item = dict(answer)
        raw_result = answer_item.pop("result_json", None)
        if raw_result:
            try:
                answer_item["result"] = json.loads(raw_result)
            except (TypeError, json.JSONDecodeError):
                answer_item["result"] = None
        answer_item["attachments"] = attachments_for_practice_session(session_id, answer_item["question_id"])
        item["answers"].append(answer_item)
    return item


def upsert_practice_session_answer(payload: dict[str, Any]) -> None:
    now = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO practice_session_answers(
                session_id, question_id, answer, self_grade, correct, status,
                score, max_score, result_json, attempt_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, question_id) DO UPDATE SET
                answer=excluded.answer, self_grade=excluded.self_grade, correct=excluded.correct,
                status=excluded.status, score=excluded.score, max_score=excluded.max_score,
                result_json=excluded.result_json, attempt_id=excluded.attempt_id,
                updated_at=excluded.updated_at
            """,
            (
                payload["session_id"],
                payload["question_id"],
                payload.get("answer", ""),
                payload.get("self_grade"),
                payload.get("correct"),
                payload.get("status", "draft"),
                payload.get("score", 0),
                payload.get("max_score", 0),
                json.dumps(payload["result"], ensure_ascii=False) if payload.get("result") is not None else None,
                payload.get("attempt_id"),
                now,
                now,
            ),
        )


def finish_practice_session(session_id: str, score: float) -> None:
    now = utc_now()
    with get_connection() as connection:
        connection.execute(
            "UPDATE practice_sessions SET status = 'finished', score = ?, updated_at = ?, submitted_at = ? WHERE id = ?",
            (score, now, now, session_id),
        )


def touch_practice_session(session_id: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE practice_sessions SET updated_at = ? WHERE id = ? AND status = 'active'",
            (utc_now(), session_id),
        )


def create_attachment(payload: dict[str, Any]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO answer_attachments(
                id, user_id, question_id, filename, content_type, size_bytes,
                storage_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["user_id"],
                payload["question_id"],
                payload["filename"],
                payload["content_type"],
                payload["size_bytes"],
                payload["storage_path"],
                utc_now(),
            ),
        )


def link_attachments(
    attachment_ids: list[str], *, user_id: str, question_id: str,
    attempt_id: int | None = None, simulation_id: str | None = None,
    practice_session_id: str | None = None,
) -> None:
    if not attachment_ids:
        return
    with get_connection() as connection:
        placeholders = ",".join("?" for _ in attachment_ids)
        params: list[Any] = [attempt_id, simulation_id, practice_session_id, user_id, question_id, *attachment_ids]
        connection.execute(
            f"""
            UPDATE answer_attachments
            SET attempt_id = ?, simulation_id = ?, practice_session_id = ?
            WHERE user_id = ? AND question_id = ? AND id IN ({placeholders})
            """,
            params,
        )


def _attachment_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    return {
        "id": item["id"],
        "filename": item["filename"],
        "content_type": item["content_type"],
        "size_bytes": item["size_bytes"],
        "url": f"/api/attachments/{item['id']}",
        "created_at": item["created_at"],
    }


def attachments_for_attempt(attempt_id: int) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM answer_attachments WHERE attempt_id = ? ORDER BY created_at",
            (attempt_id,),
        ).fetchall()
    return [_attachment_public(row) for row in rows]


def attachments_for_simulation(simulation_id: str, question_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM answer_attachments WHERE simulation_id = ? AND question_id = ? ORDER BY created_at",
            (simulation_id, question_id),
        ).fetchall()
    return [_attachment_public(row) for row in rows]


def attachments_for_practice_session(session_id: str, question_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM answer_attachments WHERE practice_session_id = ? AND question_id = ? ORDER BY created_at",
            (session_id, question_id),
        ).fetchall()
    return [_attachment_public(row) for row in rows]


def attachment_path(attachment_id: str) -> Path | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT storage_path FROM answer_attachments WHERE id = ?",
            (attachment_id,),
        ).fetchone()
    if row is None:
        return None
    path = (ROOT_DIR / row["storage_path"]).resolve()
    try:
        path.relative_to(UPLOADS_DIR.resolve())
    except ValueError:
        return None
    return path


def _json_or_default(value: Any, default: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _note_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["tags"] = _json_or_default(item.pop("tags_json", "[]"), [])
    item["mindmap"] = _json_or_default(item.pop("mindmap_json", "[]"), [])
    item["favorite"] = bool(item.get("favorite", 0))
    return item


def _note_snapshot_params(item: dict[str, Any], *, note_id: str, user_id: str, created_at: str) -> tuple[Any, ...]:
    return (
        note_id,
        user_id,
        item.get("title", "未命名笔记"),
        item.get("concept_id", ""),
        json.dumps(item.get("tags", []), ensure_ascii=False),
        item.get("content_html", ""),
        item.get("content_markdown", ""),
        item.get("handwriting_data", ""),
        json.dumps(item.get("mindmap", []), ensure_ascii=False),
        int(bool(item.get("favorite", False))),
        created_at,
    )


def create_note(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO notes(
                id, user_id, title, concept_id, tags_json, content_html,
                content_markdown, handwriting_data, mindmap_json, favorite,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _note_snapshot_params(payload, note_id=payload["id"], user_id=payload["user_id"], created_at=now) + (now,),
        )
        connection.execute(
            """
            INSERT INTO note_versions(
                note_id, user_id, title, concept_id, tags_json, content_html,
                content_markdown, handwriting_data, mindmap_json, favorite, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _note_snapshot_params(payload, note_id=payload["id"], user_id=payload["user_id"], created_at=now),
        )
        row = connection.execute("SELECT * FROM notes WHERE id = ?", (payload["id"],)).fetchone()
    return _note_public(row) if row is not None else {}


def get_note(note_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    with get_connection() as connection:
        if user_id is None:
            row = connection.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        else:
            row = connection.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id)).fetchone()
    return _note_public(row) if row is not None else None


def list_notes(
    user_id: str,
    *,
    search: str = "",
    concept_id: str = "",
    favorite_only: bool = False,
) -> list[dict[str, Any]]:
    clauses = ["user_id = ?"]
    params: list[Any] = [user_id]
    if concept_id:
        clauses.append("concept_id = ?")
        params.append(concept_id)
    if favorite_only:
        clauses.append("favorite = 1")
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM notes WHERE {' AND '.join(clauses)} ORDER BY favorite DESC, updated_at DESC",
            params,
        ).fetchall()
    notes = [_note_public(row) for row in rows]
    query = search.strip().lower()
    if not query:
        return notes
    return [
        item for item in notes
        if query in str(item.get("title", "")).lower()
        or query in str(item.get("content_markdown", "")).lower()
        or query in str(item.get("content_html", "")).lower()
        or query in " ".join(str(tag) for tag in item.get("tags", [])).lower()
    ]


def update_note(note_id: str, user_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    now = utc_now()
    with get_connection() as connection:
        current = connection.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id)).fetchone()
        if current is None:
            return None
        current_item = _note_public(current)
        connection.execute(
            """
            INSERT INTO note_versions(
                note_id, user_id, title, concept_id, tags_json, content_html,
                content_markdown, handwriting_data, mindmap_json, favorite, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _note_snapshot_params(current_item, note_id=note_id, user_id=user_id, created_at=now),
        )
        connection.execute(
            """
            UPDATE notes SET title = ?, concept_id = ?, tags_json = ?, content_html = ?,
                content_markdown = ?, handwriting_data = ?, mindmap_json = ?,
                favorite = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                payload.get("title", "未命名笔记"),
                payload.get("concept_id", ""),
                json.dumps(payload.get("tags", []), ensure_ascii=False),
                payload.get("content_html", ""),
                payload.get("content_markdown", ""),
                payload.get("handwriting_data", ""),
                json.dumps(payload.get("mindmap", []), ensure_ascii=False),
                int(bool(payload.get("favorite", False))),
                now,
                note_id,
                user_id,
            ),
        )
        row = connection.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id)).fetchone()
    return _note_public(row) if row is not None else None


def delete_note(note_id: str, user_id: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    return cursor.rowcount > 0


def list_note_versions(note_id: str, user_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM note_versions WHERE note_id = ? AND user_id = ? ORDER BY created_at DESC",
            (note_id, user_id),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["tags"] = _json_or_default(item.pop("tags_json", "[]"), [])
        item["mindmap"] = _json_or_default(item.pop("mindmap_json", "[]"), [])
        item["favorite"] = bool(item.get("favorite", 0))
        result.append(item)
    return result


def restore_note_version(note_id: str, version_id: int, user_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM note_versions WHERE id = ? AND note_id = ? AND user_id = ?",
            (version_id, note_id, user_id),
        ).fetchone()
    if row is None:
        return None
    item = dict(row)
    return update_note(
        note_id,
        user_id,
        {
            "title": item.get("title", "未命名笔记"),
            "concept_id": item.get("concept_id", ""),
            "tags": _json_or_default(item.get("tags_json", "[]"), []),
            "content_html": item.get("content_html", ""),
            "content_markdown": item.get("content_markdown", ""),
            "handwriting_data": item.get("handwriting_data", ""),
            "mindmap": _json_or_default(item.get("mindmap_json", "[]"), []),
            "favorite": bool(item.get("favorite", 0)),
        },
    )


def create_note_asset(payload: dict[str, Any]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO note_assets(id, user_id, filename, content_type, size_bytes, storage_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["user_id"],
                payload["filename"],
                payload["content_type"],
                payload["size_bytes"],
                payload["storage_path"],
                utc_now(),
            ),
        )


def note_asset_path(asset_id: str, user_id: str | None = None) -> Path | None:
    with get_connection() as connection:
        if user_id is None:
            row = connection.execute("SELECT storage_path FROM note_assets WHERE id = ?", (asset_id,)).fetchone()
        else:
            row = connection.execute("SELECT storage_path FROM note_assets WHERE id = ? AND user_id = ?", (asset_id, user_id)).fetchone()
    if row is None:
        return None
    path = (ROOT_DIR / row["storage_path"]).resolve()
    try:
        path.relative_to(UPLOADS_DIR.resolve())
    except ValueError:
        return None
    return path


def _template_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["framework"] = _json_or_default(item.pop("framework_json", "[]"), [])
    item["mistakes"] = _json_or_default(item.pop("mistakes_json", "[]"), [])
    return item


def get_template_override(user_id: str, concept_id: str, question_type: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM workbench_template_overrides WHERE user_id = ? AND concept_id = ? AND question_type = ?",
            (user_id, concept_id, question_type),
        ).fetchone()
    return _template_public(row) if row is not None else None


def list_template_overrides(user_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM workbench_template_overrides WHERE user_id = ? ORDER BY concept_id, question_type",
            (user_id,),
        ).fetchall()
    return [_template_public(row) for row in rows]


def upsert_template_override(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    with get_connection() as connection:
        current = connection.execute(
            "SELECT * FROM workbench_template_overrides WHERE user_id = ? AND concept_id = ? AND question_type = ?",
            (payload["user_id"], payload["concept_id"], payload["question_type"]),
        ).fetchone()
        if current is not None:
            current_item = _template_public(current)
            connection.execute(
                """
                INSERT INTO workbench_template_versions(
                    user_id, concept_id, question_type, overview, framework_json,
                    mistakes_json, memory_aid, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    current_item["user_id"], current_item["concept_id"], current_item["question_type"],
                    current_item.get("overview", ""), json.dumps(current_item.get("framework", []), ensure_ascii=False),
                    json.dumps(current_item.get("mistakes", []), ensure_ascii=False), current_item.get("memory_aid", ""), now,
                ),
            )
        connection.execute(
            """
            INSERT INTO workbench_template_overrides(
                user_id, concept_id, question_type, overview, framework_json,
                mistakes_json, memory_aid, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, concept_id, question_type) DO UPDATE SET
                overview = excluded.overview,
                framework_json = excluded.framework_json,
                mistakes_json = excluded.mistakes_json,
                memory_aid = excluded.memory_aid,
                updated_at = excluded.updated_at
            """,
            (
                payload["user_id"], payload["concept_id"], payload["question_type"], payload.get("overview", ""),
                json.dumps(payload.get("framework", []), ensure_ascii=False), json.dumps(payload.get("mistakes", []), ensure_ascii=False),
                payload.get("memory_aid", ""), now,
            ),
        )
        row = connection.execute(
            "SELECT * FROM workbench_template_overrides WHERE user_id = ? AND concept_id = ? AND question_type = ?",
            (payload["user_id"], payload["concept_id"], payload["question_type"]),
        ).fetchone()
    return _template_public(row) if row is not None else {}


def list_template_versions(user_id: str, concept_id: str, question_type: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM workbench_template_versions
            WHERE user_id = ? AND concept_id = ? AND question_type = ?
            ORDER BY created_at DESC
            """,
            (user_id, concept_id, question_type),
        ).fetchall()
    return [_template_public(row) for row in rows]
