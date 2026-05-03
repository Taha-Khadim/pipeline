"""Shared Jinja2 templates with an absolute path so the app works
regardless of the process's current working directory (matters for
PyInstaller-frozen bundles)."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = (Path(__file__).resolve().parent / "templates")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
