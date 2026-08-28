"""Start the local AI Math service from any working directory.

The launcher deliberately uses only the Python standard library around
Uvicorn. That keeps it usable on Windows, macOS and Linux without relying on
shell-specific activation scripts or a particular current directory.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import init_db
from app.services.server import ServerSettingsError, normalize_server_settings, server_settings


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动砺数本地学习服务")
    parser.add_argument("--host", default="", help="临时覆盖监听地址，例如 127.0.0.1 或 0.0.0.0")
    parser.add_argument("--port", type=int, default=0, help="临时覆盖端口，例如 8000")
    parser.add_argument("--open", "--open-browser", dest="open_browser", action="store_true", help="服务启动后自动打开默认浏览器")
    return parser.parse_args()


def _probe_health(host: str, port: int) -> bool:
    """Return whether an existing listener is already an AI Math service."""
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::", "::1"} else host
    if ":" in browser_host and not browser_host.startswith("["):
        browser_host = f"[{browser_host}]"
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://{browser_host}:{port}/api/health", timeout=1.5) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _port_is_busy(host: str, port: int) -> bool:
    """Check a bind address without reserving it, with IPv4/IPv6 fallback."""
    candidates = [host]
    if host in {"0.0.0.0", "::", "::1", "localhost"}:
        candidates.extend(["127.0.0.1", "::1"])
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        family = socket.AF_INET6 if ":" in candidate else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as connection:
                connection.settimeout(0.35)
                if connection.connect_ex((candidate, port)) == 0:
                    return True
        except OSError:
            continue
    return False


def _browser_url(host: str, port: int) -> str:
    # 0.0.0.0 and :: are bind wildcards, not valid browser destinations.
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::", "::1"} else host
    if ":" in display_host and not display_host.startswith("["):
        display_host = f"[{display_host}]"
    return f"http://{display_host}:{port}"


def _open_browser_later(url: str) -> None:
    timer = threading.Timer(0.8, lambda: webbrowser.open(url, new=2))
    timer.daemon = True
    timer.start()


def main() -> int:
    args = _arguments()
    try:
        init_db()
        stored = server_settings()
        settings = normalize_server_settings(
            args.host or stored["host"],
            args.port or stored["port"],
            stored.get("public_url", ""),
        )
    except (OSError, ServerSettingsError) as error:
        print(f"启动配置无效：{error}", file=sys.stderr)
        return 2

    host = settings["host"]
    port = settings["port"]
    url = _browser_url(host, port)
    if _port_is_busy(host, port):
        if _probe_health(host, port):
            print(f"砺数服务已在运行：{url}")
            if args.open_browser:
                webbrowser.open(url, new=2)
            return 0
        print(f"端口 {port} 已被其他程序占用，请在设置中换一个端口，或使用 --port 临时覆盖。", file=sys.stderr)
        return 3

    print(f"砺数服务启动中：{url}")
    print("按 Ctrl+C 停止服务。")
    if args.open_browser:
        _open_browser_later(url)
    try:
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
            reload=False,
        )
    except (OSError, SystemExit) as error:
        print(f"服务启动失败：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
