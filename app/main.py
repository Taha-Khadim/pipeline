from __future__ import annotations

import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings, DATA_DIR, SCREENSHOTS_DIR
from app.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("lumora")

BASE_DIR = Path(__file__).resolve().parent


def _ensure_playwright_browser() -> None:
    """Install the Chromium binary for Playwright on first run if missing.

    Skipped when LUMORA_SKIP_PLAYWRIGHT_INSTALL=1 (used by frozen builds that
    bundle browsers themselves).
    """
    if os.environ.get("LUMORA_SKIP_PLAYWRIGHT_INSTALL") == "1":
        return

    marker = DATA_DIR / ".playwright-installed"
    if marker.exists():
        return

    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        return

    try:
        log.info("Installing Playwright Chromium (one-time, ~150 MB)…")
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            timeout=900,
        )
        marker.write_text("ok")
        log.info("Playwright Chromium installed.")
    except Exception as exc:
        log.warning("Could not auto-install Playwright Chromium: %s", exc)
        log.warning("Run manually:  python -m playwright install chromium")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Lumora data dir: %s", DATA_DIR)
    _ensure_playwright_browser()
    await init_db()
    yield


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/screenshots", StaticFiles(directory=str(SCREENSHOTS_DIR)), name="screenshots")

from app.routers import dashboard, discover, leads, outreach, settings as settings_router  # noqa: E402

app.include_router(dashboard.router)
app.include_router(discover.router, prefix="/discover", tags=["discover"])
app.include_router(leads.router, prefix="/leads", tags=["leads"])
app.include_router(outreach.router, prefix="/outreach", tags=["outreach"])
app.include_router(settings_router.router, prefix="/settings", tags=["settings"])
