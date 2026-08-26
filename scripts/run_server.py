from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import init_db
from app.services.server import server_settings


if __name__ == "__main__":
    init_db()
    settings = server_settings()
    uvicorn.run(
        "app.main:app",
        host=settings["host"],
        port=settings["port"],
        reload=False,
    )
