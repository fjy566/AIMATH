from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

import httpx

from app.database import get_setting, set_setting


class LLMError(RuntimeError):
    pass


MAX_MODEL_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_CHAT_RESPONSE_BYTES = 8 * 1024 * 1024
CHAT_RESPONSE_TIMEOUT_SECONDS = 300.0
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


def _chat_target(model: str | None, user_id: str) -> tuple[str, str, str]:
    settings = _settings(user_id)
    base_url = settings.get("base_url", "")
    api_key = settings.get("api_key", "")
    resolved_model = model or settings.get("model", "")
    if not base_url or not resolved_model:
        raise LLMError("请先在设置页填写 Base URL 并选择模型。")
    return f"{_api_root(base_url)}/chat/completions", api_key, resolved_model


def _message_text(message: dict[str, Any]) -> str:
    """Extract only the provider's final content, never its hidden reasoning."""
    content = _content_text(message.get("content")).strip()
    if not content:
        return ""
    # A few gateways concatenate their private reasoning into content using
    # the same tags used by chat templates. Keep only the final text; a
    # reasoning-only message becomes empty and is rejected by chat_completion.
    content = re.sub(r"<(?:think|analysis)>[\s\S]*?</(?:think|analysis)>", "", content, flags=re.IGNORECASE).strip()
    if re.match(r"^<(?:think|analysis)>[\s\S]*$", content, flags=re.IGNORECASE):
        return ""
    return content


def _content_text(value: Any) -> str:
    """Flatten the text shapes used by OpenAI-compatible multimodal gateways."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "".join(_content_text(item) for item in value)
    if isinstance(value, dict):
        for key in ("text", "value", "content", "output_text"):
            if key in value:
                return _content_text(value[key])
    return ""


def parse_vision_grade(content: str) -> dict[str, Any] | None:
    """Normalize a model's fenced or plain JSON handwriting judgement."""
    text = str(content or "").strip()
    fenced = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text, flags=re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except (TypeError, ValueError):
            return None
    if not isinstance(parsed, dict):
        return None
    raw_verdict = parsed.get("verdict", parsed.get("is_correct", parsed.get("correct")))
    if isinstance(raw_verdict, bool):
        verdict = "correct" if raw_verdict else "incorrect"
    else:
        normalized = str(raw_verdict or "").strip().lower()
        if normalized in {"correct", "true", "yes", "对", "正确", "一致"}:
            verdict = "correct"
        elif normalized in {"incorrect", "false", "no", "错", "错误", "不一致"}:
            verdict = "incorrect"
        else:
            verdict = "unclear"
    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "recognized_answer": _content_text(parsed.get("recognized_answer", parsed.get("answer", ""))).strip(),
        "verdict": verdict,
        "confidence": confidence,
        "explanation": _content_text(parsed.get("explanation", parsed.get("reason", ""))).strip(),
    }


def _stream_chunk_text(chunk: Any) -> tuple[str, str]:
    """Return reasoning/content text while tolerating usage and heartbeat chunks."""
    if not isinstance(chunk, dict):
        raise LLMError("模型流式响应不是 JSON 对象。")
    error = chunk.get("error")
    if error:
        if isinstance(error, dict):
            message = error.get("message") or error.get("detail") or json.dumps(error, ensure_ascii=False)
        else:
            message = str(error)
        raise LLMError(f"模型服务返回错误：{message}")
    choices = chunk.get("choices")
    # OpenAI-compatible services commonly send an empty choices array for the
    # terminal usage block. It is metadata, not a malformed model response.
    if choices == []:
        return "", ""
    if not isinstance(choices, list):
        return "", ""
    reasoning_parts: list[str] = []
    content_parts: list[str] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta") or choice.get("message") or {}
        if not isinstance(delta, dict):
            continue
        reasoning_parts.append(_content_text(delta.get("reasoning_content") or delta.get("reasoning")))
        content_parts.append(_content_text(delta.get("content") if "content" in delta else choice.get("text")))
    return "".join(reasoning_parts), "".join(content_parts)


