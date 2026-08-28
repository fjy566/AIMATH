from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.database import get_setting, set_setting


class LLMError(RuntimeError):
    pass


MAX_MODEL_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_CHAT_RESPONSE_BYTES = 8 * 1024 * 1024
BLOCKED_METADATA_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.google.com",
    "instance-data.ec2.internal",
}


def _valid_base_url(value: str) -> str:
    base_url = (value or "").strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise LLMError("Base URL 必须是 http:// 或 https:// 开头的地址。")
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if hostname in BLOCKED_METADATA_HOSTS:
        raise LLMError("为避免误访问云主机元数据，不能使用该模型服务地址。")
    try:
        parsed_port = parsed.port
    except ValueError as exc:
        raise LLMError("Base URL 的端口无效。") from exc
    if parsed_port is not None and not 1 <= parsed_port <= 65535:
        raise LLMError("Base URL 的端口必须在 1–65535 之间。")
    return base_url


def _api_root(base_url: str) -> str:
    base_url = _valid_base_url(base_url)
    if base_url.endswith("/chat/completions"):
        return base_url[: -len("/chat/completions")]
    if base_url.endswith("/models"):
        return base_url[: -len("/models")]
    return base_url if base_url.endswith("/v1") else f"{base_url}/v1"


def _headers(api_key: str) -> dict[str, str]:
    result = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        result["Authorization"] = f"Bearer {api_key}"
    return result


def _settings(user_id: str = "local-user") -> dict[str, str]:
    key = "llm_settings" if str(user_id or "local-user") == "local-user" else f"llm_settings:{str(user_id).strip()}"
    value = get_setting(key, {})
    return value if isinstance(value, dict) else {}


def mask_api_key(value: str) -> str:
    if not value:
        return ""
    return "••••••••" + value[-4:]


def public_settings(user_id: str = "local-user") -> dict[str, Any]:
    settings = _settings(user_id)
    key = settings.get("api_key", "")
    return {
        "base_url": settings.get("base_url", ""),
        "model": settings.get("model", ""),
        "api_key_set": bool(key),
        "api_key_masked": mask_api_key(key),
    }


def save_settings(base_url: str, model: str, api_key: str | None = None, clear_api_key: bool = False, user_id: str = "local-user") -> dict[str, Any]:
    settings = _settings(user_id)
    if base_url.strip():
        _valid_base_url(base_url)
    settings["base_url"] = base_url.strip().rstrip("/")
    settings["model"] = (model or "").strip()
    if clear_api_key:
        settings["api_key"] = ""
    elif api_key is not None and api_key.strip():
        settings["api_key"] = api_key.strip()
    key = "llm_settings" if str(user_id or "local-user") == "local-user" else f"llm_settings:{str(user_id).strip()}"
    set_setting(key, settings)
    return public_settings(user_id)


