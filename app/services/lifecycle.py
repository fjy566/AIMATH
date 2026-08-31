"""Process lifecycle controls for the local single-process service."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Literal

from app.services.server import server_settings


ROOT_DIR = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = ROOT_DIR / "scripts" / "run_server.py"
ACTION_DELAY_SECONDS = 0.5
RESTART_LAUNCHER_ENV = "AI_MATH_RESTART_LAUNCHER"
RESTART_CODE = "\n".join(
    (
        "import os",
        "import runpy",
        "import socket",
        "import sys",
        "import time",
        "",
        "host = os.environ.get('AI_MATH_RESTART_HOST', '127.0.0.1')",
        "port = int(os.environ.get('AI_MATH_RESTART_PORT', '8000'))",
        "probe_host = '127.0.0.1' if host in {'0.0.0.0', '::', '::1', 'localhost'} else host",
        "for _ in range(40):",
        "    try:",
        "        with socket.create_connection((probe_host, port), timeout=0.25):",
        "            pass",
        "    except OSError:",
        "        break",
        "    time.sleep(0.25)",
        "sys.argv = ['run_server.py', '--open']",
        "runpy.run_path(os.environ['AI_MATH_RESTART_LAUNCHER'], run_name='__main__')",
    )
)


class LifecycleError(RuntimeError):
    """Raised when the local service cannot schedule a lifecycle action."""


def _restart_process() -> None:
    if not LAUNCHER_PATH.is_file():
        raise LifecycleError("找不到后台启动脚本，无法重启服务。")
    settings = server_settings()
    environment = os.environ.copy()
    environment[RESTART_LAUNCHER_ENV] = str(LAUNCHER_PATH)
    environment["AI_MATH_RESTART_HOST"] = str(settings["host"])
    environment["AI_MATH_RESTART_PORT"] = str(settings["port"])
    subprocess.Popen(
        [sys.executable, "-c", RESTART_CODE],
        cwd=str(ROOT_DIR),
        env=environment,
        stdin=subprocess.DEVNULL,
    )
    os.kill(os.getpid(), signal.SIGTERM)


def _shutdown_process() -> None:
    os.kill(os.getpid(), signal.SIGTERM)


def schedule_lifecycle_action(action: Literal["restart", "shutdown"], delay_seconds: float = ACTION_DELAY_SECONDS) -> None:
    """Run a process action after the HTTP response has had time to flush."""
    if action == "restart":
        if not LAUNCHER_PATH.is_file():
            raise LifecycleError("找不到后台启动脚本，无法重启服务。")
        callback = _restart_process
    elif action == "shutdown":
        callback = _shutdown_process
    else:
        raise LifecycleError("不支持的后台控制操作。")

    timer = threading.Timer(max(0.0, float(delay_seconds)), callback)
    timer.daemon = True
    timer.start()
