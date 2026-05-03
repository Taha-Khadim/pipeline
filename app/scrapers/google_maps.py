"""
Google Maps scraper using Playwright.

Strategy:
  1. Open the search-results page and scroll to load N listings.
  2. Extract names + maps URLs from the result cards.
  3. For each maps URL, navigate the SAME page to that URL — this fully
     opens the detail panel and exposes phone/website/address/category/rating
     via stable [data-item-id=...] selectors. (Clicking the result card
     in-place silently fails on the current Maps build, hence the goto.)
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass, asdict

from playwright.async_api import async_playwright, Page, TimeoutError as PwTimeout

from app.config import get_settings

log = logging.getLogger(__name__)


@dataclass
class BusinessResult:
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


async def _random_delay(lo: float = 0.5, hi: float = 1.5):
    await asyncio.sleep(random.uniform(lo, hi))


async def _dismiss_consent(page: Page):
    for sel in [
        'button:has-text("Accept all")',
        'button:has-text("Accept All")',
        'button:has-text("I agree")',
        '[aria-label="Accept all"]',
        'form[action*="consent"] button',
    ]:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await asyncio.sleep(1.0)
                return
        except Exception:
            continue


async def _scroll_feed(page: Page, max_items: int) -> None:
    prev_count = 0
    stale = 0
    for _ in range(40):
        items = await page.query_selector_all('div.Nv2PK a[href*="/maps/place/"]')
        if not items:
            items = await page.query_selector_all('a[href*="/maps/place/"]')
        if len(items) >= max_items:
            return
        if len(items) == prev_count:
            stale += 1
            if stale >= 4:
                return
        else:
            stale = 0
        prev_count = len(items)

        feed = await page.query_selector('div[role="feed"]')
        if feed:
            await feed.evaluate("el => el.scrollBy(0, 1200)")
        else:
            await page.mouse.wheel(0, 800)
        await asyncio.sleep(1.0 + random.uniform(0, 0.5))


async def _extract_from_card(card, city: str, country: str) -> BusinessResult | None:
    """Parse a sidebar result card. Returns name + url + best-effort
    rating/category/address. Phone/website are filled later by a detail visit."""
    try:
        biz = BusinessResult(city=city, country=country)
        link = await card.query_selector('a[href*="/maps/place/"]')
        if not link:
            return None
        biz.google_maps_url = await link.get_attribute("href") or ""
        label = await link.get_attribute("aria-label") or ""
        if label:
            biz.name = label.strip()

        if not biz.name:
            n = await card.query_selector('.qBF1Pd, .fontHeadlineSmall')
            if n:
                biz.name = (await n.inner_text()).strip()
        if not biz.name:
            return None

        text = await card.inner_text()
        rm = re.search(r"(\d[.,]\d)\s*\(?(\d[\d,.]*)?\)?", text)
        if rm:
            try:
                biz.google_rating = float(rm.group(1).replace(",", "."))
                if rm.group(2):
                    biz.google_reviews = int(rm.group(2).replace(",", "").replace(".", ""))
            except ValueError:
                pass

        for line in (l.strip() for l in text.split("\n") if l.strip()):
            if "·" in line and not biz.category:
                parts = [p.strip() for p in line.split("·")]
                for p in parts:
                    if not re.search(r"\d", p) and 2 < len(p) < 60 and not biz.category:
                        biz.category = p
                    elif re.search(r"\d", p) and len(p) < 100 and not biz.address:
                        biz.address = p

        # The card sometimes has a "Visit Site" anchor to the actual website.
        for a in await card.query_selector_all('a[href]'):
            href = await a.get_attribute("href") or ""
            if href.startswith("http") and "google" not in href and "maps" not in href:
                biz.website_url = href
                biz.has_website = True
                break

        return biz
    except Exception as exc:
        log.debug("card parse error: %s", exc)
        return None


async def _enrich_from_detail(page: Page, biz: BusinessResult) -> BusinessResult:
    """Navigate directly to the listing's maps URL and pull phone / website /
    address / category / rating from the detail panel."""
    if not biz.google_maps_url:
        return biz
    try:
        await page.goto(biz.google_maps_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2.0 + random.uniform(0.0, 1.0))

        if not biz.phone:
            el = await page.query_selector('button[data-item-id*="phone"]')
            if el:
                aria = await el.get_attribute("aria-label") or ""
                m = re.search(r"Phone:\s*(.+)", aria)
                if m:
                    biz.phone = m.group(1).strip()
                else:
                    biz.phone = (await el.inner_text()).strip().split("\n")[-1].strip()

        if not biz.website_url:
            el = await page.query_selector('a[data-item-id="authority"]')
            if el:
                href = await el.get_attribute("href") or ""
                if href and "google" not in href:
                    biz.website_url = href
                    biz.has_website = True

        if not biz.address:
            el = await page.query_selector('button[data-item-id="address"]')
            if el:
                aria = await el.get_attribute("aria-label") or ""
                m = re.search(r"Address:\s*(.+)", aria)
                biz.address = m.group(1).strip() if m else (await el.inner_text()).strip().split("\n")[-1].strip()

        if not biz.category:
            el = await page.query_selector('button[jsaction*="category"]')
            if el:
                biz.category = (await el.inner_text()).strip()

        if biz.google_rating is None:
            el = await page.query_selector('div.fontDisplayLarge')
            if el:
                try:
                    biz.google_rating = float((await el.inner_text()).strip().replace(",", "."))
                except ValueError:
                    pass

        if biz.google_reviews is None:
            el = await page.query_selector('button[jsaction*="reviewChart"] span, span[aria-label*="review"]')
            if el:
                txt = (await el.inner_text()) + " " + (await el.get_attribute("aria-label") or "")
                m = re.search(r"([\d,]+)", txt)
                if m:
                    try:
                        biz.google_reviews = int(m.group(1).replace(",", ""))
                    except ValueError:
                        pass

        return biz
    except PwTimeout:
        log.debug("detail nav timeout: %s", biz.name)
        return biz
    except Exception as exc:
        log.debug("detail enrich error %s: %s", biz.name, exc)
        return biz


async def scrape_google_maps(
    industry: str,
    city: str,
    country: str,
    max_results: int | None = None,
) -> list[dict]:
    settings = get_settings()
    max_results = max_results or settings.max_results_per_scrape
    query = f"{industry} in {city} {country}"
    encoded = query.replace(" ", "+")
    url = f"https://www.google.com/maps/search/{encoded}/"
    results: list[BusinessResult] = []

    log.info("Google Maps scrape: %s (max %d)", query, max_results)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            await _dismiss_consent(page)
            await asyncio.sleep(1.5)

            await _scroll_feed(page, max_results)

            cards = await page.query_selector_all('div.Nv2PK')
            if not cards:
                cards = await page.query_selector_all('div[jsaction*="mouseover"][role="article"]')
            log.info("Found %d result cards", len(cards))

            seen: set[str] = set()
            for card in cards[:max_results]:
                biz = await _extract_from_card(card, city, country)
                if biz and biz.name and biz.name not in seen:
                    seen.add(biz.name)
                    results.append(biz)

            log.info("Enriching %d listings via detail navigation…", len(results))
            enriched = 0
            for biz in results:
                if biz.phone and biz.website_url:
                    enriched += 1
                    continue
                await _enrich_from_detail(page, biz)
                if biz.phone or biz.website_url:
                    enriched += 1
                await _random_delay(0.5, 1.2)
            log.info("Enriched %d/%d listings", enriched, len(results))

        except Exception as exc:
            log.error("Google Maps scrape failed: %s", exc)
        finally:
            await browser.close()

    out = [b.to_dict() for b in results if b.name]
    log.info("Google Maps: %d businesses extracted", len(out))
    return out
