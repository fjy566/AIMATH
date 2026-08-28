from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, Response, status

from app.database import get_connection, utc_now


SESSION_COOKIE = "ai_math_session"
CSRF_COOKIE = "ai_math_csrf"
SESSION_TTL = timedelta(days=14)
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
# Keep login identifiers predictable across browsers and avoid visually
# confusable Unicode usernames; display_name remains fully Unicode.
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW_SECONDS = 300
RATE_LIMIT_MAX_ATTEMPTS = 12


class AuthValidationError(ValueError):
    """Raised when a user supplied identity or password is not acceptable."""


@dataclass(frozen=True)
class AuthContext:
    user: dict[str, Any]
    session_hash: str | None = None
    legacy: bool = False

    @property
    def user_id(self) -> str:
        return str(self.user.get("id", ""))

    @property
    def role(self) -> str:
        return str(self.user.get("role", "user"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_after(delta: timedelta) -> str:
    return (_now() + delta).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    params = (2**14, 8, 1)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=params[0], r=params[1], p=params[2], dklen=64)
    return f"scrypt${params[0]}${params[1]}${params[2]}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_n, raw_r, raw_p, raw_salt, raw_digest = str(encoded).split("$", 5)
        if algorithm != "scrypt":
            return False
        n, r, p = int(raw_n), int(raw_r), int(raw_p)
        if n < 2**12 or n > 2**18 or r < 1 or r > 32 or p < 1 or p > 8:
            return False
        candidate = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(raw_salt), n=n, r=r, p=p, dklen=len(_unb64(raw_digest)))
        return hmac.compare_digest(candidate, _unb64(raw_digest))
    except (TypeError, ValueError, OverflowError):
        return False


def normalize_username(value: str) -> str:
    username = str(value or "").strip().casefold()
    if not USERNAME_PATTERN.fullmatch(username):
        raise AuthValidationError("用户名需为 3–32 个字母、数字、下划线或短横线。")
    return username


def normalize_email(value: str) -> str:
    email = str(value or "").strip().casefold()
    if email and (len(email) > 254 or not EMAIL_PATTERN.fullmatch(email)):
        raise AuthValidationError("请输入有效的邮箱地址，或留空。")
    return email


def validate_password(value: str) -> str:
    password = str(value or "")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise AuthValidationError(f"密码至少需要 {PASSWORD_MIN_LENGTH} 个字符。")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise AuthValidationError(f"密码不能超过 {PASSWORD_MAX_LENGTH} 个字符。")
    if any(character.isspace() for character in password):
        raise AuthValidationError("密码不能包含空格。")
    return password


def _json_or_default(value: Any, default: Any) -> Any:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, type(default)) else default
    except (TypeError, json.JSONDecodeError):
        return default


def public_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    preferences = _json_or_default(item.pop("preferences_json", "{}"), {})
    item.pop("password_hash", None)
    # Keep session internals out of every user-facing payload, even if a
    # future query passes a joined auth row by mistake.
    for sensitive_key in ("id_hash", "csrf_hash", "session_hash", "ip_address", "user_agent", "expires_at", "last_seen_at"):
        item.pop(sensitive_key, None)
    item["preferences"] = preferences
    item["is_active"] = bool(item.get("is_active", 0))
    return item


def user_count() -> int:
    with get_connection() as connection:
        row = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
    return int(row["count"] if row else 0)


def has_admin() -> bool:
    with get_connection() as connection:
        row = connection.execute("SELECT 1 FROM users WHERE role = 'admin' AND is_active = 1 LIMIT 1").fetchone()
    return row is not None


def get_user(user_id: str, *, include_inactive: bool = False) -> dict[str, Any] | None:
    query = "SELECT * FROM users WHERE id = ?"
    params: list[Any] = [user_id]
    if not include_inactive:
        query += " AND is_active = 1"
    with get_connection() as connection:
        row = connection.execute(query, params).fetchone()
    return public_user(row) if row is not None else None


def list_users() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM users ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END, created_at ASC"
        ).fetchall()
    users = [public_user(row) for row in rows]
    # The admin directory only needs identity and status metadata; personal
    # study preferences stay private to the account settings endpoint.
    for user in users:
        user.pop("preferences", None)
    return users


