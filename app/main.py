from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.database import (
    UPLOADS_DIR,
    attachment_path,
    attachments_for_attempt,
    create_attachment,
    create_note,
    create_note_asset,
    delete_simulation,
    create_practice_session,
    create_simulation,
    delete_note,
    fetch_attempts,
    finish_practice_session,
    finish_simulation,
    get_note,
    get_simulation,
    get_practice_session,
    get_template_override,
    init_db,
    insert_attempt,
    list_note_versions,
    list_notes,
    list_template_overrides,
    list_template_versions,
    link_attachments,
    note_asset_path,
    restore_note_version,
    touch_practice_session,
    update_note,
    upsert_template_override,
    upsert_practice_session_answer,
    upsert_simulation_answer,
)
from app.services.content import question_store
from app.services.concepts import concept_descriptor
from app.services.grading import grade_question
from app.services.learner import (
    CONCEPT_META,
    forecast_score,
    learning_analytics,
    difficulty_descriptor,
    progress_summary,
    randomized_practice_questions,
    recommended_questions,
    study_blocks,
)
from app.services.llm import LLMError, fetch_models, public_settings, save_settings, tutor_response
from app.services.server import ServerSettingsError, save_server_settings, server_settings
from app.services.workbench import (
    QUESTION_TYPES,
    build_workbench_template,
    question_type_catalog,
    workbench_catalog,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT_DIR / "app" / "static"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Math · 考研数学学练系统", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class AttemptRequest(BaseModel):
    user_id: str = "local-user"
    answer: str = ""
    self_grade: float | None = Field(default=None, ge=0, le=1)
    duration_seconds: int = Field(default=0, ge=0, le=86400)
    hints_used: int = Field(default=0, ge=0, le=100)
    error_type: str = ""
    mode: str = "practice"
    attachment_ids: list[str] = Field(default_factory=list)


class SimulationCreateRequest(BaseModel):
    user_id: str = "local-user"
    exam_type: str = "数学二"
    year: int | None = None
    duration_minutes: int = Field(default=180, ge=1, le=600)


class SimulationSubmitRequest(BaseModel):
    user_id: str = "local-user"
    answers: dict[str, str] = Field(default_factory=dict)
    self_grades: dict[str, float] = Field(default_factory=dict)
    attachment_ids: dict[str, list[str]] = Field(default_factory=dict)


class PracticeSessionCreateRequest(BaseModel):
    user_id: str = "local-user"
    exam_type: str = "数学二"
    concept_id: str
    question_type: str
    count: int = Field(default=15, ge=1, le=15)


class PracticeSessionDataRequest(BaseModel):
    user_id: str = "local-user"
    answers: dict[str, str] = Field(default_factory=dict)
    self_grades: dict[str, float] = Field(default_factory=dict)
    attachment_ids: dict[str, list[str]] = Field(default_factory=dict)


class ModelSettingsRequest(BaseModel):
    base_url: str
    model: str = ""
    api_key: str | None = None
    clear_api_key: bool = False


class ModelFetchRequest(BaseModel):
    base_url: str | None = None
    api_key: str | None = None


class ServerSettingsRequest(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    public_url: str = ""


class TutorRequest(BaseModel):
    user_id: str = "local-user"
    answer: str = ""
    request: str = "分析我的错误"


class NoteRequest(BaseModel):
    user_id: str = "local-user"
    title: str = Field(default="未命名笔记", max_length=200)
    concept_id: str = Field(default="", max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=30)
    content_html: str = Field(default="", max_length=300000)
    content_markdown: str = Field(default="", max_length=300000)
    handwriting_data: str = Field(default="", max_length=12_000_000)
    mindmap: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    favorite: bool = False


class TemplateUpdateRequest(BaseModel):
    user_id: str = "local-user"
    overview: str = Field(default="", max_length=5000)
    framework: list[str] = Field(default_factory=list, max_length=20)
    mistakes: list[str] = Field(default_factory=list, max_length=20)
    memory_aid: str = Field(default="", max_length=500)


class WorkbenchImportRequest(BaseModel):
    user_id: str = "local-user"
    notes: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    template_overrides: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


def _question_public(question: dict[str, Any], reveal: bool = False) -> dict[str, Any]:
    result = {key: value for key, value in question.items() if key not in {"raw_markdown", "answer_markdown", "solution_markdown"}}
    difficulty_band, difficulty_label = difficulty_descriptor(question.get("year"))
    result["difficulty_band"] = difficulty_band
    result["difficulty_label"] = difficulty_label
    result["answer_available"] = bool(question.get("has_answer"))
    result["solution_available"] = bool(question.get("has_solution"))
    result["concept_labels"] = [concept_descriptor(item) for item in question.get("concept_ids", [])]
    result["has_out_of_syllabus_concepts"] = any(item["scope"] == "out-of-syllabus" for item in result["concept_labels"])
    if reveal:
        result["answer_markdown"] = question.get("answer_markdown", "")
        result["solution_markdown"] = question.get("solution_markdown", "")
    return result


def _question_or_404(question_id: str) -> dict[str, Any]:
    question = question_store.get(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="题目不存在。")
    return question


def _attempt_response(question: dict[str, Any], result: dict[str, Any], attempt_id: int) -> dict[str, Any]:
    return {
        "attempt_id": attempt_id,
        "question_id": question["id"],
        "result": result,
        "answer_markdown": question.get("answer_markdown", ""),
        "solution_markdown": question.get("solution_markdown", ""),
        "has_solution": bool(question.get("has_solution")),
        "source_path": question.get("source_path", ""),
        "attachments": attachments_for_attempt(attempt_id),
    }


def _sanitize_note_html(value: str) -> str:
    """Keep the editor useful while removing executable or embedded content."""
    html = str(value or "")
    html = re.sub(r"<script\b[\s\S]*?</script\s*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<(iframe|object|embed|form)\b[\s\S]*?</\1\s*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\s+on[a-z0-9_-]+\s*=\s*(\"[^\"]*\"|'[^']*')", "", html, flags=re.IGNORECASE)
    html = re.sub(r"(href|src)\s*=\s*(['\"])\s*javascript:[^'\"]*\2", r"\1=\2\2", html, flags=re.IGNORECASE)
    return html[:300000]


def _normalize_note_payload(payload: NoteRequest, *, user_id: str, note_id: str | None = None) -> dict[str, Any]:
    tags: list[str] = []
    for raw_tag in payload.tags:
        tag = str(raw_tag).strip()[:40]
        if tag and tag not in tags:
            tags.append(tag)
    mindmap: list[dict[str, str]] = []
    for index, raw_node in enumerate(payload.mindmap[:50]):
        label = str(raw_node.get("label", "")).strip()[:200]
        if not label:
            continue
        mindmap.append({
            "id": str(raw_node.get("id", f"node-{index + 1}"))[:80],
            "label": label,
            "parent": str(raw_node.get("parent", "root"))[:80],
        })
    item = {
        "id": note_id or uuid.uuid4().hex,
        "user_id": user_id.strip() or "local-user",
        "title": payload.title.strip() or "未命名笔记",
        "concept_id": payload.concept_id.strip(),
        "tags": tags,
        "content_html": _sanitize_note_html(payload.content_html),
        "content_markdown": payload.content_markdown[:300000],
        "handwriting_data": payload.handwriting_data[:12_000_000],
        "mindmap": mindmap,
        "favorite": bool(payload.favorite),
    }
    return item


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    questions = question_store.list()
    return {"status": "ok", "question_count": len(questions), "data_ready": bool(questions)}


@app.post("/api/uploads/answer-image")
async def upload_answer_image(
    file: UploadFile = File(...),
    user_id: str = Form(default="local-user"),
    question_id: str = Form(...),
) -> dict[str, Any]:
    content_type = (file.content_type or "").lower()
    if content_type not in IMAGE_SUFFIXES:
        raise HTTPException(status_code=415, detail="只支持 PNG、JPG、WebP 或 GIF 图片。")
    content = await file.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="图片不能超过 8 MB。")
    attachment_id = uuid.uuid4().hex
    relative_path = Path("data") / "uploads" / f"{attachment_id}{IMAGE_SUFFIXES[content_type]}"
    absolute_path = ROOT_DIR / relative_path
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(content)
    create_attachment(
        {
            "id": attachment_id,
            "user_id": user_id.strip() or "local-user",
            "question_id": question_id,
            "filename": file.filename or "answer-image",
            "content_type": content_type,
            "size_bytes": len(content),
            "storage_path": relative_path.as_posix(),
        }
    )
    return {
        "attachment_id": attachment_id,
        "filename": file.filename or "answer-image",
        "content_type": content_type,
        "size_bytes": len(content),
    }


@app.get("/api/attachments/{attachment_id}")
def get_attachment(attachment_id: str) -> FileResponse:
    path = attachment_path(attachment_id)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="图片不存在。")
    return FileResponse(path)


