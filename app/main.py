from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
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
    get_question_classification_override,
    get_template_override,
    init_db,
    insert_attempt,
    list_note_versions,
    list_notes,
    list_template_overrides,
    list_template_versions,
    list_question_classification_overrides,
    link_attachments,
    note_asset_path,
    restore_note_version,
    touch_practice_session,
    update_note,
    upsert_template_override,
    upsert_practice_session_answer,
    upsert_question_classification,
    upsert_simulation_answer,
)
from app.services.content import question_store
from app.services.auth import (
    AuthContext,
    AuthValidationError,
    admin_overview,
    authenticate_user,
    change_password,
    check_rate_limit,
    clear_session_cookies,
    create_session,
    create_user,
    current_csrf_token,
    get_preferences,
    has_admin,
    list_audit_events,
    list_sessions,
    list_users,
    require_admin,
    require_user,
    revoke_other_sessions,
    revoke_session,
    revoke_user_sessions_by_admin,
    set_csrf_cookie,
    set_session_cookies,
    update_preferences,
    update_profile,
    update_user_by_admin,
    user_count,
)
from app.services.concepts import MATH2_CONCEPT_IDS, concept_descriptor
from app.services.grading import grade_question
from app.services.learner import (
    CONCEPT_META,
    forecast_score,
    learning_analytics,
    difficulty_descriptor,
    progress_summary,
    question_attempt_summaries,
    randomized_practice_questions,
    recommended_questions,
    study_blocks,
)
from app.services.llm import LLMError, fetch_models, hint_response, public_settings, save_settings, tutor_response
from app.services.server import ServerSettingsError, save_server_settings, server_settings
from app.services.workbench import (
    build_workbench_template,
    is_valid_subtype,
    question_subtype_ids,
    subtype_count,
    subtype_descriptor,
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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        # Prevent a shared browser profile from serving one account's cached
        # progress or settings after logout/login as another account.
        response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def _user_id(context: AuthContext, supplied: str | None = None) -> str:
    """Use the session identity; only an unclaimed legacy workspace may pass its old id."""
    if context.legacy:
        return str(supplied or context.user_id or "local-user").strip()[:100] or "local-user"
    return context.user_id


def _request_ip(request: Request) -> str:
    return (request.client.host if request.client else "")[:64]


def _validate_answer_maps(
    answers: dict[str, str],
    self_grades: dict[str, float],
    attachment_ids: dict[str, list[str]],
    allowed_ids: set[str],
) -> None:
    submitted_ids = set(answers) | set(self_grades) | set(attachment_ids)
    unknown = submitted_ids - allowed_ids
    if unknown:
        raise HTTPException(status_code=400, detail="提交中包含不属于当前题组的题目。")
    if any(len(str(value)) > 300000 for value in answers.values()):
        raise HTTPException(status_code=413, detail="单题答案不能超过 300000 个字符。")
    if any(len(items) > 8 for items in attachment_ids.values()):
        raise HTTPException(status_code=400, detail="单题最多关联 8 个附件。")


def _auth_payload(user: dict[str, Any], csrf_token: str, expires_at: str) -> dict[str, Any]:
    return {"user": user, "csrf_token": csrf_token, "session_expires_at": expires_at}


def _image_magic_matches(content_type: str, content: bytes) -> bool:
    signatures = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/gif": content.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
    }
    return bool(signatures.get(content_type, False))


class AttemptRequest(BaseModel):
    user_id: str = "local-user"
    answer: str = Field(default="", max_length=300000)
    self_grade: float | None = Field(default=None, ge=0, le=1)
    duration_seconds: int = Field(default=0, ge=0, le=86400)
    hints_used: int = Field(default=0, ge=0, le=100)
    error_type: str = Field(default="", max_length=200)
    mode: str = Field(default="practice", max_length=40)
    attachment_ids: list[str] = Field(default_factory=list, max_length=8)


class SimulationCreateRequest(BaseModel):
    user_id: str = "local-user"
    exam_type: str = "数学二"
    year: int | None = None
    duration_minutes: int = Field(default=180, ge=1, le=600)


class SimulationSubmitRequest(BaseModel):
    user_id: str = "local-user"
    answers: dict[str, str] = Field(default_factory=dict, max_length=30)
    self_grades: dict[str, float] = Field(default_factory=dict, max_length=30)
    attachment_ids: dict[str, list[str]] = Field(default_factory=dict, max_length=30)


class PracticeSessionCreateRequest(BaseModel):
    user_id: str = "local-user"
    exam_type: str = "数学二"
    concept_id: str
    question_type: str = ""
    subtype_id: str = ""
    count: int = Field(default=15, ge=1, le=15)
    exclude_question_ids: list[str] = Field(default_factory=list, max_length=30)


class ClassificationCorrectionRequest(BaseModel):
    user_id: str = "local-user"
    concept_id: str
    subtype_id: str
    note: str = Field(default="", max_length=500)


