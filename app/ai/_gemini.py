"""Shared Gemini API helper with model fallback.

Why a shared helper:
  Both research_agent.py and outreach_gen.py call Gemini. Free-tier model
  availability and quotas vary widely (gemini-2.0-flash may report
  ``limit: 0`` for some accounts while gemini-2.5-flash works fine), so
  every Gemini call should walk a list of candidate models until one
  succeeds. Centralising the logic keeps that list, error handling, and
  parse logic in one place.
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

# Ordered list of Gemini models to try, cheapest / most-available first.
# `gemini-flash-latest` is an alias that always points to the latest free
# flash model, so it's a sensible primary choice.
GEMINI_MODELS: list[str] = [
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
]


async def gemini_json(
    prompt: str,
    api_key: str,
    *,
    temperature: float = 0.7,
    fallback_payload: dict | None = None,
) -> dict:
    """Call Gemini with ``prompt`` and return parsed JSON.

    Walks ``GEMINI_MODELS`` in order. Returns ``{"error": "..."}`` if
    every model fails, with a useful explanation of why.
    """
    if not api_key:
        return {"error": (
            "Google Gemini API key is not set. Open the Settings page, "
            "paste your free key from https://aistudio.google.com/apikey, "
            "click Save, and try again."
        )}

    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            import google.generativeai as genai  # noqa: F401  (used below)
    except ImportError as exc:
        return {"error": f"google-generativeai not installed: {exc}"}

    genai.configure(api_key=api_key)

    last_err: str = ""
    for model_name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(
                model_name,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": temperature,
                },
            )
            resp = await model.generate_content_async(prompt)
            text = (resp.text or "").strip()
            if not text:
                last_err = f"{model_name}: empty response"
                continue
            parsed = _parse_json(text)
            if parsed and not parsed.get("_parse_error"):
                parsed["_model"] = model_name
                return parsed
            last_err = f"{model_name}: model returned non-JSON output"
        except Exception as exc:
            msg = str(exc)
            log.warning("Gemini model %s failed: %s", model_name, msg[:300])
            short = msg.splitlines()[0][:200] if msg else "(no message)"
            last_err = f"{model_name}: {short}"
            upper = msg.upper()
            # Auth errors: trying more models won't help.
            if "API_KEY_INVALID" in upper or " 401 " in f" {msg} " or "403" in upper:
                return {"error": (
                    "Google Gemini rejected the API key. "
                    "Open Settings, double-check the key from "
                    "https://aistudio.google.com/apikey and save it again."
                )}
            # 404 = model not enabled for this project; just try next.
            # 429 = quota; try next model (different quota bucket).
            continue

    if fallback_payload is not None:
        # Caller provided a graceful fallback payload (e.g. for research
        # where empty data is better than a hard error).
        result: dict[str, Any] = dict(fallback_payload)
        result["_error"] = last_err
        return result

    return {"error": (
        f"All Gemini models failed. Last error — {last_err}. "
        "This usually means free-tier quota is exhausted "
        "(wait ~1 minute and retry), or the key isn't activated for any "
        "Generative AI model. Get a fresh key at "
        "https://aistudio.google.com/apikey."
    )}


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"body": str(data)}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end])
                return data if isinstance(data, dict) else {"body": str(data)}
            except Exception:
                pass
        return {"_parse_error": True, "body": text}