@app.get("/api/workbench")
def get_workbench_catalog(
    concept_id: str = Query(default=""),
    question_type: str = Query(default=""),
    user_id: str = Query(default="local-user"),
) -> dict[str, Any]:
    questions = question_store.list()
    if concept_id or question_type:
        if not concept_id or not question_type:
            raise HTTPException(status_code=400, detail="选择知识块和题型后才能读取模板。")
        override = get_template_override(user_id.strip() or "local-user", concept_id, question_type)
        try:
            template = build_workbench_template(questions, concept_id, question_type, override)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"template": template}
    return {
        "concepts": workbench_catalog(questions),
        "question_types": question_type_catalog(),
        "total_templates": len(workbench_catalog(questions)) * len(QUESTION_TYPES),
    }


@app.put("/api/workbench/templates/{concept_id}/{question_type}")
def save_workbench_template(concept_id: str, question_type: str, payload: TemplateUpdateRequest) -> dict[str, Any]:
    if concept_id not in CONCEPT_META or question_type not in QUESTION_TYPES:
        raise HTTPException(status_code=400, detail="无效的知识块或题型。")
    saved = upsert_template_override({
        "user_id": payload.user_id.strip() or "local-user",
        "concept_id": concept_id,
        "question_type": question_type,
        "overview": payload.overview.strip(),
        "framework": [item.strip() for item in payload.framework if item.strip()],
        "mistakes": [item.strip() for item in payload.mistakes if item.strip()],
        "memory_aid": payload.memory_aid.strip(),
    })
    return {"template": build_workbench_template(question_store.list(), concept_id, question_type, saved)}