def _audit(
    connection: sqlite3.Connection,
    action: str,
    *,
    user_id: str | None = None,
    actor_user_id: str | None = None,
    target_user_id: str | None = None,
    ip_address: str = "",
    detail: str = "",
) -> None:
    connection.execute(
        """
        INSERT INTO auth_audit_events(user_id, actor_user_id, action, target_user_id, ip_address, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, actor_user_id, action, target_user_id, ip_address[:64], detail[:500], utc_now()),
    )


def create_user(
    username: str,
    password: str,
    *,
    email: str = "",
    display_name: str = "",
    ip_address: str = "",
) -> tuple[dict[str, Any], bool]:
    normalized_username = normalize_username(username)
    normalized_email = normalize_email(email)
    normalized_password = validate_password(password)
    display = str(display_name or "").strip()[:80] or normalized_username
    user_id = secrets.token_hex(16)
    now = utc_now()
    password_hash = hash_password(normalized_password)
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        is_first = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"] == 0
        role = "admin" if is_first else "user"
        try:
            connection.execute(
                """
                INSERT INTO users(id, username, email, display_name, password_hash, role, is_active, preferences_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, '{}', ?, ?)
                """,
                (user_id, normalized_username, normalized_email, display, password_hash, role, now, now),
            )
        except sqlite3.IntegrityError as exc:
            detail = str(exc).lower()
            if "email" in detail:
                raise AuthValidationError("该邮箱已经注册。") from exc
            raise AuthValidationError("该用户名已经注册。") from exc
        _migrate_legacy_local_data(connection, user_id, ip_address=ip_address)
        _audit(connection, "register", user_id=user_id, target_user_id=user_id, ip_address=ip_address, detail=f"role={role}")
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return (public_user(row) if row else {}, is_first)


def _migrate_legacy_local_data(connection: sqlite3.Connection, user_id: str, *, ip_address: str = "") -> None:
    """Move the pre-auth local workspace into the first registered account."""
    if connection.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
        return
    tables = (
        "attempts",
        "question_classification_overrides",
        "simulations",
        "practice_sessions",
        "answer_attachments",
        "notes",
        "note_versions",
        "note_assets",
        "workbench_template_overrides",
        "workbench_template_versions",
    )
    moved = 0
    for table in tables:
        try:
            cursor = connection.execute(f"UPDATE {table} SET user_id = ? WHERE user_id = ?", (user_id, "local-user"))
            moved += cursor.rowcount
        except sqlite3.OperationalError:
            # Keep startup compatible with databases created by much older builds.
            continue
    # LLM configuration predates accounts and was stored under one global key.
    # Copy it to the first account so registration does not silently discard a
    # learner's existing model connection. Keep the legacy key for rollback and
    # old CLI callers.
    try:
        legacy_llm = connection.execute("SELECT value FROM settings WHERE key = ?", ("llm_settings",)).fetchone()
        scoped_key = f"llm_settings:{user_id}"
        scoped_exists = connection.execute("SELECT 1 FROM settings WHERE key = ?", (scoped_key,)).fetchone()
        if legacy_llm is not None and scoped_exists is None:
            connection.execute(
                "INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
                (scoped_key, legacy_llm["value"], utc_now()),
            )
    except sqlite3.OperationalError:
        pass
    if moved:
        _audit(connection, "legacy-data-migrated", user_id=user_id, target_user_id=user_id, ip_address=ip_address, detail=f"rows={moved}")


def authenticate_user(identifier: str, password: str, *, ip_address: str = "") -> dict[str, Any] | None:
    login = str(identifier or "").strip().casefold()
    if not login or not password:
        return None
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE (username = ? OR (email <> '' AND email = ?)) AND is_active = 1",
            (login, login),
        ).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            if row is not None:
                _audit(connection, "login-failed", target_user_id=row["id"], ip_address=ip_address)
            return None
        now = utc_now()
        connection.execute("UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?", (now, now, row["id"]))
        _audit(connection, "login", user_id=row["id"], target_user_id=row["id"], ip_address=ip_address)
        refreshed = connection.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
    return public_user(refreshed) if refreshed is not None else None


def _request_ip(request: Request) -> str:
    return (request.client.host if request.client else "")[:64]


def check_rate_limit(request: Request, bucket: str) -> None:
    """Apply a small in-process guard to login and registration bursts."""
    key = f"{bucket}:{_request_ip(request)}"
    now = time.monotonic()
    recent = [stamp for stamp in _RATE_LIMIT_BUCKETS.get(key, []) if now - stamp < RATE_LIMIT_WINDOW_SECONDS]
    if len(recent) >= RATE_LIMIT_MAX_ATTEMPTS:
        _RATE_LIMIT_BUCKETS[key] = recent
        raise HTTPException(status_code=429, detail="尝试次数过多，请稍后再试。", headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)})
    recent.append(now)
    _RATE_LIMIT_BUCKETS[key] = recent
    if len(_RATE_LIMIT_BUCKETS) > 1000:
        for old_key, stamps in list(_RATE_LIMIT_BUCKETS.items()):
            if not stamps or now - stamps[-1] >= RATE_LIMIT_WINDOW_SECONDS:
                _RATE_LIMIT_BUCKETS.pop(old_key, None)


def create_session(user_id: str, request: Request) -> tuple[str, str, str]:
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    now = utc_now()
    expires_at = _iso_after(SESSION_TTL)
    with get_connection() as connection:
        connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now,))
        connection.execute(
            """
            INSERT INTO auth_sessions(id_hash, user_id, csrf_hash, expires_at, created_at, last_seen_at, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (token_hash, user_id, _hash_token(csrf_token), expires_at, now, now, _request_ip(request), (request.headers.get("user-agent") or "")[:300]),
        )
        connection.execute(
            "DELETE FROM auth_sessions WHERE user_id = ? AND id_hash <> ? AND expires_at <= ?",
            (user_id, token_hash, now),
        )
    return token, csrf_token, expires_at


def _cookie_secure(request: Request) -> bool:
    return request.url.scheme == "https"


def set_session_cookies(response: Response, request: Request, token: str, csrf_token: str, max_age: int = int(SESSION_TTL.total_seconds())) -> None:
    secure = _cookie_secure(request)
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=secure, samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE, csrf_token, max_age=max_age, httponly=False, secure=secure, samesite="lax", path="/")