class PracticeSessionDataRequest(BaseModel):
    user_id: str = "local-user"
    answers: dict[str, str] = Field(default_factory=dict, max_length=15)
    self_grades: dict[str, float] = Field(default_factory=dict, max_length=15)
    attachment_ids: dict[str, list[str]] = Field(default_factory=dict, max_length=15)


class ModelSettingsRequest(BaseModel):
    base_url: str = Field(default="", max_length=2048)
    model: str = Field(default="", max_length=200)
    api_key: str | None = Field(default=None, max_length=500)
    clear_api_key: bool = False


class ModelFetchRequest(BaseModel):
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=500)


class ServerSettingsRequest(BaseModel):
    host: str = Field(default="127.0.0.1", max_length=253)
    port: int = Field(default=8000, ge=1, le=65535)
    public_url: str = Field(default="", max_length=2048)


class TutorRequest(BaseModel):
    user_id: str = "local-user"
    answer: str = Field(default="", max_length=300000)
    request: str = Field(default="分析我的错误", max_length=500)


class NoteRequest(BaseModel):
    user_id: str = "local-user"
    title: str = Field(default="未命名笔记", max_length=200)
    concept_id: str = Field(default="", max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=30)
    content_html: str = Field(default="", max_length=300000)
    content_markdown: str = Field(default="", max_length=300000)
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


class AuthRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    email: str = Field(default="", max_length=254)
    display_name: str = Field(default="", max_length=80)


class AuthLoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    email: str = Field(default="", max_length=254)


class PreferencesUpdateRequest(BaseModel):
    theme: str = "system"
    default_exam_type: str = "数学二"
    daily_goal: int = Field(default=30, ge=5, le=240)
    practice_count: int = Field(default=15, ge=1, le=15)
    sound_enabled: bool = False


class AdminUserUpdateRequest(BaseModel):
    role: str = "user"
    is_active: bool = True
    display_name: str = Field(min_length=1, max_length=80)


def _question_override(question: dict[str, Any], user_id: str = "local-user", overrides: dict[str, dict[str, Any]] | None = None) -> dict[str, Any] | None:
    question_id = str(question.get("id", ""))
    if overrides is not None:
        return overrides.get(question_id)
    return get_question_classification_override(user_id, question_id)


def _effective_question(question: dict[str, Any], override: dict[str, Any] | None = None) -> dict[str, Any]:
    if not override:
        return question
    item = dict(question)
    original_concepts = list(question.get("concept_ids") or [])
    item["concept_ids"] = [override["concept_id"]] + [
        concept_id for concept_id in original_concepts if concept_id not in MATH2_CONCEPT_IDS
    ]
    item["_classification_override"] = override
    return item