@app.get("/api/workbench/templates/{concept_id}/{question_type}/versions")
def get_workbench_template_versions(concept_id: str, question_type: str, user_id: str = "local-user") -> dict[str, Any]:
    if concept_id not in CONCEPT_META or question_type not in QUESTION_TYPES:
        raise HTTPException(status_code=400, detail="无效的知识块或题型。")
    return {"items": list_template_versions(user_id.strip() or "local-user", concept_id, question_type)}


@app.get("/api/workbench/notes")
def get_workbench_notes(
    user_id: str = "local-user",
    search: str = "",
    concept_id: str = "",
    favorite: bool = False,
) -> dict[str, Any]:
    return {"items": list_notes(user_id.strip() or "local-user", search=search, concept_id=concept_id, favorite_only=favorite)}


@app.post("/api/workbench/notes")
def create_workbench_note(payload: NoteRequest) -> dict[str, Any]:
    item = _normalize_note_payload(payload, user_id=payload.user_id)
    return {"note": create_note(item)}


@app.get("/api/workbench/notes/{note_id}")
def get_workbench_note(note_id: str, user_id: str = "local-user") -> dict[str, Any]:
    note = get_note(note_id, user_id.strip() or "local-user")
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在。")
    return {"note": note}


@app.put("/api/workbench/notes/{note_id}")
def update_workbench_note(note_id: str, payload: NoteRequest) -> dict[str, Any]:
    user_id = payload.user_id.strip() or "local-user"
    if get_note(note_id, user_id) is None:
        raise HTTPException(status_code=404, detail="笔记不存在。")
    item = _normalize_note_payload(payload, user_id=user_id, note_id=note_id)
    saved = update_note(note_id, user_id, item)
    if saved is None:
        raise HTTPException(status_code=404, detail="笔记不存在。")
    return {"note": saved}


@app.delete("/api/workbench/notes/{note_id}")
def delete_workbench_note(note_id: str, user_id: str = "local-user") -> dict[str, Any]:
    if not delete_note(note_id, user_id.strip() or "local-user"):
        raise HTTPException(status_code=404, detail="笔记不存在。")
    return {"status": "deleted", "note_id": note_id}


