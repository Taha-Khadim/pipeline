"""
Settings router — lets the user configure the API key + sender info
from the UI. Persists to settings.json in the user data dir.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.config import get_settings, save_settings_json
from app.templating import templates

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def settings_page(request: Request):
    s = get_settings()
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
    }


@router.post("/save")
async def save(request: Request):
    body = await request.json()

    google_api_key = (body.get("google_api_key") or "").strip()
    payload = {
        "sender_name": (body.get("sender_name") or "").strip(),
        "sender_company": (body.get("sender_company") or "").strip(),
        "sender_website": (body.get("sender_website") or "").strip(),
        "sender_email": (body.get("sender_email") or "").strip(),
    }
    # Only update the key if a non-masked value was provided.
    if google_api_key and not google_api_key.startswith("•"):
        payload["google_api_key"] = google_api_key

    save_settings_json(payload)
    return {"ok": True}


@router.post("/test-gemini")
async def test_gemini(request: Request):
    s = get_settings()
    if not s.google_api_key:
        return {"ok": False, "error": "No API key configured."}

    try:
        import google.generativeai as genai
        genai.configure(api_key=s.google_api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
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