def _questions_for_user(user_id: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    normalized_user = user_id.strip() or "local-user"
    overrides = list_question_classification_overrides(normalized_user)
    return [
        _effective_question(question, overrides.get(str(question.get("id", ""))))
        for question in question_store.list()
    ], overrides


def _question_attempt_stats(user_id: str = "local-user") -> dict[str, dict[str, Any]]:
    return question_attempt_summaries(fetch_attempts(user_id.strip() or "local-user"))


def _empty_attempt_summary() -> dict[str, Any]:
    return {
        "attempted": False,
        "attempts": 0,
        "correct": 0,
        "incorrect": 0,
        "partial": 0,
        "manual": 0,
        "accuracy": None,
        "last_status": "",
        "last_status_label": "",
        "last_score": 0,
        "last_max_score": 0,
        "last_attempt_at": None,
    }


def _attach_workbench_attempt_stats(template: dict[str, Any], attempt_stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Add the same per-question history used by the library to Workbench."""
    containers = [template.get("example"), *(template.get("variants") or [])]
    for container in containers:
        question = container.get("question") if isinstance(container, dict) else None
        if not isinstance(question, dict):
            continue
        summary = dict(attempt_stats.get(str(question.get("id", "")), _empty_attempt_summary()))
        question["attempt_summary"] = summary
        question["attempted"] = bool(summary.get("attempts"))
    return template


def _question_public(
    question: dict[str, Any],
    reveal: bool = False,
    *,
    user_id: str = "local-user",
    classification_overrides: dict[str, dict[str, Any]] | None = None,
    attempt_stats: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    override = _question_override(question, user_id, classification_overrides)
    effective = _effective_question(question, override)
    result = {key: value for key, value in question.items() if key not in {"raw_markdown", "answer_markdown", "solution_markdown"}}
    result["concept_ids"] = list(effective.get("concept_ids") or [])
    difficulty_band, difficulty_label = difficulty_descriptor(effective.get("year"))
    result["difficulty_band"] = difficulty_band
    result["difficulty_label"] = difficulty_label
    result["answer_available"] = bool(effective.get("has_answer"))
    result["solution_available"] = bool(effective.get("has_solution"))
    result["concept_labels"] = [concept_descriptor(item) for item in effective.get("concept_ids", [])]
    result["has_out_of_syllabus_concepts"] = any(item["scope"] == "out-of-syllabus" for item in result["concept_labels"])
    subtype_ids = [override["subtype_id"]] if override else question_subtype_ids(question)
    subtype_items = [descriptor for item in subtype_ids if (descriptor := subtype_descriptor(item))]
    result["subtype_ids"] = subtype_ids
    result["subtype_labels"] = subtype_items
    result["classification_source"] = "user-correction" if override else ("rule" if subtype_ids else "unclassified")
    result["classification_updated_at"] = override.get("updated_at", "") if override else ""
    result["classification_note"] = override.get("note", "") if override else ""
    if attempt_stats is None:
        attempt_stats = _question_attempt_stats(user_id)
    result["attempt_summary"] = dict(attempt_stats.get(str(question.get("id", "")), _empty_attempt_summary()))
    result["attempted"] = bool(result["attempt_summary"].get("attempts"))
    if reveal:
        result["answer_markdown"] = effective.get("answer_markdown", "")
        result["solution_markdown"] = effective.get("solution_markdown", "")
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
    item = {
        "id": note_id or uuid.uuid4().hex,
        "user_id": user_id.strip() or "local-user",
        "title": payload.title.strip() or "未命名笔记",
        "concept_id": payload.concept_id.strip(),
        "tags": tags,
        "content_html": _sanitize_note_html(payload.content_html),
        "content_markdown": payload.content_markdown[:300000],
        "favorite": bool(payload.favorite),
    }
    return item


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    # The shell carries versioned asset URLs; keep the document itself fresh
    # so a desktop browser cannot remain on a stale auth/bootstrap bundle.
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/auth/bootstrap")
def auth_bootstrap() -> dict[str, Any]:
    return {"registration_enabled": True, "has_users": user_count() > 0, "has_admin": has_admin()}


@app.post("/api/auth/register")
def auth_register(payload: AuthRegisterRequest, request: Request, response: Response) -> dict[str, Any]:
    check_rate_limit(request, "register")
    try:
        user, is_first = create_user(
            payload.username,
            payload.password,
            email=payload.email,
            display_name=payload.display_name,
            ip_address=_request_ip(request),
        )
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token, csrf_token, expires_at = create_session(user["id"], request)
    set_session_cookies(response, request, token, csrf_token)
    return {**_auth_payload(user, csrf_token, expires_at), "first_account_is_admin": is_first}


@app.post("/api/auth/login")
def auth_login(payload: AuthLoginRequest, request: Request, response: Response) -> dict[str, Any]:
    check_rate_limit(request, "login")
    user = authenticate_user(payload.identifier, payload.password, ip_address=_request_ip(request))
    if user is None:
        raise HTTPException(status_code=401, detail="账号或密码错误。")
    token, csrf_token, expires_at = create_session(user["id"], request)
    set_session_cookies(response, request, token, csrf_token)
    return _auth_payload(user, csrf_token, expires_at)


@app.get("/api/auth/me")
def auth_me(request: Request, response: Response, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    if context.legacy:
        raise HTTPException(status_code=401, detail="当前工作区尚未注册账户。")
    csrf_token = current_csrf_token(request, context)
    set_csrf_cookie(response, request, csrf_token)
    return _auth_payload(context.user, csrf_token, "")


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response, context: AuthContext = Depends(require_user)) -> dict[str, str]:
    if context.session_hash:
        revoke_session(context.session_hash, context.user_id)
    clear_session_cookies(response)
    return {"status": "logged_out"}


@app.post("/api/auth/change-password")
def auth_change_password(payload: ChangePasswordRequest, request: Request, response: Response, context: AuthContext = Depends(require_user)) -> dict[str, str]:
    if context.legacy:
        raise HTTPException(status_code=401, detail="请先注册账户后再修改密码。")
    try:
        change_password(context.user_id, payload.current_password, payload.new_password, ip_address=_request_ip(request))
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clear_session_cookies(response)
    return {"status": "password_changed", "message": "密码已更新，请重新登录。"}


@app.get("/api/auth/sessions")
def auth_sessions(context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    if context.legacy:
        return {"items": []}
    return {"items": list_sessions(context.user_id, context.session_hash)}


@app.post("/api/auth/sessions/revoke-others")
def auth_revoke_other_sessions(context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    if context.legacy:
        return {"revoked": 0}
    return {"revoked": revoke_other_sessions(context.user_id, context.session_hash)}


@app.get("/api/settings")
def account_settings(context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    if context.legacy:
        return {"profile": context.user, "preferences": {"theme": "system", "default_exam_type": "数学二", "daily_goal": 30, "practice_count": 15, "sound_enabled": False}, "sessions": []}
    return {
        "profile": context.user,
        "preferences": get_preferences(context.user_id),
        "sessions": list_sessions(context.user_id, context.session_hash),
    }


@app.patch("/api/settings/profile")
def account_profile_update(payload: ProfileUpdateRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    if context.legacy:
        raise HTTPException(status_code=401, detail="请先注册账户后再修改账户资料。")
    try:
        profile = update_profile(_user_id(context, context.user_id), display_name=payload.display_name, email=payload.email)
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"profile": profile}


@app.patch("/api/settings/preferences")
def account_preferences_update(payload: PreferencesUpdateRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    if context.legacy:
        raise HTTPException(status_code=401, detail="请先注册账户后再修改学习偏好。")
    try:
        preferences = update_preferences(context.user_id, payload.model_dump())
    except (AuthValidationError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"preferences": preferences}


@app.get("/api/admin/overview")
def get_admin_overview(_: AuthContext = Depends(require_admin)) -> dict[str, Any]:
    return admin_overview()


@app.get("/api/admin/users")
def get_admin_users(
    search: str = Query(default="", max_length=80),
    role: str = Query(default="", max_length=12),
    status: str = Query(default="", max_length=12),
    _: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    return {"items": list_users(search=search, role=role, status=status)}


@app.patch("/api/admin/users/{target_user_id}")
def admin_update_user(target_user_id: str, payload: AdminUserUpdateRequest, request: Request, context: AuthContext = Depends(require_admin)) -> dict[str, Any]:
    try:
        user = update_user_by_admin(
            target_user_id,
            role=payload.role,
            is_active=payload.is_active,
            display_name=payload.display_name,
            actor_user_id=context.user_id,
            ip_address=_request_ip(request),
        )
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user}


@app.post("/api/admin/users/{target_user_id}/sessions/revoke")
def admin_revoke_user_sessions(target_user_id: str, request: Request, context: AuthContext = Depends(require_admin)) -> dict[str, Any]:
    try:
        revoked = revoke_user_sessions_by_admin(
            target_user_id,
            actor_user_id=context.user_id,
            ip_address=_request_ip(request),
        )
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"revoked": revoked}


@app.get("/api/admin/audit")
def get_admin_audit(
    limit: int = Query(default=100, ge=1, le=200),
    action: str = Query(default="", max_length=80),
    search: str = Query(default="", max_length=100),
    _: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    return {"items": list_audit_events(limit, action=action, search=search)}


@app.get("/api/health")
def health() -> dict[str, Any]:
    questions = question_store.list()
    return {"status": "ok", "question_count": len(questions), "data_ready": bool(questions)}


@app.post("/api/uploads/answer-image")
async def upload_answer_image(
    file: UploadFile = File(...),
    user_id: str = Form(default="local-user"),
    question_id: str = Form(...),
    context: AuthContext = Depends(require_user),
) -> dict[str, Any]:
    content_type = (file.content_type or "").lower()
    if content_type not in IMAGE_SUFFIXES:
        raise HTTPException(status_code=415, detail="只支持 PNG、JPG、WebP 或 GIF 图片。")
    content = await file.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="图片不能超过 8 MB。")
    if not _image_magic_matches(content_type, content):
        raise HTTPException(status_code=415, detail="文件内容与图片类型不匹配。")
    _question_or_404(question_id)
    owner_id = _user_id(context, user_id)
    attachment_id = uuid.uuid4().hex
    relative_path = Path("data") / "uploads" / f"{attachment_id}{IMAGE_SUFFIXES[content_type]}"
    absolute_path = ROOT_DIR / relative_path
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(content)
    create_attachment(
        {
            "id": attachment_id,
            "user_id": owner_id,
            "question_id": question_id,
            "filename": Path(file.filename or "answer-image").name[:120] or "answer-image",
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
def get_attachment(attachment_id: str, user_id: str = "local-user", context: AuthContext = Depends(require_user)) -> FileResponse:
    path = attachment_path(attachment_id, _user_id(context, user_id))
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="图片不存在。")
    return FileResponse(path)


@app.get("/api/workbench")
def get_workbench_catalog(
    concept_id: str = Query(default=""),
    subtype_id: str = Query(default=""),
    user_id: str = Query(default="local-user"),
    refresh: bool = Query(default=False),
    exclude_question_ids: list[str] = Query(default=[]),
    context: AuthContext = Depends(require_user),
) -> dict[str, Any]:
    owner_id = _user_id(context, user_id)
    questions, _ = _questions_for_user(owner_id)
    attempt_stats = _question_attempt_stats(owner_id)
    if concept_id or subtype_id:
        if not concept_id or not subtype_id:
            raise HTTPException(status_code=400, detail="选择知识块和细分题型后才能读取模板。")
        override = get_template_override(owner_id, concept_id, subtype_id)
        try:
            template = build_workbench_template(
                questions,
                concept_id,
                subtype_id,
                override,
                refresh=refresh,
                exclude_question_ids=exclude_question_ids,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"template": _attach_workbench_attempt_stats(template, attempt_stats)}
    catalog = workbench_catalog(questions, attempt_stats=attempt_stats)
    return {
        "concepts": catalog,
        "total_templates": subtype_count(),
        "taxonomy_version": "math2-subtypes-v1",
    }


@app.put("/api/workbench/templates/{concept_id}/{subtype_id}")
def save_workbench_template(concept_id: str, subtype_id: str, payload: TemplateUpdateRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    if not is_valid_subtype(concept_id, subtype_id):
        raise HTTPException(status_code=400, detail="无效的知识块或细分题型。")
    owner_id = _user_id(context, payload.user_id)
    saved = upsert_template_override({
        "user_id": owner_id,
        "concept_id": concept_id,
        "question_type": subtype_id,
        "overview": payload.overview.strip(),
        "framework": [item.strip() for item in payload.framework if item.strip()],
        "mistakes": [item.strip() for item in payload.mistakes if item.strip()],
        "memory_aid": payload.memory_aid.strip(),
    })
    questions, _ = _questions_for_user(owner_id)
    template = build_workbench_template(questions, concept_id, subtype_id, saved)
    return {"template": _attach_workbench_attempt_stats(template, _question_attempt_stats(owner_id))}


@app.get("/api/workbench/templates/{concept_id}/{subtype_id}/versions")
def get_workbench_template_versions(concept_id: str, subtype_id: str, user_id: str = "local-user", context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    if not is_valid_subtype(concept_id, subtype_id):
        raise HTTPException(status_code=400, detail="无效的知识块或细分题型。")
    return {"items": list_template_versions(_user_id(context, user_id), concept_id, subtype_id)}


@app.get("/api/workbench/notes")
def get_workbench_notes(
    user_id: str = "local-user",
    search: str = "",
    concept_id: str = "",
    favorite: bool = False,
    context: AuthContext = Depends(require_user),
) -> dict[str, Any]:
    return {"items": list_notes(_user_id(context, user_id), search=search, concept_id=concept_id, favorite_only=favorite)}


@app.post("/api/workbench/notes")
def create_workbench_note(payload: NoteRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    item = _normalize_note_payload(payload, user_id=_user_id(context, payload.user_id))
    return {"note": create_note(item)}


@app.get("/api/workbench/notes/{note_id}")
def get_workbench_note(note_id: str, user_id: str = "local-user", context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    note = get_note(note_id, _user_id(context, user_id))
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在。")
    return {"note": note}


@app.put("/api/workbench/notes/{note_id}")
def update_workbench_note(note_id: str, payload: NoteRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    user_id = _user_id(context, payload.user_id)
    if get_note(note_id, user_id) is None:
        raise HTTPException(status_code=404, detail="笔记不存在。")
    item = _normalize_note_payload(payload, user_id=user_id, note_id=note_id)
    saved = update_note(note_id, user_id, item)
    if saved is None:
        raise HTTPException(status_code=404, detail="笔记不存在。")
    return {"note": saved}


@app.delete("/api/workbench/notes/{note_id}")
def delete_workbench_note(note_id: str, user_id: str = "local-user", context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    if not delete_note(note_id, _user_id(context, user_id)):
        raise HTTPException(status_code=404, detail="笔记不存在。")
    return {"status": "deleted", "note_id": note_id}


@app.get("/api/workbench/notes/{note_id}/versions")
def get_workbench_note_versions(note_id: str, user_id: str = "local-user", context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    normalized_user_id = _user_id(context, user_id)
    if get_note(note_id, normalized_user_id) is None:
        raise HTTPException(status_code=404, detail="笔记不存在。")
    return {"items": list_note_versions(note_id, normalized_user_id)}


@app.post("/api/workbench/notes/{note_id}/restore/{version_id}")
def restore_workbench_note_version(note_id: str, version_id: int, user_id: str = "local-user", context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    note = restore_note_version(note_id, version_id, _user_id(context, user_id))
    if note is None:
        raise HTTPException(status_code=404, detail="笔记版本不存在。")
    return {"note": note}


@app.post("/api/workbench/notes/assets")
async def upload_workbench_note_asset(
    file: UploadFile = File(...),
    user_id: str = Form(default="local-user"),
    context: AuthContext = Depends(require_user),
) -> dict[str, Any]:
    content_type = (file.content_type or "").lower()
    if content_type not in IMAGE_SUFFIXES:
        raise HTTPException(status_code=415, detail="只支持 PNG、JPG、WebP 或 GIF 图片。")
    content = await file.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="图片不能超过 8 MB。")
    if not _image_magic_matches(content_type, content):
        raise HTTPException(status_code=415, detail="文件内容与图片类型不匹配。")
    owner_id = _user_id(context, user_id)
    asset_id = uuid.uuid4().hex
    relative_path = Path("data") / "uploads" / "notes" / f"{asset_id}{IMAGE_SUFFIXES[content_type]}"
    absolute_path = ROOT_DIR / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(content)
    create_note_asset({
        "id": asset_id,
        "user_id": owner_id,
        "filename": Path(file.filename or "note-image").name[:120] or "note-image",
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
def get_workbench_note_asset(asset_id: str, user_id: str = "local-user", context: AuthContext = Depends(require_user)) -> FileResponse:
    path = note_asset_path(asset_id, _user_id(context, user_id))
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="笔记图片不存在。")
    return FileResponse(path)


@app.get("/api/workbench/export")
def export_workbench(user_id: str = "local-user", context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    normalized_user_id = _user_id(context, user_id)
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
def import_workbench(payload: WorkbenchImportRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    user_id = _user_id(context, payload.user_id)
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
        subtype_id = str(raw_template.get("question_type", ""))
        if not is_valid_subtype(concept_id, subtype_id):
            continue
        try:
            request = TemplateUpdateRequest(**raw_template)
        except Exception:
            continue
        upsert_template_override({
            "user_id": user_id,
            "concept_id": concept_id,
            "question_type": subtype_id,
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
    user_id: str = "local-user",
    exam_type: str | None = None,
    year: int | None = None,
    question_type: str | None = None,
    concept_id: str | None = None,
    subtype_id: str | None = None,
    scope: str | None = None,
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_user),
) -> dict[str, Any]:
    normalized_user = _user_id(context, user_id)
    overrides = list_question_classification_overrides(normalized_user)
    attempt_stats = _question_attempt_stats(normalized_user)
    if subtype_id and subtype_descriptor(subtype_id) is None:
        raise HTTPException(status_code=400, detail="无效的细分题型。")
    items = []
    for question in question_store.list():
        override = overrides.get(str(question.get("id", "")))
        effective = _effective_question(question, override)
        if exam_type and question.get("exam_type") != exam_type:
            continue
        if year and question.get("year") != year:
            continue
        if question_type and question.get("question_type") != question_type:
            continue
        if concept_id and concept_id not in effective.get("concept_ids", []):
            continue
        if subtype_id and subtype_id not in ([override["subtype_id"]] if override else question_subtype_ids(question)):
            continue
        if scope in {"math2", "out-of-syllabus"}:
            question_scopes = {concept_descriptor(item)["scope"] for item in effective.get("concept_ids", [])}
            if scope not in question_scopes:
                continue
        items.append(_question_public(question, user_id=normalized_user, classification_overrides=overrides, attempt_stats=attempt_stats))
    items.sort(key=lambda item: (item.get("year", 0), item.get("number", 0), item.get("id", "")), reverse=True)
    return {"items": items[offset : offset + limit], "total": len(items), "offset": offset, "limit": limit}


@app.get("/api/questions/{question_id}")
def get_question(question_id: str, reveal: bool = False, user_id: str = "local-user", context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    owner_id = _user_id(context, user_id)
    return _question_public(_question_or_404(question_id), reveal=reveal, user_id=owner_id, attempt_stats=_question_attempt_stats(owner_id))


@app.put("/api/questions/{question_id}/classification")
def correct_question_classification(question_id: str, payload: ClassificationCorrectionRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    question = _question_or_404(question_id)
    user_id = _user_id(context, payload.user_id)
    if payload.concept_id not in MATH2_CONCEPT_IDS:
        raise HTTPException(status_code=400, detail="纠正分类必须选择数学二大纲内知识块。")
    if not is_valid_subtype(payload.concept_id, payload.subtype_id):
        raise HTTPException(status_code=400, detail="所选细分题型不属于该知识块。")
    saved = upsert_question_classification(
        {
            "user_id": user_id,
            "question_id": question_id,
            "concept_id": payload.concept_id,
            "subtype_id": payload.subtype_id,
            "note": payload.note,
        }
    )
    return {"question": _question_public(question, user_id=user_id, attempt_stats=_question_attempt_stats(user_id)), "override": saved}


@app.post("/api/questions/{question_id}/attempts")
def create_attempt(question_id: str, payload: AttemptRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    question = _question_or_404(question_id)
    owner_id = _user_id(context, payload.user_id)
    effective_question = _effective_question(question, _question_override(question, owner_id))
    result = grade_question(question, payload.answer, payload.self_grade)
    error_type = payload.error_type.strip() or result.get("error_type", "")
    attempt_id = insert_attempt(
        {
            "user_id": owner_id,
            "question_id": question_id,
            "answer": payload.answer,
            "correct": result.get("correct"),
            "status": result["status"],
            "score": result["score"],
            "max_score": result["max_score"],
            "confidence": result["confidence"],
            "error_type": error_type,
            "concepts": effective_question.get("concept_ids", []),
            "duration_seconds": payload.duration_seconds,
            "hints_used": payload.hints_used,
            "mode": payload.mode,
        }
    )
    link_attachments(
        payload.attachment_ids,
        user_id=owner_id,
        question_id=question_id,
        attempt_id=attempt_id,
    )
    result["error_type"] = error_type
    response = _attempt_response(question, result, attempt_id)
    response["attempt_summary"] = _question_attempt_stats(owner_id).get(question_id, _empty_attempt_summary())
    return response


@app.get("/api/progress")
def progress(user_id: str = "local-user", context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    owner_id = _user_id(context, user_id)
    questions, _ = _questions_for_user(owner_id)
    return progress_summary(fetch_attempts(owner_id), questions)


@app.get("/api/analytics")
def analytics(user_id: str = "local-user", exam_type: str = "数学二", context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    owner_id = _user_id(context, user_id)
    questions, _ = _questions_for_user(owner_id)
    return learning_analytics(questions, fetch_attempts(owner_id), exam_type=exam_type)


@app.get("/api/practice/next")
def practice_next(
    user_id: str = "local-user",
    exam_type: str = "数学二",
    concept_id: str | None = None,
    subtype_id: str | None = None,
    limit: int = Query(default=8, ge=1, le=30),
    context: AuthContext = Depends(require_user),
) -> dict[str, Any]:
    owner_id = _user_id(context, user_id)
    attempts = fetch_attempts(owner_id)
    questions, overrides = _questions_for_user(owner_id)
    attempt_stats = question_attempt_summaries(attempts)
    items = recommended_questions(questions, attempts, exam_type=exam_type, concept_id=concept_id, limit=limit)
    if subtype_id:
        items = [item for item in items if subtype_id in question_subtype_ids(item)]
    return {
        "items": [_question_public(item, user_id=owner_id, classification_overrides=overrides, attempt_stats=attempt_stats) for item in items],
        "concept_id": concept_id,
        "subtype_id": subtype_id,
        "exam_type": exam_type,
    }


@app.get("/api/study/blocks")
def study_block_endpoint(user_id: str = "local-user", limit: int = Query(default=6, ge=1, le=12), context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    owner_id = _user_id(context, user_id)
    questions, overrides = _questions_for_user(owner_id)
    attempts = fetch_attempts(owner_id)
    attempt_stats = question_attempt_summaries(attempts)
    blocks = study_blocks(questions, attempts, limit=limit)
    return {
        "blocks": [
            {
                **block,
                "questions": [_question_public(item, user_id=owner_id, classification_overrides=overrides, attempt_stats=attempt_stats) for item in block["questions"]],
            }
            for block in blocks
        ]
    }


def practice_session_view(session: dict[str, Any] | None, *, reveal: bool = False) -> dict[str, Any]:
    if session is None:
        raise HTTPException(status_code=404, detail="训练会话不存在。")
    answer_map = {answer["question_id"]: answer for answer in session.get("answers", [])}
    attempt_stats = _question_attempt_stats(session.get("user_id", "local-user"))
    questions = []
    for question_id in session["question_ids"]:
        question = question_store.get(question_id)
        if question is None:
            continue
        item = _question_public(
            question,
            reveal=reveal,
            user_id=session.get("user_id", "local-user"),
            attempt_stats=attempt_stats,
        )
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
    _validate_answer_maps(payload.answers, payload.self_grades, payload.attachment_ids, allowed)


@app.post("/api/practice/sessions")
def create_practice_session_endpoint(payload: PracticeSessionCreateRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    if payload.question_type and payload.question_type not in {"choice", "fill", "solution"}:
        raise HTTPException(status_code=400, detail="不支持的题型。")
    if payload.subtype_id and not is_valid_subtype(payload.concept_id, payload.subtype_id):
        raise HTTPException(status_code=400, detail="所选细分题型不属于该知识块。")
    user_id = _user_id(context, payload.user_id)
    attempts = fetch_attempts(user_id)
    questions, _ = _questions_for_user(user_id)
    selected = randomized_practice_questions(
        questions, attempts,
        exam_type=payload.exam_type,
        concept_id=payload.concept_id,
        question_type=payload.question_type or None,
        subtype_id=payload.subtype_id or None,
        limit=payload.count,
        exclude_question_ids=payload.exclude_question_ids,
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
            "subtype_id": payload.subtype_id,
            "question_ids": [question["id"] for question in selected],
            "requested_count": payload.count,
            "max_score": sum(float(question.get("points", 0)) for question in selected),
        }
    )
    return practice_session_view(get_practice_session(session_id))


@app.get("/api/practice/sessions/{session_id}")
def get_practice_session_endpoint(session_id: str, user_id: str = "local-user", context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    session = _practice_session_or_404(session_id, _user_id(context, user_id))
    return practice_session_view(session, reveal=session.get("status") == "finished")


@app.put("/api/practice/sessions/{session_id}")
def save_practice_session_endpoint(session_id: str, payload: PracticeSessionDataRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    session = _practice_session_or_404(session_id, _user_id(context, payload.user_id))
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
def submit_practice_session_endpoint(session_id: str, payload: PracticeSessionDataRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    session = _practice_session_or_404(session_id, _user_id(context, payload.user_id))
    if session.get("status") == "finished":
        return practice_session_view(session, reveal=True)
    _validate_practice_payload(session, payload)
    total = 0.0
    for question_id in session["question_ids"]:
        question = _question_or_404(question_id)
        effective_question = _effective_question(question, _question_override(question, session["user_id"]))
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
                "concepts": effective_question.get("concept_ids", []),
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
def score_forecast(user_id: str = "local-user", exam_type: str = "数学二", context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    owner_id = _user_id(context, user_id)
    questions, _ = _questions_for_user(owner_id)
    return forecast_score(questions, fetch_attempts(owner_id), exam_type=exam_type)


@app.post("/api/simulations")
def create_simulation_endpoint(payload: SimulationCreateRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
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
            "user_id": _user_id(context, payload.user_id),
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
    attempt_stats = _question_attempt_stats(simulation.get("user_id", "local-user"))
    for question_id in simulation["question_ids"]:
        question = question_store.get(question_id)
        if question is None:
            continue
        item = _question_public(
            question,
            reveal=reveal,
            user_id=simulation.get("user_id", "local-user"),
            attempt_stats=attempt_stats,
        )
        if question_id in answer_map:
            item["attempt"] = answer_map[question_id]
        questions.append(item)
    return {**{key: value for key, value in simulation.items() if key not in {"question_ids", "answers"}}, "questions": questions}


@app.get("/api/simulations/{simulation_id}")
def get_simulation_endpoint(simulation_id: str, user_id: str = "local-user", context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    simulation = get_simulation(simulation_id)
    if simulation is not None and simulation.get("user_id") != _user_id(context, user_id):
        raise HTTPException(status_code=404, detail="模拟考试不存在。")
    return simulation_view(simulation, reveal=bool(simulation and simulation.get("status") == "finished"))


@app.delete("/api/simulations/{simulation_id}")
def cancel_simulation_endpoint(simulation_id: str, user_id: str = "local-user", context: AuthContext = Depends(require_user)) -> dict[str, str]:
    simulation = get_simulation(simulation_id)
    if simulation is None:
        raise HTTPException(status_code=404, detail="模拟考试不存在。")
    normalized_user_id = _user_id(context, user_id)
    if simulation.get("user_id") != normalized_user_id:
        # Keep the pre-account compatibility response for old callers, while
        # authenticated users receive a non-enumerating 404.
        if context.legacy:
            raise HTTPException(status_code=403, detail="没有权限取消这套模拟考。")
        raise HTTPException(status_code=404, detail="模拟考试不存在。")
    if simulation.get("status") == "finished":
        raise HTTPException(status_code=409, detail="已交卷的模拟考不能取消。")
    if not delete_simulation(simulation_id):
        raise HTTPException(status_code=409, detail="模拟考状态已发生变化，请刷新后重试。")
    return {"id": simulation_id, "status": "cancelled"}


@app.post("/api/simulations/{simulation_id}/submit")
def submit_simulation(simulation_id: str, payload: SimulationSubmitRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    simulation = get_simulation(simulation_id)
    if simulation is None:
        raise HTTPException(status_code=404, detail="模拟考试不存在。")
    owner_id = _user_id(context, payload.user_id)
    if simulation.get("user_id") != owner_id:
        raise HTTPException(status_code=404, detail="模拟考试不存在。")
    if simulation.get("status") == "finished":
        return simulation_view(simulation, reveal=True)
    _validate_answer_maps(payload.answers, payload.self_grades, payload.attachment_ids, set(simulation["question_ids"]))
    total = 0.0
    for question_id in simulation["question_ids"]:
        question = _question_or_404(question_id)
        effective_question = _effective_question(question, _question_override(question, owner_id))
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
                "user_id": owner_id,
                "question_id": question_id,
                "answer": answer,
                "correct": result.get("correct"),
                "status": result["status"],
                "score": result["score"],
                "max_score": result["max_score"],
                "confidence": result["confidence"],
                "error_type": result.get("error_type", ""),
                "concepts": effective_question.get("concept_ids", []),
                "duration_seconds": 0,
                "hints_used": 0,
                "mode": "simulation",
            }
        )
        link_attachments(
            payload.attachment_ids.get(question_id, []),
            user_id=owner_id,
            question_id=question_id,
            attempt_id=attempt_id,
            simulation_id=simulation_id,
        )
    finish_simulation(simulation_id, total)
    return simulation_view(get_simulation(simulation_id), reveal=True)


@app.get("/api/llm/settings")
def llm_settings(context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    return public_settings(context.user_id if not context.legacy else "local-user")


@app.post("/api/llm/settings")
def save_llm_settings(payload: ModelSettingsRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    try:
        return save_settings(payload.base_url, payload.model, payload.api_key, payload.clear_api_key, _user_id(context))
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/llm/models")
async def llm_models(payload: ModelFetchRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    try:
        models = await fetch_models(payload.base_url, payload.api_key, _user_id(context))
        return {"models": models}
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/server/settings")
def get_server_settings(_: AuthContext = Depends(require_user)) -> dict[str, Any]:
    return server_settings()


@app.post("/api/server/settings")
def update_server_settings(payload: ServerSettingsRequest, _: AuthContext = Depends(require_admin)) -> dict[str, Any]:
    try:
        return save_server_settings(payload.host, payload.port, payload.public_url)
    except ServerSettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/questions/{question_id}/tutor")
async def tutor(question_id: str, payload: TutorRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    question = _question_or_404(question_id)
    try:
        return await tutor_response(question, payload.answer, payload.request, user_id=_user_id(context, payload.user_id))
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/questions/{question_id}/hint")
async def question_hint(question_id: str, payload: TutorRequest, context: AuthContext = Depends(require_user)) -> dict[str, Any]:
    question = _question_or_404(question_id)
    try:
        return await hint_response(question, payload.answer, payload.request or "给我解题思路", user_id=_user_id(context, payload.user_id))
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