@app.get("/api/workbench/notes/{note_id}/versions")
def get_workbench_note_versions(note_id: str, user_id: str = "local-user") -> dict[str, Any]:
    normalized_user_id = user_id.strip() or "local-user"
    if get_note(note_id, normalized_user_id) is None:
        raise HTTPException(status_code=404, detail="笔记不存在。")
    return {"items": list_note_versions(note_id, normalized_user_id)}


@app.post("/api/workbench/notes/{note_id}/restore/{version_id}")
def restore_workbench_note_version(note_id: str, version_id: int, user_id: str = "local-user") -> dict[str, Any]:
    note = restore_note_version(note_id, version_id, user_id.strip() or "local-user")
    if note is None:
        raise HTTPException(status_code=404, detail="笔记版本不存在。")
    return {"note": note}


@app.post("/api/workbench/notes/assets")
async def upload_workbench_note_asset(
    file: UploadFile = File(...),
    user_id: str = Form(default="local-user"),
) -> dict[str, Any]:
    content_type = (file.content_type or "").lower()
    if content_type not in IMAGE_SUFFIXES:
        raise HTTPException(status_code=415, detail="只支持 PNG、JPG、WebP 或 GIF 图片。")
    content = await file.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="图片不能超过 8 MB。")
    asset_id = uuid.uuid4().hex
    relative_path = Path("data") / "uploads" / "notes" / f"{asset_id}{IMAGE_SUFFIXES[content_type]}"
    absolute_path = ROOT_DIR / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(content)
    create_note_asset({
        "id": asset_id,
        "user_id": user_id.strip() or "local-user",
        "filename": file.filename or "note-image",
        "content_type": content_type,
        "size_bytes": len(content),
        "storage_path": relative_path.as_posix(),
    })
    return {
        "asset_id": asset_id,
        "filename": file.filename or "note-image",
        "content_type": content_type,
        "size_bytes": len(content),
        "url": f"/api/workbench/note-assets/{asset_id}",
    }


@app.get("/api/workbench/note-assets/{asset_id}")
def get_workbench_note_asset(asset_id: str) -> FileResponse:
    path = note_asset_path(asset_id)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="笔记图片不存在。")
    return FileResponse(path)


@app.get("/api/workbench/export")
def export_workbench(user_id: str = "local-user") -> dict[str, Any]:
    normalized_user_id = user_id.strip() or "local-user"
    notes = list_notes(normalized_user_id)
    versions = {note["id"]: list_note_versions(note["id"], normalized_user_id) for note in notes}
    return {
        "format": "ai-math-workbench",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user_id": normalized_user_id,
        "notes": notes,
        "note_versions": versions,
        "template_overrides": list_template_overrides(normalized_user_id),
    }


@app.post("/api/workbench/import")
def import_workbench(payload: WorkbenchImportRequest) -> dict[str, Any]:
    user_id = payload.user_id.strip() or "local-user"
    imported_notes = 0
    imported_templates = 0
    for raw_note in payload.notes:
        try:
            request = NoteRequest(**raw_note)
        except Exception:
            continue
        note_id = str(raw_note.get("id") or uuid.uuid4().hex)
        item = _normalize_note_payload(request, user_id=user_id, note_id=note_id)
        if get_note(note_id, user_id) is None:
            create_note(item)
        else:
            update_note(note_id, user_id, item)
        imported_notes += 1
    for raw_template in payload.template_overrides:
        concept_id = str(raw_template.get("concept_id", ""))
        question_type = str(raw_template.get("question_type", ""))
        if concept_id not in CONCEPT_META or question_type not in QUESTION_TYPES:
            continue
        try:
            request = TemplateUpdateRequest(**raw_template)
        except Exception:
            continue
        upsert_template_override({
            "user_id": user_id,
            "concept_id": concept_id,
            "question_type": question_type,
            "overview": request.overview.strip(),
            "framework": [item.strip() for item in request.framework if item.strip()],
            "mistakes": [item.strip() for item in request.mistakes if item.strip()],
            "memory_aid": request.memory_aid.strip(),
        })
        imported_templates += 1
    return {"imported_notes": imported_notes, "imported_templates": imported_templates}


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    questions = question_store.list()
    by_exam: dict[str, dict[str, Any]] = {}
    for question in questions:
        bucket = by_exam.setdefault(question["exam_type"], {"questions": 0, "years": [], "with_answer": 0, "with_solution": 0})
        bucket["questions"] += 1
        bucket["with_answer"] += int(question.get("has_answer", False))
        bucket["with_solution"] += int(question.get("has_solution", False))
        bucket["years"].append(question["year"])
    for bucket in by_exam.values():
        bucket["years"] = sorted(set(bucket["years"]))
    return {
        "total_questions": len(questions),
        "real_source": "荒原之梦考研数学 GitHub 公开刷题版（当前导入数学二）",
        "by_exam": by_exam,
        "source_notice": "题库保留原始 Markdown/LaTeX、答案、解析和来源路径；公开发布或商业化前请取得作者书面授权。",
    }


