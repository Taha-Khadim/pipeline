"""
Bing Maps local-business scraper using Playwright.

Bing Maps consistently exposes a local results panel with structured cards
that contain name, category, address and phone — all from the inner_text.
We use the b1.bing.com/maps URL with a free-text query.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import asdict, dataclass
from urllib.parse import quote_plus, unquote

from playwright.async_api import async_playwright, Page

log = logging.getLogger(__name__)


@dataclass
class BingBusiness:
    name: str = ""
    category: str = ""
    address: str = ""
    city: str = ""
    country: str = ""
    phone: str = ""
    website_url: str = ""
    has_website: bool = False
    google_maps_url: str = ""
    google_rating: float | None = None
    google_reviews: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


async def _dismiss_consent(page: Page):
    for sel in [
        '#bnp_btn_accept',
        'button:has-text("Accept")',
        '#bnp_container .bnp_btn_accept',
    ]:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await asyncio.sleep(0.5)
                return
        except Exception:
            continue


_PHONE_RE = re.compile(r"(\+?\d[\d\s\-().]{8,20}\d)")


def _parse_card_text(text: str, biz: BingBusiness) -> None:
    """Parse the inner_text of a Bing Maps card into our fields.

    Card layout (one per newline):
        Tavistock Dental London
        Dentist
        16 Tavistock Pl, London
        Closed · Opens Mon 9 AM · +44 20 7837 5638
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return
    if not biz.name:
        biz.name = lines[0]
    for line in lines[1:]:
        if not biz.category and 2 < len(line) < 60 and not re.search(r"\d", line):
            biz.category = line
            continue
        if not biz.address and re.search(r"\d", line) and "·" not in line and len(line) < 200:
            biz.address = line
            continue
        if "·" in line:
            for chunk in (c.strip() for c in line.split("·")):
                m = _PHONE_RE.search(chunk)
                if m and not biz.phone:
                    biz.phone = m.group(1).strip()
        m = _PHONE_RE.search(line)
        if m and not biz.phone and len(m.group(1)) >= 10:
            biz.phone = m.group(1).strip()
        rm = re.search(r"(\d[.,]\d)\s*\(?(\d[\d,.]*)?\)?\s*reviews?", line, re.I)
        if rm and biz.google_rating is None:
            try:
                biz.google_rating = float(rm.group(1).replace(",", "."))
                if rm.group(2):
                    biz.google_reviews = int(rm.group(2).replace(",", "").replace(".", ""))
            except ValueError:
                pass


async def _extract_card(card, city: str, country: str) -> BingBusiness | None:
    try:
        biz = BingBusiness(city=city, country=country)
        text = await card.inner_text()
        _parse_card_text(text, biz)
        if not biz.name:
            return None

        for a in await card.query_selector_all('a[href]'):
            href = await a.get_attribute("href") or ""
            if not href.startswith("http"):
                continue
            if "bing.com" in href or "microsoft.com" in href:
                continue
            biz.website_url = href
            biz.has_website = True
            break

        if not biz.website_url:
            for a in await card.query_selector_all('a[href*="url="]'):
                href = await a.get_attribute("href") or ""
                m = re.search(r"url=([^&]+)", href)
                if m:
                    candidate = unquote(m.group(1))
                    if candidate.startswith("http") and "bing.com" not in candidate:
                        biz.website_url = candidate
                        biz.has_website = True
                        break

        return biz
    except Exception as exc:
        log.debug("bing card parse error: %s", exc)
        return None


async def scrape_yelp(
    industry: str,
    city: str,
    country: str,
    max_results: int = 30,
) -> list[dict]:
    """Scrape Bing Maps local-results panel."""
    query = f"{industry} {city}"
    encoded = quote_plus(query)
    url = f"https://www.bing.com/maps?q={encoded}"
    results: list[dict] = []

    log.info("Bing Maps scrape: %s", query)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 900},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            await _dismiss_consent(page)
            await asyncio.sleep(1.5)

            cards = await page.query_selector_all('[data-entity]')
            if not cards:
                cards = await page.query_selector_all('div[role="listitem"]')
            log.info("Bing Maps: %d cards", len(cards))

            seen: set[str] = set()
            for card in cards[:max_results]:
                biz = await _extract_card(card, city, country)
                if biz and biz.name and biz.name not in seen:
                    seen.add(biz.name)
                    results.append(biz.to_dict())

        except Exception as exc:
            log.error("Bing Maps scrape failed: %s", exc)
        finally:
            await browser.close()

    log.info("Bing Maps: %d businesses extracted", len(results))
    return results