def set_csrf_cookie(response: Response, request: Request, csrf_token: str, max_age: int = int(SESSION_TTL.total_seconds())) -> None:
    response.set_cookie(CSRF_COOKIE, csrf_token, max_age=max_age, httponly=False, secure=_cookie_secure(request), samesite="lax", path="/")


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _legacy_context(request: Request) -> AuthContext:
    # This temporary compatibility mode keeps an existing unclaimed local
    # workspace usable. The first registration closes it permanently.
    requested = request.query_params.get("user_id", "local-user").strip()[:100] or "local-user"
    return AuthContext(
        user={"id": requested, "username": requested, "display_name": "本地学习者", "role": "admin", "is_active": True, "legacy": True},
        legacy=True,
    )


def _session_context(request: Request) -> AuthContext | None:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        return None
    token_hash = _hash_token(token)
    now_dt = _now()
    now = now_dt.isoformat()
    touch_before = (now_dt - timedelta(seconds=60)).isoformat()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT u.* FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id_hash = ? AND s.expires_at > ? AND u.is_active = 1
            """,
            (token_hash, now),
        ).fetchone()
        if row is None:
            connection.execute("DELETE FROM auth_sessions WHERE id_hash = ?", (token_hash,))
            return None
        # Avoid a SQLite write on every parallel API read while still keeping
        # the device activity timestamp useful in the settings page.
        connection.execute(
            "UPDATE auth_sessions SET last_seen_at = ? WHERE id_hash = ? AND last_seen_at < ?",
            (now, token_hash, touch_before),
        )
    return AuthContext(user=public_user(row), session_hash=token_hash)


def require_user(request: Request) -> AuthContext:
    context = _session_context(request)
    if context is None:
        if user_count() == 0:
            return _legacy_context(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录。", headers={"WWW-Authenticate": "Cookie"})
    if request.method not in SAFE_METHODS:
        csrf = request.headers.get("X-CSRF-Token", "")
        with get_connection() as connection:
            row = connection.execute("SELECT csrf_hash FROM auth_sessions WHERE id_hash = ?", (context.session_hash,)).fetchone()
        if row is None or not csrf or not hmac.compare_digest(_hash_token(csrf), row["csrf_hash"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请求校验已失效，请刷新页面后重试。")
    return context


def require_admin(context: AuthContext = Depends(require_user)) -> AuthContext:
    if context.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有管理员可以执行此操作。")
    return context


def current_csrf_token(request: Request, context: AuthContext) -> str:
    token = request.cookies.get(CSRF_COOKIE, "")
    if token:
        with get_connection() as connection:
            row = connection.execute("SELECT csrf_hash FROM auth_sessions WHERE id_hash = ?", (context.session_hash,)).fetchone()
        if row is not None and hmac.compare_digest(_hash_token(token), row["csrf_hash"]):
            return token
    token = secrets.token_urlsafe(32)
    with get_connection() as connection:
        connection.execute("UPDATE auth_sessions SET csrf_hash = ? WHERE id_hash = ?", (_hash_token(token), context.session_hash))
    return token


def list_sessions(user_id: str, current_session_hash: str | None = None) -> list[dict[str, Any]]:
    now = utc_now()
    with get_connection() as connection:
        connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now,))
        rows = connection.execute(
            "SELECT id_hash, created_at, last_seen_at, expires_at, ip_address, user_agent FROM auth_sessions WHERE user_id = ? ORDER BY last_seen_at DESC",
            (user_id,),
        ).fetchall()
    return [
        {
            "id": row["id_hash"][:12],
            "current": bool(current_session_hash and hmac.compare_digest(row["id_hash"], current_session_hash)),
            "created_at": row["created_at"],
            "last_seen_at": row["last_seen_at"],
            "expires_at": row["expires_at"],
            "ip_address": row["ip_address"],
            "user_agent": row["user_agent"],
        }
        for row in rows
    ]


def revoke_other_sessions(user_id: str, current_session_hash: str | None) -> int:
    with get_connection() as connection:
        if current_session_hash:
            cursor = connection.execute("DELETE FROM auth_sessions WHERE user_id = ? AND id_hash <> ?", (user_id, current_session_hash))
        else:
            cursor = connection.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
    return int(cursor.rowcount)


def revoke_session(session_hash: str, user_id: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM auth_sessions WHERE id_hash = ? AND user_id = ?", (session_hash, user_id))
    return cursor.rowcount > 0


def update_profile(user_id: str, *, display_name: str, email: str) -> dict[str, Any]:
    normalized_email = normalize_email(email)
    display = str(display_name or "").strip()[:80]
    if not display:
        raise AuthValidationError("显示名称不能为空。")
    with get_connection() as connection:
        try:
            connection.execute(
                "UPDATE users SET display_name = ?, email = ?, updated_at = ? WHERE id = ? AND is_active = 1",
                (display, normalized_email, utc_now(), user_id),
            )
        except sqlite3.IntegrityError as exc:
            raise AuthValidationError("该邮箱已经被其他账户使用。") from exc
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise AuthValidationError("账户不存在。")
    return public_user(row)


def get_preferences(user_id: str) -> dict[str, Any]:
    with get_connection() as connection:
        row = connection.execute("SELECT preferences_json FROM users WHERE id = ?", (user_id,)).fetchone()
    preferences = _json_or_default(row["preferences_json"] if row else "{}", {})
    defaults = {"theme": "system", "default_exam_type": "数学二", "daily_goal": 30, "practice_count": 15, "sound_enabled": False}
    return {**defaults, **preferences}


def update_preferences(user_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
    allowed = {"theme", "default_exam_type", "daily_goal", "practice_count", "sound_enabled"}
    current = get_preferences(user_id)
    current.update({key: value for key, value in preferences.items() if key in allowed})
    if current["theme"] not in {"system", "light", "dark"}:
        raise AuthValidationError("主题只能选择跟随系统、浅色或深色。")
    if current["default_exam_type"] not in {"数学二"}:
        raise AuthValidationError("当前只支持数学二。")
    current["daily_goal"] = max(5, min(240, int(current["daily_goal"])))
    current["practice_count"] = max(1, min(15, int(current["practice_count"])))
    current["sound_enabled"] = bool(current["sound_enabled"])
    with get_connection() as connection:
        connection.execute("UPDATE users SET preferences_json = ?, updated_at = ? WHERE id = ?", (json.dumps(current, ensure_ascii=False), utc_now(), user_id))
    return current


def change_password(user_id: str, current_password: str, new_password: str, *, ip_address: str = "") -> None:
    validate_password(new_password)
    with get_connection() as connection:
        row = connection.execute("SELECT password_hash FROM users WHERE id = ? AND is_active = 1", (user_id,)).fetchone()
        if row is None or not verify_password(current_password, row["password_hash"]):
            raise AuthValidationError("当前密码不正确。")
        connection.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?", (hash_password(new_password), utc_now(), user_id))
        connection.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
        _audit(connection, "password-changed", user_id=user_id, actor_user_id=user_id, target_user_id=user_id, ip_address=ip_address)


def update_user_by_admin(target_user_id: str, *, role: str, is_active: bool, display_name: str, actor_user_id: str, ip_address: str = "") -> dict[str, Any]:
    if role not in {"user", "admin"}:
        raise AuthValidationError("角色只能是普通用户或管理员。")
    display = str(display_name or "").strip()[:80]
    if not display:
        raise AuthValidationError("显示名称不能为空。")
    with get_connection() as connection:
        target = connection.execute("SELECT * FROM users WHERE id = ?", (target_user_id,)).fetchone()
        if target is None:
            raise AuthValidationError("账户不存在。")
        if target_user_id == actor_user_id and (not is_active or role != "admin"):
            raise AuthValidationError("不能停用或降级当前登录的管理员账户。")
        if target["role"] == "admin" and (role != "admin" or not is_active):
            admin_count = connection.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND is_active = 1").fetchone()["count"]
            if admin_count <= 1:
                raise AuthValidationError("系统至少需要保留一名启用中的管理员。")
        connection.execute(
            "UPDATE users SET role = ?, is_active = ?, display_name = ?, updated_at = ? WHERE id = ?",
            (role, int(is_active), display, utc_now(), target_user_id),
        )
        if not is_active:
            connection.execute("DELETE FROM auth_sessions WHERE user_id = ?", (target_user_id,))
        _audit(connection, "admin-user-updated", user_id=actor_user_id, actor_user_id=actor_user_id, target_user_id=target_user_id, ip_address=ip_address, detail=f"role={role};active={int(is_active)}")
        row = connection.execute("SELECT * FROM users WHERE id = ?", (target_user_id,)).fetchone()
    return public_user(row) if row else {}


def list_audit_events(limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(200, int(limit)))
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT a.*, u.username AS user_username, actor.username AS actor_username, target.username AS target_username
            FROM auth_audit_events a
            LEFT JOIN users u ON u.id = a.user_id
            LEFT JOIN users actor ON actor.id = a.actor_user_id
            LEFT JOIN users target ON target.id = a.target_user_id
            ORDER BY a.created_at DESC LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def admin_overview() -> dict[str, Any]:
    with get_connection() as connection:
        users = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        active_users = connection.execute("SELECT COUNT(*) AS count FROM users WHERE is_active = 1").fetchone()["count"]
        admins = connection.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND is_active = 1").fetchone()["count"]
        sessions = connection.execute("SELECT COUNT(*) AS count FROM auth_sessions WHERE expires_at > ?", (utc_now(),)).fetchone()["count"]
        attempts = connection.execute("SELECT COUNT(*) AS count FROM attempts").fetchone()["count"]
        notes = connection.execute("SELECT COUNT(*) AS count FROM notes").fetchone()["count"]
    return {"users": int(users), "active_users": int(active_users), "admins": int(admins), "active_sessions": int(sessions), "attempts": int(attempts), "notes": int(notes)}