@app.get("/api/exams")
def exams() -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for question in question_store.list():
        grouped.setdefault((question["exam_type"], int(question["year"])), []).append(question)
    return [
        {
            "exam_type": exam_type,
            "year": year,
            "question_count": len(items),
            "max_score": sum(float(item.get("points", 0)) for item in items),
        }
        for (exam_type, year), items in sorted(grouped.items(), key=lambda item: (item[0][0], -item[0][1]))
    ]


@app.get("/api/concepts")
def concepts() -> list[dict[str, str]]:
    return [
        {
            "id": key,
            "name": value[0],
            "subject": value[1],
            "scope": "math2",
            "scope_label": "数学二大纲",
        }
        for key, value in CONCEPT_META.items()
    ]


@app.get("/api/questions")
def list_questions(
    exam_type: str | None = None,
    year: int | None = None,
    question_type: str | None = None,
    concept_id: str | None = None,
    scope: str | None = None,
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = []
    for question in question_store.list():
        if exam_type and question.get("exam_type") != exam_type:
            continue
        if year and question.get("year") != year:
            continue
        if question_type and question.get("question_type") != question_type:
            continue
        if concept_id and concept_id not in question.get("concept_ids", []):
            continue
        if scope in {"math2", "out-of-syllabus"}:
            question_scopes = {concept_descriptor(item)["scope"] for item in question.get("concept_ids", [])}
            if scope not in question_scopes:
                continue
        items.append(_question_public(question))
    items.sort(key=lambda item: (item.get("year", 0), item.get("number", 0), item.get("id", "")), reverse=True)
    return {"items": items[offset : offset + limit], "total": len(items), "offset": offset, "limit": limit}


@app.get("/api/questions/{question_id}")
def get_question(question_id: str, reveal: bool = False) -> dict[str, Any]:
    return _question_public(_question_or_404(question_id), reveal=reveal)


@app.post("/api/questions/{question_id}/attempts")
def create_attempt(question_id: str, payload: AttemptRequest) -> dict[str, Any]:
    question = _question_or_404(question_id)
    result = grade_question(question, payload.answer, payload.self_grade)
    error_type = payload.error_type.strip() or result.get("error_type", "")
    attempt_id = insert_attempt(
        {
            "user_id": payload.user_id.strip() or "local-user",
            "question_id": question_id,
            "answer": payload.answer,
            "correct": result.get("correct"),
            "status": result["status"],
            "score": result["score"],
            "max_score": result["max_score"],
            "confidence": result["confidence"],
            "error_type": error_type,
            "concepts": question.get("concept_ids", []),
            "duration_seconds": payload.duration_seconds,
            "hints_used": payload.hints_used,
            "mode": payload.mode,
        }
    )
    link_attachments(
        payload.attachment_ids,
        user_id=payload.user_id.strip() or "local-user",
        question_id=question_id,
        attempt_id=attempt_id,
    )
    result["error_type"] = error_type
    return _attempt_response(question, result, attempt_id)


@app.get("/api/progress")
def progress(user_id: str = "local-user") -> dict[str, Any]:
    return progress_summary(fetch_attempts(user_id), question_store.list())


@app.get("/api/analytics")
def analytics(user_id: str = "local-user", exam_type: str = "数学二") -> dict[str, Any]:
    return learning_analytics(question_store.list(), fetch_attempts(user_id), exam_type=exam_type)


@app.get("/api/practice/next")
def practice_next(
    user_id: str = "local-user",
    exam_type: str = "数学二",
    concept_id: str | None = None,
    limit: int = Query(default=8, ge=1, le=30),
) -> dict[str, Any]:
    attempts = fetch_attempts(user_id)
    items = recommended_questions(question_store.list(), attempts, exam_type=exam_type, concept_id=concept_id, limit=limit)
    return {"items": [_question_public(item) for item in items], "concept_id": concept_id, "exam_type": exam_type}


@app.get("/api/study/blocks")
def study_block_endpoint(user_id: str = "local-user", limit: int = Query(default=6, ge=1, le=12)) -> dict[str, Any]:
    blocks = study_blocks(question_store.list(), fetch_attempts(user_id), limit=limit)
    return {
        "blocks": [
            {
                **block,
                "questions": [_question_public(item) for item in block["questions"]],
            }
            for block in blocks
        ]
    }


def practice_session_view(session: dict[str, Any] | None, *, reveal: bool = False) -> dict[str, Any]:
    if session is None:
        raise HTTPException(status_code=404, detail="训练会话不存在。")
    answer_map = {answer["question_id"]: answer for answer in session.get("answers", [])}
    questions = []
    for question_id in session["question_ids"]:
        question = question_store.get(question_id)
        if question is None:
            continue
        item = _question_public(question, reveal=reveal)
        answer = answer_map.get(question_id)
        if answer:
            item["answer_state"] = {
                "answer": answer.get("answer", ""),
                "self_grade": answer.get("self_grade"),
                "correct": answer.get("correct"),
                "status": answer.get("status", "draft"),
                "score": answer.get("score", 0),
                "max_score": answer.get("max_score", question.get("points", 0)),
                "attempt_id": answer.get("attempt_id"),
                "result": answer.get("result"),
                "attachments": answer.get("attachments", []),
            }
        questions.append(item)
    answered_count = sum(1 for answer in answer_map.values() if (answer.get("answer") or "").strip() or answer.get("self_grade") is not None)
    return {
        **{key: value for key, value in session.items() if key not in {"question_ids", "answers"}},
        "questions": questions,
        "question_count": len(questions),
        "answered_count": answered_count,
    }


def _practice_session_or_404(session_id: str, user_id: str) -> dict[str, Any]:
    session = get_practice_session(session_id)
    if session is None or session.get("user_id") != (user_id.strip() or "local-user"):
        raise HTTPException(status_code=404, detail="训练会话不存在。")
    return session


def _validate_practice_payload(session: dict[str, Any], payload: PracticeSessionDataRequest) -> None:
    allowed = set(session["question_ids"])
    submitted_ids = set(payload.answers) | set(payload.self_grades) | set(payload.attachment_ids)
    unknown = submitted_ids - allowed
    if unknown:
        raise HTTPException(status_code=400, detail="提交中包含不属于本训练会话的题目。")


@app.post("/api/practice/sessions")
def create_practice_session_endpoint(payload: PracticeSessionCreateRequest) -> dict[str, Any]:
    if payload.question_type not in {"choice", "fill", "solution"}:
        raise HTTPException(status_code=400, detail="不支持的题型。")
    user_id = payload.user_id.strip() or "local-user"
    attempts = fetch_attempts(user_id)
    selected = randomized_practice_questions(
        question_store.list(), attempts,
        exam_type=payload.exam_type,
        concept_id=payload.concept_id,
        question_type=payload.question_type,
        limit=payload.count,
    )
    if not selected:
        raise HTTPException(status_code=404, detail="该知识块暂时没有对应题型的真实题目。")
    session_id = uuid.uuid4().hex
    create_practice_session(
        {
            "id": session_id,
            "user_id": user_id,
            "exam_type": payload.exam_type,
            "concept_id": payload.concept_id,
            "question_type": payload.question_type,
            "question_ids": [question["id"] for question in selected],
            "requested_count": payload.count,
            "max_score": sum(float(question.get("points", 0)) for question in selected),
        }
    )
    return practice_session_view(get_practice_session(session_id))


@app.get("/api/practice/sessions/{session_id}")
def get_practice_session_endpoint(session_id: str, user_id: str = "local-user") -> dict[str, Any]:
    session = _practice_session_or_404(session_id, user_id)
    return practice_session_view(session, reveal=session.get("status") == "finished")


@app.put("/api/practice/sessions/{session_id}")
def save_practice_session_endpoint(session_id: str, payload: PracticeSessionDataRequest) -> dict[str, Any]:
    session = _practice_session_or_404(session_id, payload.user_id)
    if session.get("status") == "finished":
        return practice_session_view(session, reveal=True)
    _validate_practice_payload(session, payload)
    for question_id in set(payload.answers) | set(payload.self_grades) | set(payload.attachment_ids):
        question = _question_or_404(question_id)
        upsert_practice_session_answer(
            {
                "session_id": session_id,
                "question_id": question_id,
                "answer": payload.answers.get(question_id, ""),
                "self_grade": payload.self_grades.get(question_id),
                "status": "draft",
                "max_score": question.get("points", 0),
            }
        )
        link_attachments(
            payload.attachment_ids.get(question_id, []),
            user_id=session["user_id"],
            question_id=question_id,
            practice_session_id=session_id,
        )
    touch_practice_session(session_id)
    return practice_session_view(get_practice_session(session_id))


@app.post("/api/practice/sessions/{session_id}/submit")
def submit_practice_session_endpoint(session_id: str, payload: PracticeSessionDataRequest) -> dict[str, Any]:
    session = _practice_session_or_404(session_id, payload.user_id)
    if session.get("status") == "finished":
        return practice_session_view(session, reveal=True)
    _validate_practice_payload(session, payload)
    total = 0.0
    for question_id in session["question_ids"]:
        question = _question_or_404(question_id)
        answer = payload.answers.get(question_id, "")
        self_grade = payload.self_grades.get(question_id)
        result = grade_question(question, answer, self_grade)
        total += float(result["score"])
        attempt_id = insert_attempt(
            {
                "user_id": session["user_id"],
                "question_id": question_id,
                "answer": answer,
                "correct": result.get("correct"),
                "status": result["status"],
                "score": result["score"],
                "max_score": result["max_score"],
                "confidence": result["confidence"],
                "error_type": result.get("error_type", ""),
                "concepts": question.get("concept_ids", []),
                "duration_seconds": 0,
                "hints_used": 0,
                "mode": "practice-session",
            }
        )
        upsert_practice_session_answer(
            {
                "session_id": session_id,
                "question_id": question_id,
                "answer": answer,
                "self_grade": self_grade,
                "correct": result.get("correct"),
                "status": result["status"],
                "score": result["score"],
                "max_score": result["max_score"],
                "result": result,
                "attempt_id": attempt_id,
            }
        )
        link_attachments(
            payload.attachment_ids.get(question_id, []),
            user_id=session["user_id"],
            question_id=question_id,
            attempt_id=attempt_id,
            practice_session_id=session_id,
        )
    finish_practice_session(session_id, total)
    return practice_session_view(get_practice_session(session_id), reveal=True)


@app.get("/api/forecast")
def score_forecast(user_id: str = "local-user", exam_type: str = "数学二") -> dict[str, Any]:
    return forecast_score(question_store.list(), fetch_attempts(user_id), exam_type=exam_type)


@app.post("/api/simulations")
def create_simulation_endpoint(payload: SimulationCreateRequest) -> dict[str, Any]:
    pool = [question for question in question_store.list() if question.get("exam_type") == payload.exam_type]
    if not pool:
        raise HTTPException(status_code=404, detail="当前题库没有该考试类型。")
    year = payload.year or max(int(question["year"]) for question in pool)
    paper = [question for question in pool if int(question["year"]) == year]
    if not paper:
        raise HTTPException(status_code=404, detail=f"题库中没有 {payload.exam_type} {year} 年试卷。")
    paper.sort(key=lambda item: (item.get("number", 0), item.get("id", "")))
    simulation_id = uuid.uuid4().hex
    question_ids = [question["id"] for question in paper]
    create_simulation(
        {
            "id": simulation_id,
            "user_id": payload.user_id.strip() or "local-user",
            "exam_type": payload.exam_type,
            "year": year,
            "question_ids": question_ids,
            "max_score": sum(float(question.get("points", 0)) for question in paper),
            "duration_seconds": payload.duration_minutes * 60,
        }
    )
    return simulation_view(get_simulation(simulation_id), reveal=False)


def simulation_view(simulation: dict[str, Any] | None, reveal: bool = False) -> dict[str, Any]:
    if simulation is None:
        raise HTTPException(status_code=404, detail="模拟考试不存在。")
    questions = []
    answer_map = {answer["question_id"]: answer for answer in simulation.get("answers", [])}
    for question_id in simulation["question_ids"]:
        question = question_store.get(question_id)
        if question is None:
            continue
        item = _question_public(question, reveal=reveal)
        if question_id in answer_map:
            item["attempt"] = answer_map[question_id]
        questions.append(item)
    return {**{key: value for key, value in simulation.items() if key not in {"question_ids", "answers"}}, "questions": questions}


@app.get("/api/simulations/{simulation_id}")
def get_simulation_endpoint(simulation_id: str) -> dict[str, Any]:
    simulation = get_simulation(simulation_id)
    return simulation_view(simulation, reveal=bool(simulation and simulation.get("status") == "finished"))


@app.delete("/api/simulations/{simulation_id}")
def cancel_simulation_endpoint(simulation_id: str, user_id: str = "local-user") -> dict[str, str]:
    simulation = get_simulation(simulation_id)
    if simulation is None:
        raise HTTPException(status_code=404, detail="模拟考试不存在。")
    normalized_user_id = user_id.strip() or "local-user"
    if simulation.get("user_id") != normalized_user_id:
        raise HTTPException(status_code=403, detail="没有权限取消这套模拟考。")
    if simulation.get("status") == "finished":
        raise HTTPException(status_code=409, detail="已交卷的模拟考不能取消。")
    if not delete_simulation(simulation_id):
        raise HTTPException(status_code=409, detail="模拟考状态已发生变化，请刷新后重试。")
    return {"id": simulation_id, "status": "cancelled"}


@app.post("/api/simulations/{simulation_id}/submit")
def submit_simulation(simulation_id: str, payload: SimulationSubmitRequest) -> dict[str, Any]:
    simulation = get_simulation(simulation_id)
    if simulation is None:
        raise HTTPException(status_code=404, detail="模拟考试不存在。")
    if simulation.get("status") == "finished":
        return simulation_view(simulation, reveal=True)
    total = 0.0
    for question_id in simulation["question_ids"]:
        question = _question_or_404(question_id)
        answer = payload.answers.get(question_id, "")
        self_grade = payload.self_grades.get(question_id)
        result = grade_question(question, answer, self_grade)
        total += float(result["score"])
        upsert_simulation_answer(
            {
                "simulation_id": simulation_id,
                "question_id": question_id,
                "answer": answer,
                "correct": result.get("correct"),
                "status": result["status"],
                "score": result["score"],
            }
        )
        attempt_id = insert_attempt(
            {
                "user_id": payload.user_id.strip() or simulation.get("user_id", "local-user"),
                "question_id": question_id,
                "answer": answer,
                "correct": result.get("correct"),
                "status": result["status"],
                "score": result["score"],
                "max_score": result["max_score"],
                "confidence": result["confidence"],
                "error_type": result.get("error_type", ""),
                "concepts": question.get("concept_ids", []),
                "duration_seconds": 0,
                "hints_used": 0,
                "mode": "simulation",
            }
        )
        link_attachments(
            payload.attachment_ids.get(question_id, []),
            user_id=payload.user_id.strip() or simulation.get("user_id", "local-user"),
            question_id=question_id,
            attempt_id=attempt_id,
            simulation_id=simulation_id,
        )
    finish_simulation(simulation_id, total)
    return simulation_view(get_simulation(simulation_id), reveal=True)


@app.get("/api/llm/settings")
def llm_settings() -> dict[str, Any]:
    return public_settings()


@app.post("/api/llm/settings")
def save_llm_settings(payload: ModelSettingsRequest) -> dict[str, Any]:
    try:
        return save_settings(payload.base_url, payload.model, payload.api_key, payload.clear_api_key)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/llm/models")
async def llm_models(payload: ModelFetchRequest) -> dict[str, Any]:
    try:
        models = await fetch_models(payload.base_url, payload.api_key)
        return {"models": models}
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/server/settings")
def get_server_settings() -> dict[str, Any]:
    return server_settings()


@app.post("/api/server/settings")
def update_server_settings(payload: ServerSettingsRequest) -> dict[str, Any]:
    try:
        return save_server_settings(payload.host, payload.port, payload.public_url)
    except ServerSettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/questions/{question_id}/tutor")
async def tutor(question_id: str, payload: TutorRequest) -> dict[str, Any]:
    question = _question_or_404(question_id)
    try:
        return await tutor_response(question, payload.answer, payload.request)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
