from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

from app.database import get_setting, set_setting


DEFAULT_SERVER_SETTINGS = {
    "host": "127.0.0.1",
    "port": 8000,
    "public_url": "",
}
HOSTNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")


class ServerSettingsError(ValueError):
    """Raised when a bind or advertised server setting cannot be used."""


def _validate_host(value: str) -> str:
    host = (value or "").strip()
    if not host:
        raise ServerSettingsError("监听地址不能为空。")
    if any(character.isspace() for character in host):
        raise ServerSettingsError("监听地址不能包含空格。")
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::", "::1"}:
        return host
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        if not HOSTNAME_PATTERN.fullmatch(host) or ".." in host:
            raise ServerSettingsError("监听地址应为 IP、localhost 或合法主机名。")
        return host


def _validate_public_url(value: str) -> str:
    public_url = (value or "").strip().rstrip("/")
    if not public_url:
        return ""
    parsed = urlparse(public_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ServerSettingsError("对外访问地址必须是 http:// 或 https:// 开头的完整地址。")
    return public_url


def normalize_server_settings(host: str, port: int, public_url: str = "") -> dict[str, Any]:
    try:
        normalized_port = int(port)
    except (TypeError, ValueError) as exc:
        raise ServerSettingsError("端口必须是 1 到 65535 之间的整数。") from exc
    if not 1 <= normalized_port <= 65535:
        raise ServerSettingsError("端口必须是 1 到 65535 之间的整数。")
    return {
        "host": _validate_host(host),
        "port": normalized_port,
        "public_url": _validate_public_url(public_url),
    }


def _stored_settings() -> dict[str, Any]:
    value = get_setting("server_settings", {})
    return value if isinstance(value, dict) else {}


def server_settings() -> dict[str, Any]:
    stored = _stored_settings()
    try:
        normalized = normalize_server_settings(
            stored.get("host", DEFAULT_SERVER_SETTINGS["host"]),
            stored.get("port", DEFAULT_SERVER_SETTINGS["port"]),
            stored.get("public_url", DEFAULT_SERVER_SETTINGS["public_url"]),
        )
    except ServerSettingsError:
        normalized = dict(DEFAULT_SERVER_SETTINGS)
    public_url = normalized["public_url"]
    bind_host = normalized["host"]
    access_url = public_url or f"http://{bind_host}:{normalized['port']}"
    # Wildcard bind addresses are useful to the server but cannot be pasted
    # into a browser. Keep the original access_url for compatibility and also
    # expose a safe local URL for desktop launchers and the settings view.
    browser_host = "127.0.0.1" if bind_host in {"0.0.0.0", "::", "::1"} else bind_host
    if ":" in browser_host and not browser_host.startswith("["):
        browser_host = f"[{browser_host}]"
    browser_url = public_url or f"http://{browser_host}:{normalized['port']}"
    is_network_bound = bind_host not in {"127.0.0.1", "localhost", "::1"}
    return {
        **normalized,
        "access_url": access_url,
        "browser_url": browser_url,
        "binding_mode": "网络访问" if is_network_bound else "仅本机",
        "network_exposure_warning": is_network_bound,
        "restart_required": True,
        "launch_command": "python scripts/run_server.py",
        "direct_launch_command": f"python -m uvicorn app.main:app --host {bind_host} --port {normalized['port']}",
    }


def save_server_settings(host: str, port: int, public_url: str = "") -> dict[str, Any]:
    normalized = normalize_server_settings(host, port, public_url)
    set_setting("server_settings", normalized)
    return server_settings()