async def chat_completion(messages: list[dict[str, Any]], *, model: str | None = None, temperature: float = 0.2, user_id: str = "local-user") -> str:
    url, api_key, resolved_model = _chat_target(model, user_id)
    # Do not impose a provider-side token ceiling. Reasoning-capable models
    # decide their own budget; only the response byte guard above protects the
    # application from an unexpectedly large payload.
    payload = {"model": resolved_model, "messages": messages, "temperature": temperature}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(CHAT_RESPONSE_TIMEOUT_SECONDS, connect=8.0), follow_redirects=False, trust_env=False) as client:
            response = await client.post(url, headers=_headers(api_key), json=payload)
        response.raise_for_status()
        if len(response.content) > MAX_CHAT_RESPONSE_BYTES:
            raise LLMError("模型响应过大，已停止读取。")
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise LLMError("模型没有返回可用的回答。")
        message = choices[0].get("message") or choices[0].get("delta") or {"content": choices[0].get("text")}
        if not isinstance(message, dict):
            raise LLMError("模型回答格式不受支持。")
        content = _message_text(message)
        if not content:
            raise LLMError("模型只返回了思考过程，没有返回最终答案，请重试。")
        return content
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300] if exc.response is not None else str(exc)
        raise LLMError(f"模型调用失败（HTTP {exc.response.status_code}）：{detail}") from exc
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
        raise LLMError(f"模型响应无效：{exc}") from exc


