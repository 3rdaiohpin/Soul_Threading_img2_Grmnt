"""Hugging Face Spaces / self-hosted entrypoint.

Serves the FastAPI backend AND the built React frontend from a single process
on port 7860 (Hugging Face default).

Usage:
    uvicorn hf_serve:app --host 0.0.0.0 --port 7860
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

# Make backend module importable
BACKEND_DIR = Path(__file__).parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Ensure the backend sees its own .env
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "soul_threading")
os.environ.setdefault("CORS_ORIGINS", "*")

from server import app  # noqa: E402  (FastAPI app instance)
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

FRONTEND_BUILD = Path(__file__).parent / "frontend" / "build"

if FRONTEND_BUILD.exists():
    # Mount static assets under /static
    app.mount(
        "/static",
        StaticFiles(directory=str(FRONTEND_BUILD / "static")),
        name="static",
    )

    @app.get("/", include_in_schema=False)
    async def _index():
        return FileResponse(FRONTEND_BUILD / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa(full_path: str):
        # Return actual assets when they exist, otherwise SPA fallback
        candidate = FRONTEND_BUILD / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_BUILD / "index.html")
