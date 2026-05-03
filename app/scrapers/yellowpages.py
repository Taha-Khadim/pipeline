"""
Stub module — Google Search scraping is blocked by CAPTCHA.
This module exists to keep the import working but simply returns empty results.
The actual scraping is done by google_maps.py and yelp.py (Bing Local).
"""

from __future__ import annotations
import logging

log = logging.getLogger(__name__)


async def scrape_yellowpages(
    industry: str,
    city: str,
    country: str,
    max_results: int = 30,
) -> list[dict]:
    log.info("Google Search source disabled (CAPTCHA), skipping")
    return []
