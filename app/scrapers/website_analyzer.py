"""
Website quality analyzer.

Checks whether a business website exists, is mobile-friendly, uses HTTPS,
and gives an overall quality assessment. Takes a screenshot for reference.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PwTimeout

from app.config import get_settings

log = logging.getLogger(__name__)


@dataclass
class WebsiteAnalysis:
    is_live: bool = False
    uses_https: bool = False
    is_mobile_friendly: bool = False
    load_time_ms: int = 0
    has_contact_form: bool = False
    has_booking_system: bool = False
    technology: str = ""
    page_title: str = ""
    meta_description: str = ""
    quality_score: float = 0.0
    issues: list[str] | None = None
    screenshot_path: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _detect_technology(html: str, headers: dict) -> str:
    html_lower = html.lower()
    if "wp-content" in html_lower or "wordpress" in html_lower:
        return "WordPress"
    if "wix.com" in html_lower or "wixsite" in html_lower:
        return "Wix"
    if "squarespace" in html_lower:
        return "Squarespace"
    if "shopify" in html_lower:
        return "Shopify"
    if "webflow" in html_lower:
        return "Webflow"
    if "godaddy" in html_lower:
        return "GoDaddy Builder"
    server = headers.get("x-powered-by", "")
    if server:
        return server
    return "Unknown / Custom"


async def analyze_website(
    url: str,
    take_screenshot: bool = True,
    lead_id: int | None = None,
) -> WebsiteAnalysis:
    """
    Analyze a business website for quality, technology, and issues.
    Optionally captures a screenshot.
    """
    if not url:
        return WebsiteAnalysis(issues=["No URL provided"])

    if not url.startswith("http"):
        url = "https://" + url

    analysis = WebsiteAnalysis()
    analysis.issues = []
    analysis.uses_https = url.startswith("https")

    if not analysis.uses_https:
        analysis.issues.append("Does not use HTTPS")

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LumoraBot/1.0)"},
        ) as client:
            resp = await client.get(url)
        elapsed = int((time.monotonic() - start) * 1000)

        analysis.is_live = resp.status_code == 200
        analysis.load_time_ms = elapsed

        if not analysis.is_live:
            analysis.issues.append(f"HTTP {resp.status_code}")
            return analysis

        html = resp.text
        headers = dict(resp.headers)

        soup = BeautifulSoup(html, "html.parser")

        title_tag = soup.find("title")
        if title_tag:
            analysis.page_title = title_tag.get_text(strip=True)

        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            analysis.meta_description = meta_desc.get("content", "")

        viewport = soup.find("meta", attrs={"name": "viewport"})
        analysis.is_mobile_friendly = viewport is not None
        if not analysis.is_mobile_friendly:
            analysis.issues.append("Not mobile-friendly (no viewport meta tag)")

        forms = soup.find_all("form")
        if forms:
            for form in forms:
                text = form.get_text(" ", strip=True).lower()
                if any(w in text for w in ["contact", "message", "email", "inquiry"]):
                    analysis.has_contact_form = True
                if any(w in text for w in ["book", "appointment", "schedule", "reserve"]):
                    analysis.has_booking_system = True

        analysis.technology = _detect_technology(html, headers)

        if analysis.load_time_ms > 5000:
            analysis.issues.append(f"Slow load time: {analysis.load_time_ms}ms")

        if not analysis.meta_description:
            analysis.issues.append("Missing meta description (bad for SEO)")

        # Quality score: 0-10
        score = 5.0
        if analysis.uses_https:
            score += 1
        if analysis.is_mobile_friendly:
            score += 1.5
        else:
            score -= 2
        if analysis.has_contact_form:
            score += 0.5
        if analysis.has_booking_system:
            score += 0.5
        if analysis.meta_description:
            score += 0.5
        if analysis.load_time_ms < 2000:
            score += 0.5
        elif analysis.load_time_ms > 5000:
            score -= 1
        if analysis.technology in ("Wix", "GoDaddy Builder"):
            score -= 0.5
            analysis.issues.append(f"Built with {analysis.technology} (opportunity to upgrade)")

        analysis.quality_score = max(0.0, min(10.0, round(score, 1)))

    except Exception as exc:
        log.warning("Website analysis failed for %s: %s", url, exc)
        analysis.issues.append(f"Analysis error: {str(exc)}")
        return analysis

    if take_screenshot:
        try:
            analysis.screenshot_path = await _capture_screenshot(url, lead_id)
        except Exception as exc:
            log.warning("Screenshot failed for %s: %s", url, exc)

    return analysis


async def _capture_screenshot(url: str, lead_id: int | None) -> str | None:
    settings = get_settings()
    screenshots_dir = Path(settings.screenshots_dir)
    screenshots_dir.mkdir(exist_ok=True)

    filename = f"lead_{lead_id}.png" if lead_id else f"{urlparse(url).netloc}.png"
    filepath = screenshots_dir / filename

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        try:
            await page.goto(url, wait_until="networkidle", timeout=20000)
            await page.screenshot(path=str(filepath), full_page=False)
        except PwTimeout:
            await page.screenshot(path=str(filepath), full_page=False)
        finally:
            await browser.close()

    return str(filepath)