async def chat_completion_stream(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    user_id: str = "local-user",
) -> AsyncIterator[dict[str, str]]:
    """Proxy OpenAI-compatible SSE chunks without imposing a read timeout."""
    url, api_key, resolved_model = _chat_target(model, user_id)
    payload = {
        "model": resolved_model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    timeout = httpx.Timeout(connect=8.0, read=None, write=30.0, pool=8.0)
    total_bytes = 0
    reasoning_started = False
    saw_content = False
    reasoning_parts: list[str] = []
    try:
        async with asyncio.timeout(CHAT_RESPONSE_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
                async with client.stream("POST", url, headers=_headers(api_key), json=payload) as response:
                    if response.status_code >= 400:
                        detail = (await response.aread()).decode("utf-8", errors="replace")[:300]
                        raise LLMError(f"模型调用失败（HTTP {response.status_code}）：{detail}")
                    yield {"type": "start", "model": resolved_model}
                    async for line in response.aiter_lines():
                        total_bytes += len(line.encode("utf-8")) + 1
                        if total_bytes > MAX_CHAT_RESPONSE_BYTES:
                            raise LLMError("模型响应过大，已停止读取。")
                        stripped = line.strip()
                        if not stripped or stripped.startswith(":"):
                            continue
                        raw = stripped[5:].strip() if stripped.startswith("data:") else stripped
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(raw)
                        except (ValueError, TypeError) as exc:
                            raise LLMError(f"模型流式响应无效：{exc}") from exc
                        reasoning, content = _stream_chunk_text(chunk)
                        if reasoning:
                            reasoning_parts.append(reasoning)
                        if reasoning and not reasoning_started:
                            reasoning_started = True
                            yield {"type": "reasoning", "delta": ""}
                        if content:
                            saw_content = True
                            yield {"type": "content", "delta": content}
        if not saw_content:
            # Some reasoning-first gateways close the stream after emitting
            # only `reasoning_content` (or `choices: []` usage metadata). Give
            # them one compatible non-stream completion chance so the caller
            # still receives the final answer instead of an empty stream.
            try:
                fallback = await chat_completion(
                    messages,
                    model=resolved_model,
                    temperature=temperature,
                    user_id=user_id,
                )
            except LLMError as exc:
                raise LLMError("模型完成了思考，但没有返回最终答案，请重试。") from exc
            if fallback.strip():
                yield {"type": "content", "delta": fallback}
                saw_content = True
            elif reasoning_parts:
                raise LLMError("模型完成了思考，但没有返回最终答案，请重试。")
            else:
                raise LLMError("模型没有返回可用的回答，请重试。")
        yield {"type": "done"}
    except LLMError:
        raise
    except httpx.HTTPError as exc:
        raise LLMError(f"模型流式连接失败：{exc}") from exc
    except TimeoutError as exc:
        raise LLMError("模型响应超过 5 分钟，请重试或检查模型服务。") from exc


def _tutor_messages(
    question: dict[str, Any],
    user_answer: str,
    request: str,
    image_data_urls: list[str] | None = None,
) -> list[dict[str, Any]]:
    solution = question.get("solution_markdown") or "当前来源没有提供该题解析。"
    user_text = (
        f"请求：{request}\n题目：\n{question.get('question_markdown', '')}\n"
        f"标准答案：\n{question.get('answer_markdown', '')}\n来源解析：\n{solution}\n"
        f"我的文字作答：\n{user_answer or '未填写文字；请检查随附的手写作答图片'}\n"
        "请先完成必要的内部思考；思考过程由界面状态代替，不要写入最终 content。最终只返回可解析的 JSON。"
    )
    user_content: str | list[dict[str, Any]] = user_text
    if image_data_urls:
        user_content = [{"type": "text", "text": user_text}]
        user_content.extend({"type": "image_url", "image_url": {"url": url}} for url in image_data_urls)
    return [
        {
            "role": "system",
            "content": (
                "你是考研数学辅导老师。只能依据用户提供的题目、答案和解析回答；如果来源没有解析，"
                "必须明确说没有来源解析，不得编造。先诊断错误类型，再给一个不直接泄露完整答案的提示，"
                "最后给出下一步训练建议。用简体中文，返回 JSON："
                '{"diagnosis":"","error_type":"","hint":"","explanation":"","next_step":""}。'
                "可以进行内部推理，但最终 content 只能包含上述 JSON，不要把推理文字放入 JSON。"
            ),
        },
        {
            "role": "user",
            "content": user_content,
        },
    ]


def _vision_grade_messages(question: dict[str, Any], image_data_urls: list[str]) -> list[dict[str, Any]]:
    question_text = (
        "请读取随附的手写作答图片，并与标准答案逐项核对。只判断图片中确实可见的答案，"
        "看不清时返回 unclear，不要因为文字作答为空就判错。只输出 JSON，不要输出 Markdown 代码围栏："
        '{"recognized_answer":"","verdict":"correct|incorrect|unclear","confidence":0.0,"explanation":""}\n'
        f"题目：\n{question.get('question_markdown', '')}\n"
        f"标准答案：\n{question.get('answer_markdown', '')}\n"
        f"来源解析：\n{question.get('solution_markdown') or '当前来源没有提供解析。'}\n"
        "请先完成必要的内部思考；最终 content 只输出可解析的 JSON，不要输出思考文字或 Markdown 围栏。"
    )
    return [
        {
            "role": "system",
            "content": "你是严格、诚实的考研数学阅卷助手。必须阅读用户随附的手写图片，不得把缺少文字答案当作未作答。",
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": question_text}]
            + [{"type": "image_url", "image_url": {"url": url}} for url in image_data_urls],
        },
    ]


async def vision_grade_question(
    question: dict[str, Any], image_data_urls: list[str], user_id: str = "local-user"
) -> dict[str, Any]:
    if not image_data_urls:
        raise LLMError("没有可供模型读取的手写作答图片。")
    content = await chat_completion(_vision_grade_messages(question, image_data_urls), temperature=0.0, user_id=user_id)
    result = parse_vision_grade(content)
    if result is None:
        raise LLMError("模型返回的手写判定结果无法解析，请重试。")
    return {"result": result, "model": _settings(user_id).get("model", "")}


async def tutor_response(
    question: dict[str, Any], user_answer: str, request: str = "分析我的错误",
    user_id: str = "local-user", image_data_urls: list[str] | None = None,
) -> dict[str, Any]:
    messages = _tutor_messages(question, user_answer, request, image_data_urls)
    content = await chat_completion(messages, temperature=0.15, user_id=user_id)
    return {"content": content, "model": _settings(user_id).get("model", "")}


async def tutor_response_stream(
    question: dict[str, Any],
    user_answer: str,
    request: str = "分析我的错误",
    user_id: str = "local-user",
    image_data_urls: list[str] | None = None,
) -> AsyncIterator[dict[str, str]]:
    messages = _tutor_messages(question, user_answer, request, image_data_urls)
    async for event in chat_completion_stream(messages, temperature=0.15, user_id=user_id):
        yield event


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
