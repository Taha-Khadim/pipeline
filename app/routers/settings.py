"""
Settings router — lets the user configure the API key, sender info, and
the Supabase Postgres connection from the in-app UI. Persists to
settings.json in the user data dir.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from app.config import (
    get_settings,
    save_settings_json,
    supabase_postgres_url,
    _normalize_pg_url,
)
from app.templating import templates

log = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _pg_test_ssl() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def _ping(url: str, *, timeout: float = 8.0):
    """Open one Postgres connection, run SELECT 1, return (ok, message)."""
    try:
        import asyncpg  # type: ignore
    except ImportError:
        return False, "asyncpg not installed in this build."

    plain = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(
                plain,
                ssl=_pg_test_ssl(),
                statement_cache_size=0,
            ),
            timeout=timeout,
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

    try:
        try:
            count = await conn.fetchval("SELECT COUNT(*) FROM public.leads")
        except Exception:
            count = None
        version = await conn.fetchval("SELECT version()")
    finally:
        await conn.close()

    msg = "Connected to Supabase Postgres."
    if count is not None:
        msg += f" {count} lead row(s) so far."
    else:
        msg += " (Schema not migrated yet — open Settings → View migration SQL.)"
    msg += f"  [{(version or '')[:60]}]"
    return True, msg


async def _is_db_healthy() -> bool:
    """Quick health-check of the configured database URL. Used by the page."""
    try:
        s = get_settings()
        ok, _ = await _ping(s.effective_database_url, timeout=4)
        return ok
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_class=HTMLResponse)
async def settings_page(request: Request):
    s = get_settings()
    db_healthy = await _is_db_healthy()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active_page": "settings",
            "google_api_key_set": bool(s.google_api_key),
            "google_api_key_preview": _mask(s.google_api_key),
            "sender_name": s.sender_name,
            "sender_company": s.sender_company,
            "sender_website": s.sender_website,
            "sender_email": s.sender_email,
            "supabase_url": s.supabase_url,
            "supabase_anon_key_preview": _mask(s.supabase_anon_key),
            "supabase_password_set": bool(s.supabase_db_password),
            "database_backend": "postgres",
            "database_url_explicit": _redact_url(s.database_url) if s.database_url else "",
            "db_healthy": db_healthy,
        },
    )


@router.get("/status")
async def settings_status():
    s = get_settings()
    return {
        "google_api_key_set": bool(s.google_api_key),
        "sender_name": s.sender_name,
        "sender_company": s.sender_company,
        "sender_website": s.sender_website,
        "sender_email": s.sender_email,
        "supabase_url": s.supabase_url,
        "supabase_password_set": bool(s.supabase_db_password),
        "database_backend": "postgres",
        "db_healthy": await _is_db_healthy(),
    }


@router.post("/save")
async def save(request: Request):
    body = await request.json()

    payload: dict = {
        "sender_name": (body.get("sender_name") or "").strip(),
        "sender_company": (body.get("sender_company") or "").strip(),
        "sender_website": (body.get("sender_website") or "").strip(),
        "sender_email": (body.get("sender_email") or "").strip(),
    }

    google_api_key = (body.get("google_api_key") or "").strip()
    if google_api_key and not google_api_key.startswith("•"):
        payload["google_api_key"] = google_api_key

    save_settings_json(payload)
    return {"ok": True}


@router.post("/save-database")
async def save_database(request: Request):
    """Persist Supabase connection settings + rebuild the engine."""
    body = await request.json()

    s = get_settings()

    new_url = (body.get("supabase_url") or s.supabase_url).strip()
    new_anon = (body.get("supabase_anon_key") or "").strip()
    new_password = (body.get("supabase_db_password") or "").strip()
    new_database_url = (body.get("database_url") or "").strip()

    payload: dict = {"supabase_url": new_url}
    if new_anon and not new_anon.startswith("•"):
        payload["supabase_anon_key"] = new_anon
    if new_password and not new_password.startswith("•"):
        payload["supabase_db_password"] = new_password
    # If user pasted a redacted URL (the page renders the password as ***),
    # leave the existing one alone so we don't blow it away.
    if new_database_url and "***" not in new_database_url:
        payload["database_url"] = new_database_url
    elif new_database_url == "":
        payload["database_url"] = ""

    save_settings_json(payload)

    try:
        from app.database import reset_engine

        await reset_engine()
    except Exception as exc:
        log.warning("reset_engine failed after save-database: %s", exc)

    s2 = get_settings()
    return {
        "ok": True,
        "database_backend": "postgres",
        "supabase_password_set": bool(s2.supabase_db_password),
        "db_healthy": await _is_db_healthy(),
    }


@router.post("/test-database")
async def test_database(request: Request):
    """Try to open a connection with the current (or supplied) credentials."""
    try:
        raw = await request.body()
        body = json.loads(raw.decode() or "{}") if raw else {}
    except Exception:
        body = {}

    s = get_settings()

    explicit_url = (body.get("database_url") or "").strip()
    if explicit_url and "***" not in explicit_url:
        url = _normalize_pg_url(explicit_url)
    else:
        url = (body.get("supabase_url") or s.supabase_url).strip()
        pw = (body.get("supabase_db_password") or s.supabase_db_password).strip()
        derived = supabase_postgres_url(url, pw) if pw else None
        url = derived or s.effective_database_url

    if not url:
        return JSONResponse(
            {"ok": False, "error": "No Supabase connection configured."},
            status_code=200,
        )

    ok, msg = await _ping(url, timeout=10)
    if not ok:
        return {"ok": False, "error": msg}
    return {"ok": True, "message": msg}


@router.get("/migration-sql", response_class=PlainTextResponse)
async def migration_sql():
    """Return the Supabase migration SQL so users can copy/paste it."""
    import sys

    bases = [Path(__file__).resolve().parent.parent.parent]
    if hasattr(sys, "_MEIPASS"):
        bases.append(Path(sys._MEIPASS))
    if getattr(sys, "frozen", False):
        bases.append(Path(sys.executable).resolve().parent)

    for base in bases:
        for tail in (
            "scripts/supabase_migration.sql",
            "supabase_migration.sql",
        ):
            p = base / tail
            if p.exists():
                return PlainTextResponse(
                    p.read_text(),
                    media_type="text/plain; charset=utf-8",
                    headers={
                        "Content-Disposition": "inline; filename=supabase_migration.sql"
                    },
                )
    return PlainTextResponse(
        "-- migration SQL not found in this build", status_code=404
    )


@router.post("/test-gemini")
async def test_gemini(request: Request):
    s = get_settings()
    if not s.google_api_key:
        return {"ok": False, "error": "No API key configured."}

    try:
        import google.generativeai as genai

        genai.configure(api_key=s.google_api_key)
        model = genai.GenerativeModel("gemini-flash-lite-latest")
        resp = await model.generate_content_async("Reply with the single word: OK")
        text = (resp.text or "").strip()
        return {"ok": True, "reply": text[:100]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return value[:4] + "•" * (len(value) - 8) + value[-4:]


def _redact_url(url: str) -> str:
    """Hide the password segment in URLs we send back to the page."""
    try:
        from urllib.parse import urlsplit, urlunsplit

        p = urlsplit(url)
        if p.username and p.password:
            netloc = f"{p.username}:***@{p.hostname}"
            if p.port:
                netloc += f":{p.port}"
            return urlunsplit(p._replace(netloc=netloc))
    except Exception:
        pass
    return url