async def fetch_models(base_url: str | None = None, api_key: str | None = None, user_id: str = "local-user") -> list[dict[str, Any]]:
    settings = _settings(user_id)
    resolved_base = (base_url or settings.get("base_url", "")).strip()
    resolved_key = api_key if api_key is not None else settings.get("api_key", "")
    root = _api_root(resolved_base)
    url = f"{root}/models"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0), follow_redirects=False, trust_env=False) as client:
            response = await client.get(url, headers=_headers(resolved_key))
        response.raise_for_status()
        if len(response.content) > MAX_MODEL_RESPONSE_BYTES:
            raise LLMError("模型列表响应过大，已停止读取。")
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300] if exc.response is not None else str(exc)
        raise LLMError(f"模型列表请求失败（HTTP {exc.response.status_code}）：{detail}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise LLMError(f"无法连接模型服务：{exc}") from exc
    data = payload.get("data", payload if isinstance(payload, list) else [])
    models = []
    for item in data:
        if isinstance(item, str):
            models.append({"id": item, "object": "model"})
        elif isinstance(item, dict) and item.get("id"):
            models.append({"id": str(item["id"]), "object": item.get("object", "model"), "owned_by": item.get("owned_by", "")})
    return sorted(models, key=lambda item: item["id"].lower())


async def chat_completion(messages: list[dict[str, Any]], *, model: str | None = None, temperature: float = 0.2, user_id: str = "local-user") -> str:
    settings = _settings(user_id)
    base_url = settings.get("base_url", "")
    api_key = settings.get("api_key", "")
    resolved_model = model or settings.get("model", "")
    if not base_url or not resolved_model:
        raise LLMError("请先在设置页填写 Base URL 并选择模型。")
    url = f"{_api_root(base_url)}/chat/completions"
    payload = {"model": resolved_model, "messages": messages, "temperature": temperature}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=8.0), follow_redirects=False, trust_env=False) as client:
            response = await client.post(url, headers=_headers(api_key), json=payload)
        response.raise_for_status()
        if len(response.content) > MAX_CHAT_RESPONSE_BYTES:
            raise LLMError("模型响应过大，已停止读取。")
        data = response.json()
        return str(data["choices"][0]["message"].get("content", "")).strip()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300] if exc.response is not None else str(exc)
        raise LLMError(f"模型调用失败（HTTP {exc.response.status_code}）：{detail}") from exc
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
        raise LLMError(f"模型响应无效：{exc}") from exc


async def tutor_response(question: dict[str, Any], user_answer: str, request: str = "分析我的错误", user_id: str = "local-user") -> dict[str, Any]:
    solution = question.get("solution_markdown") or "当前来源没有提供该题解析。"
    messages = [
        {
            "role": "system",
            "content": (
                "你是考研数学辅导老师。只能依据用户提供的题目、答案和解析回答；如果来源没有解析，"
                "必须明确说没有来源解析，不得编造。先诊断错误类型，再给一个不直接泄露完整答案的提示，"
                "最后给出下一步训练建议。用简体中文，返回 JSON："
                '{"diagnosis":"","error_type":"","hint":"","explanation":"","next_step":""}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"请求：{request}\n题目：\n{question.get('question_markdown', '')}\n"
                f"标准答案：\n{question.get('answer_markdown', '')}\n来源解析：\n{solution}\n"
                f"我的作答：\n{user_answer or '未作答'}"
            ),
        },
    ]
    content = await chat_completion(messages, temperature=0.15, user_id=user_id)
    return {"content": content, "model": _settings(user_id).get("model", "")}


async def hint_response(question: dict[str, Any], user_answer: str = "", request: str = "给我解题思路", user_id: str = "local-user") -> dict[str, Any]:
    """Return a progressive hint for an active training question.

    The source answer/solution is supplied as context so the configured model
    can stay grounded, but the prompt asks it to stop before dumping a full
    derivation.  The source solution remains separately available through the
    reveal endpoint, so an unavailable model never blocks reviewing the real
    answer.
    """
    solution = question.get("solution_markdown") or "当前来源没有提供该题解析。"
    messages = [
        {
            "role": "system",
            "content": (
                "你是考研数学训练陪练。只依据题目、标准答案和来源解析回答，不得编造题设。"
                "用户在做题中请求思路：先指出应识别的知识点和第一步，随后给出不超过三步的分层提示，"
                "不要直接抄出完整答案；若用户已经给出步骤，只指出下一处检查点。"
                "如果来源没有解析，必须明确说明‘当前来源没有提供解析’，但仍可给出基于题面定义的思路。"
                "用简体中文，使用清晰的短段落或编号列表。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"请求：{request}\n题目：\n{question.get('question_markdown', '')}\n"
                f"标准答案（仅供核对方向）：\n{question.get('answer_markdown', '')}\n"
                f"来源解析：\n{solution}\n我的当前作答：\n{user_answer or '尚未作答'}"
            ),
        },
    ]
    content = await chat_completion(messages, temperature=0.25, user_id=user_id)
    return {"content": content, "model": _settings(user_id).get("model", "")}
